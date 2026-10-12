"""Benchmark the whole app with moving meshes: frame rate as the user would see it (headless).

    python scripts/bench_app.py --drones 5 --seconds 5
    python scripts/bench_app.py --drones 10 --panel objects --expand --profile

Boots the real MainWindow, streams synthetic Vicon data (scripts/fake_vicon.py) to
it, and gives every subject a tracked quadcopter mesh. Each frame runs the Qt
event loop (motion capture, panels, timers, signals) and then draws the
viewport into an EGL pbuffer on the GUI thread, as QOpenGLWidget.paintGL would.
So it measures everything that competes with rendering, not just the renderer
(scripts/bench_render.py measures the renderer alone).
"""
import argparse
import cProfile
import os
import pstats
import socket
import subprocess
import sys
import tempfile
import time

import headless_gl  # must come before any OpenGL import

# Measure like the app runs (main.py turns PyOpenGL's per-call error checks off).
from ui.gl_widget import pyopengl_options  # noqa: E402
pyopengl_options.configure("--gl-checks" in sys.argv)
from headless_gl import EXIT_SKIP, HeadlessContext, HeadlessGLUnavailable

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("DRONE_TRAINER_DATA_DIR", tempfile.mkdtemp(prefix="drone_trainer_bench_"))


def _free_udp_port():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--drones", type=int, default=5, help="tracked quadcopter meshes")
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--rate", type=float, default=100.0, help="motion capture packets per second")
    parser.add_argument("--size", default="1280x720")
    parser.add_argument("--panel", default="command", help="dock panel to show (command, objects, …)")
    parser.add_argument("--expand", action="store_true", help="expand every object card (Objects panel)")
    parser.add_argument("--vsync-ms", type=float, default=0.0,
                        help="pace frames like the app's 16 ms timer (0 = as fast as possible)")
    parser.add_argument("--profile", action="store_true", help="print where GUI-thread time goes")
    parser.add_argument("--gl-checks", action="store_true", help="keep PyOpenGL's error checks on")
    parser.add_argument("--min-fps", type=float, default=0.0)
    args = parser.parse_args()
    width, height = (int(v) for v in args.size.split("x"))

    try:
        ctx = HeadlessContext(width, height)
    except HeadlessGLUnavailable as exc:
        print(f"SKIP: {exc}")
        return EXIT_SKIP

    from OpenGL.GL import glFinish
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([sys.argv[0]])

    from models.cad_mesh import CadMesh
    from models.structs import MotionCaptureConfig
    from ui.main_window import MainWindow

    port = _free_udp_port()
    vicon = subprocess.Popen([sys.executable, os.path.join(headless_gl.REPO_ROOT, "scripts", "fake_vicon.py"),
                              "--port", str(port), "--subjects", str(args.drones), "--rate", str(args.rate),
                              "--duration", str(args.seconds + 20)], stdout=subprocess.DEVNULL)
    window = MainWindow()
    try:
        window.resize(1600, 900)
        window.show()
        window.save_motion_capture_config(MotionCaptureConfig(vicon_address="127.0.0.1", vicon_port=port))
        window.motion_capture_service.connect_source()
        for i in range(args.drones):
            mesh = CadMesh("cad_files/basic_quadcopter.stl", name=f"quad{i + 1}", scale=0.004)
            mesh.set_tracked(True, f"quad{i + 1}")
            window.object_service.add_object(mesh)
        window._show_panel(args.panel)
        if args.expand and args.panel == "objects":
            for obj in window.object_service.get_objects():
                card = window.objects_panel.card_for(obj)
                if card is not None:
                    card.set_expanded(True)

        gl = window.glWidget
        with ctx:
            renderer_name = ctx.renderer_name
            gl.renderer.initialize()

            def render():
                gl.renderer.render(window.object_service.get_objects(), gl.camera(), width, height,
                                   viewport=(0, 0, width, height), **gl.overlay_arguments())
                glFinish()

            # Wait until every subject is arriving.
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                app.processEvents()
                if len(window.motion_capture_service.subjects_snapshot()) >= args.drones + 1:
                    break
                time.sleep(0.01)
            for _ in range(30):   # warm-up: uploads buffers
                app.processEvents()
                render()

            profiler = cProfile.Profile() if args.profile else None
            frames, event_time, render_time = 0, 0.0, 0.0
            start = time.perf_counter()
            if profiler:
                profiler.enable()
            while time.perf_counter() - start < args.seconds:
                t0 = time.perf_counter()
                app.processEvents()
                t1 = time.perf_counter()
                render()
                t2 = time.perf_counter()
                event_time += t1 - t0
                render_time += t2 - t1
                frames += 1
                if args.vsync_ms:
                    spare = args.vsync_ms / 1000 - (time.perf_counter() - t0)
                    if spare > 0:
                        time.sleep(spare)
            elapsed = time.perf_counter() - start
            if profiler:
                profiler.disable()

        moving = sum(1 for o in window.object_service.get_objects() if o.tracked and o.tracking_age() is not None
                     and o.tracking_age() < 0.5)
        fps = frames / elapsed
        print(f"renderer:    {renderer_name}")
        print(f"scene:       {args.drones} tracked meshes ({moving} receiving), mocap {args.rate:.0f} Hz, "
              f"panel '{args.panel}'{' (cards expanded)' if args.expand else ''}")
        print(f"frame rate:  {fps:.0f} FPS  ({1000 * elapsed / frames:.2f} ms/frame)")
        print(f"per frame:   events/UI {1000 * event_time / frames:.2f} ms, render {1000 * render_time / frames:.2f} ms")
        if profiler:
            print()
            pstats.Stats(profiler).sort_stats("tottime").print_stats(25)
        return 1 if fps < args.min_fps else 0
    finally:
        vicon.terminate()
        window.close()
        app.processEvents()


if __name__ == "__main__":
    sys.exit(main())
