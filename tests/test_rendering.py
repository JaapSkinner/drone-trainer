"""Renders real frames headlessly and checks pixels (see scripts/render_snapshot.py).

Runs in a subprocess because PyOpenGL must select its EGL backend before any
other test imports OpenGL. Skipped when the machine has no headless EGL.
"""
import os
import subprocess
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXIT_SKIP = 77


class RenderingTests(unittest.TestCase):
    def test_renderer_pixel_checks(self):
        env = dict(os.environ, PYOPENGL_PLATFORM="egl")
        env.setdefault("EGL_PLATFORM", "surfaceless")
        result = subprocess.run(
            [sys.executable, os.path.join("scripts", "render_snapshot.py"), "--check"],
            cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=120)
        if result.returncode == EXIT_SKIP:
            self.skipTest(result.stdout.strip() or "headless GL unavailable")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
