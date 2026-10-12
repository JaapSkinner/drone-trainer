"""Render the scene headlessly to a PNG, or self-check the renderer.

    python scripts/render_snapshot.py out.png        # default scene snapshot
    python scripts/render_snapshot.py --check        # pixel assertions (used by tests)

Exits with 77 when no headless GL is available.
"""
import argparse
import sys

import headless_gl  # must come before any OpenGL import
from headless_gl import EXIT_SKIP, HeadlessContext, HeadlessGLUnavailable, project_to_pixel, save_png


def default_scene():
    from models.default_scene import build_default_scene
    return build_default_scene()


def run_check(ctx) -> int:
    import numpy as np
    from models.rect_prism import RectPrism
    from models.cad_mesh import CadMesh
    from ui.gl_widget.scene_renderer import Camera, SceneRenderer

    w, h = ctx.width, ctx.height
    camera = Camera()
    renderer = SceneRenderer()
    renderer.initialize()

    red = RectPrism(name="red", colour=(1.0, 0.0, 0.0), edge_colour=None)
    # Translucent blue box halfway between the camera and the red box.
    glass = RectPrism(name="glass", colour=(0.0, 0.0, 1.0, 0.5), edge_colour=None)
    glass_pos = tuple(camera.eye() * 0.5)
    glass.set_pose((*glass_pos, 1.0, 0.0, 0.0, 0.0))
    mesh = CadMesh("cad_files/basic_quadcopter.stl", scale=0.05, colour=(0.0, 0.8, 0.0))
    mesh.set_pose((-2.5, 0.0, 2.5, 1.0, 0.0, 0.0, 0.0))

    failures = []

    def pixel(img, point):
        x, y = project_to_pixel(camera, point, w, h)
        return img[y, x].astype(int)

    # 1. Opaque: the red box's top face is red and the corner is background.
    top_face = (0.0, 0.5, 0.0)
    renderer.render([red], camera, w, h, viewport=(0, 0, w, h))
    img = ctx.read_rgb()
    red_top = pixel(img, top_face)
    r, g, b = red_top
    if not (r > 120 and g < 60 and b < 60):
        failures.append(f"red box top face is {r, g, b}")
    if tuple(img[2, 2]) != (255, 255, 255):
        failures.append(f"background corner is {tuple(img[2, 2])}")

    # 2. The mesh draws: adding it changes a meaningful number of pixels to green.
    renderer.render([red, mesh], camera, w, h, viewport=(0, 0, w, h))
    with_mesh = ctx.read_rgb()
    changed = np.any(with_mesh != img, axis=2)
    greenish = changed & (with_mesh[..., 1].astype(int) > with_mesh[..., 0].astype(int) + 40)
    if greenish.sum() < 500:
        failures.append(f"mesh only produced {int(greenish.sum())} green pixels")

    # 3. A translucent box in front blends with the red behind it.
    renderer.render([glass, red], camera, w, h, viewport=(0, 0, w, h))
    r, g, b = pixel(ctx.read_rgb(), top_face)
    if not (0.3 * red_top[0] < r < 0.7 * red_top[0] and b > 80 and g < 60):
        failures.append(f"translucent overlap is {r, g, b}; unblended red was {tuple(red_top)}")

    # 4. Moving a mesh doesn't create GL buffers, and a second mesh from the same file shares one.
    buffers = renderer.buffers
    before = buffers.live_count
    twin = CadMesh("cad_files/basic_quadcopter.stl", scale=0.05, colour=(0.0, 0.8, 0.0))
    for i in range(30):
        mesh.set_pose((-2.5 + 0.01 * i, 0.0, 2.5, 1.0, 0.0, 0.0, 0.0))
        twin.set_pose((2.5, 0.0, -2.5 + 0.01 * i, 1.0, 0.0, 0.0, 0.0))
        renderer.render([mesh, twin], camera, w, h, viewport=(0, 0, w, h))
    if buffers.live_count != before:
        failures.append(f"buffer count changed {before} -> {buffers.live_count}")

    # 5. The buffer is freed at the next frame once no object uses the mesh any more.
    mesh.release_gl()
    renderer.render([twin], camera, w, h, viewport=(0, 0, w, h))
    if buffers.live_count != before:
        failures.append(f"buffer freed while another object still uses it: {buffers.live_count} live")
    twin.release_gl()
    renderer.render([], camera, w, h, viewport=(0, 0, w, h))
    if buffers.live_count != before - 1:
        failures.append(f"buffer not freed: {buffers.live_count} live")

    # 6. Lines, per-vertex colours, translucent spheres and overlays all draw without GL errors.
    from OpenGL.GL import GL_NO_ERROR, glGetError
    from models.default_scene import build_default_scene
    from models.polyline import Polyline
    from models.sphere import Sphere
    ghost = Sphere(radius=0.3, colour=(1.0, 0.0, 0.0, 0.4))
    renderer.background_gradient = ((0.9, 0.9, 0.95, 1.0), (0.7, 0.7, 0.75, 1.0))
    renderer.render(build_default_scene() + [ghost], camera, w, h, viewport=(0, 0, w, h),
                    overlays=[Polyline([(0, 0, 0), (1, 1, 1)], (0, 0, 0, 1), width=2.0)])
    error = glGetError()
    if error != GL_NO_ERROR:
        failures.append(f"GL error 0x{error:x} drawing the default scene")
    corner = tuple(int(c) for c in ctx.read_rgb()[2, 2])
    if not (175 <= corner[0] <= 235 and corner[2] >= corner[0]):
        failures.append(f"background gradient corner is {corner}")

    # 7. Ground cues: the floor under a raised object is darker with its shadow drawn.
    from services.object_service import ObjectService
    from ui.gl_widget.ground_overlay import GroundOverlay
    renderer.background_gradient = None
    floater = Sphere(name="floater", radius=0.2, colour=(0.2, 0.4, 1.0))
    floater.set_pose((0.0, 1.5, 0.0, 1.0, 0.0, 0.0, 0.0))
    scene = ObjectService()
    scene.add_object(floater)
    renderer.render([floater], camera, w, h, viewport=(0, 0, w, h))
    floor = pixel(ctx.read_rgb(), (0.0, 0.0, 0.0))
    renderer.render([floater], camera, w, h, viewport=(0, 0, w, h), overlays=GroundOverlay(scene).drawables())
    shaded = pixel(ctx.read_rgb(), (0.0, 0.0, 0.0))
    if not shaded.sum() < floor.sum() - 60:
        failures.append(f"no shadow under a raised object: floor {tuple(floor)} -> {tuple(shaded)}")

    # 8. The selection glow changes the object's silhouette.
    renderer.render([red], camera, w, h, viewport=(0, 0, w, h))
    plain = ctx.read_rgb()
    renderer.render([red], camera, w, h, viewport=(0, 0, w, h), rim_for=lambda obj: (0.3, 0.3, 1.0, 1.0))
    glowing = ctx.read_rgb()
    changed = int(np.any(np.abs(glowing.astype(int) - plain.astype(int)) > 30, axis=2).sum())
    if changed < 300:
        failures.append(f"selection glow changed only {changed} pixels")

    for f in failures:
        print("FAIL:", f)
    print("render check:", "OK" if not failures else f"{len(failures)} failure(s)",
          f"[{ctx.renderer_name}]")
    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", nargs="?", default="snapshot.png")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--size", default="960x640")
    args = parser.parse_args()
    width, height = (int(v) for v in args.size.split("x"))

    try:
        ctx = HeadlessContext(width, height)
    except HeadlessGLUnavailable as exc:
        print(f"SKIP: {exc}")
        return EXIT_SKIP

    with ctx:
        if args.check:
            return run_check(ctx)
        from ui.gl_widget.scene_renderer import Camera, SceneRenderer
        renderer = SceneRenderer()
        renderer.initialize()
        renderer.render(default_scene(), Camera(), width, height, viewport=(0, 0, width, height))
        save_png(ctx.read_rgb(), args.output)
        print("saved", args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
