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

    # 4. Moving a mesh doesn't create GL buffers.
    from models import gl_buffers
    before = gl_buffers.live_buffer_count()
    for i in range(30):
        mesh.set_pose((-2.5 + 0.01 * i, 0.0, 2.5, 1.0, 0.0, 0.0, 0.0))
        renderer.render([mesh], camera, w, h, viewport=(0, 0, w, h))
    if gl_buffers.live_buffer_count() != before:
        failures.append(f"buffer count changed {before} -> {gl_buffers.live_buffer_count()}")

    # 5. Releasing frees the buffer at the next frame.
    mesh.release_gl()
    renderer.render([], camera, w, h, viewport=(0, 0, w, h))
    if gl_buffers.live_buffer_count() != before - 1:
        failures.append(f"buffer not freed: {gl_buffers.live_buffer_count()} live")

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
