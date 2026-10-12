"""Benchmark the renderer with many moving meshes (headless).

    python scripts/bench_render.py --meshes 10 --frames 300 --min-fps 60

Every frame moves and rotates every mesh, which is the case that used to
stall the viewport (issue #26).
"""
import argparse
import math
import sys
import time

import headless_gl  # must come before any OpenGL import

# Measure like the app runs (main.py turns PyOpenGL's per-call error checks off).
from ui.gl_widget import pyopengl_options  # noqa: E402
pyopengl_options.configure("--gl-checks" in sys.argv)
from headless_gl import EXIT_SKIP, HeadlessContext, HeadlessGLUnavailable


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--meshes", type=int, default=10)
    parser.add_argument("--frames", type=int, default=300)
    parser.add_argument("--size", default="1280x720")
    parser.add_argument("--mesh", default="cad_files/basic_quadcopter.stl")
    parser.add_argument("--gl-checks", action="store_true", help="keep PyOpenGL's error checks on")
    parser.add_argument("--min-fps", type=float, default=0.0,
                        help="exit non-zero if the average frame rate is below this")
    args = parser.parse_args()
    width, height = (int(v) for v in args.size.split("x"))

    try:
        ctx = HeadlessContext(width, height)
    except HeadlessGLUnavailable as exc:
        print(f"SKIP: {exc}")
        return EXIT_SKIP

    with ctx:
        from OpenGL.GL import glFinish
        from models import frames
        from models.cad_mesh import CadMesh
        from models.grid import Grid
        from ui.gl_widget.scene_renderer import Camera, SceneRenderer

        renderer = SceneRenderer()
        renderer.initialize()
        meshes = [CadMesh(args.mesh, name=f"m{i}", scale=0.05) for i in range(args.meshes)]
        scene = [Grid(name="Grid"), *meshes]
        camera = Camera(distance=14.0)

        def step(frame):
            t = frame / 60.0
            for i, m in enumerate(meshes):
                a = t + i * 2 * math.pi / len(meshes)
                q = frames.quat_from_axis_angle((0, 1, 0), a)
                m.set_pose((4 * math.cos(a), 1.0 + 0.3 * math.sin(3 * a), 4 * math.sin(a), *q))
            renderer.render(scene, camera, width, height, viewport=(0, 0, width, height))
            glFinish()

        step(0)  # warm-up (uploads buffers)
        buffers_before = renderer.buffers.live_count
        start = time.perf_counter()
        for f in range(1, args.frames + 1):
            step(f)
        elapsed = time.perf_counter() - start
        fps = args.frames / elapsed

        print(f"renderer:   {ctx.renderer_name}")
        print(f"scene:      {args.meshes} x {meshes[0].triangle_count} triangles, {args.frames} frames, {width}x{height}")
        print(f"frame time: {1000 * elapsed / args.frames:.2f} ms  ({fps:.0f} FPS)")
        print(f"GL buffers: {buffers_before} before, {renderer.buffers.live_count} after")

        if renderer.buffers.live_count != buffers_before:
            print("FAIL: GL buffers leaked while objects moved")
            return 1
        if fps < args.min_fps:
            print(f"FAIL: below {args.min_fps:.0f} FPS")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
