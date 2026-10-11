"""Headless OpenGL (EGL pbuffer) for render tests, snapshots and benchmarks.

Import this module *before* anything else imports OpenGL: PyOpenGL picks its
platform (GLX/EGL) on first import.

Works with a GPU driver or Mesa's software renderer (``EGL_PLATFORM=surfaceless``).
"""
import ctypes
import os
import struct
import sys
import zlib

os.environ.setdefault("PYOPENGL_PLATFORM", "egl")
os.environ.setdefault("EGL_PLATFORM", "surfaceless")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import numpy as np  # noqa: E402

# Exit code meaning "skipped: no headless GL here" (same convention as automake).
EXIT_SKIP = 77


class HeadlessGLUnavailable(RuntimeError):
    pass


class HeadlessContext:
    """A desktop-GL (compatibility profile) context rendering into a pbuffer."""

    def __init__(self, width: int = 640, height: int = 480):
        try:
            from OpenGL import EGL
        except Exception as exc:  # pragma: no cover - depends on the machine
            raise HeadlessGLUnavailable(f"PyOpenGL EGL unavailable: {exc}") from exc
        self._egl = EGL
        self.width, self.height = width, height

        self._display = EGL.eglGetDisplay(EGL.EGL_DEFAULT_DISPLAY)
        major, minor = EGL.EGLint(), EGL.EGLint()
        if not EGL.eglInitialize(self._display, ctypes.pointer(major), ctypes.pointer(minor)):
            raise HeadlessGLUnavailable("eglInitialize failed")

        attrs = (EGL.EGLint * 13)(
            EGL.EGL_SURFACE_TYPE, EGL.EGL_PBUFFER_BIT,
            EGL.EGL_RED_SIZE, 8, EGL.EGL_GREEN_SIZE, 8, EGL.EGL_BLUE_SIZE, 8,
            EGL.EGL_DEPTH_SIZE, 24,
            EGL.EGL_RENDERABLE_TYPE, EGL.EGL_OPENGL_BIT,
            EGL.EGL_NONE)
        config, count = EGL.EGLConfig(), EGL.EGLint()
        if not EGL.eglChooseConfig(self._display, attrs, ctypes.pointer(config), 1,
                                   ctypes.pointer(count)) or count.value < 1:
            raise HeadlessGLUnavailable("no suitable EGL config")

        pb_attrs = (EGL.EGLint * 5)(EGL.EGL_WIDTH, width, EGL.EGL_HEIGHT, height, EGL.EGL_NONE)
        self._surface = EGL.eglCreatePbufferSurface(self._display, config, pb_attrs)
        if not EGL.eglBindAPI(EGL.EGL_OPENGL_API):
            raise HeadlessGLUnavailable("desktop OpenGL API not available through EGL")
        self._context = EGL.eglCreateContext(self._display, config, EGL.EGL_NO_CONTEXT, None)
        if not self._context or not EGL.eglMakeCurrent(self._display, self._surface,
                                                      self._surface, self._context):
            raise HeadlessGLUnavailable("could not make an EGL context current")

    @property
    def renderer_name(self) -> str:
        from OpenGL.GL import GL_RENDERER, glGetString
        return glGetString(GL_RENDERER).decode(errors="replace")

    def read_rgb(self) -> np.ndarray:
        """Framebuffer as an (H, W, 3) uint8 array, top row first."""
        from OpenGL.GL import GL_RGB, GL_UNSIGNED_BYTE, glFinish, glReadPixels
        glFinish()
        raw = glReadPixels(0, 0, self.width, self.height, GL_RGB, GL_UNSIGNED_BYTE)
        return np.frombuffer(raw, np.uint8).reshape(self.height, self.width, 3)[::-1].copy()

    def close(self):
        EGL = self._egl
        EGL.eglMakeCurrent(self._display, EGL.EGL_NO_SURFACE, EGL.EGL_NO_SURFACE, EGL.EGL_NO_CONTEXT)
        EGL.eglDestroyContext(self._display, self._context)
        EGL.eglDestroySurface(self._display, self._surface)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def save_png(rgb: np.ndarray, path: str):
    """Write an (H, W, 3) uint8 array as a PNG (no imaging library needed)."""
    h, w, _ = rgb.shape
    raw = b"".join(b"\x00" + rgb[row].tobytes() for row in range(h))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n")
        fh.write(chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)))
        fh.write(chunk(b"IDAT", zlib.compress(raw, 6)))
        fh.write(chunk(b"IEND", b""))


def project_to_pixel(camera, point, width, height):
    """Pixel (x, y) — origin top-left — where a scene point appears."""
    p = np.array([*point, 1.0])
    clip = camera.projection_matrix(width / height) @ camera.view_matrix() @ p
    ndc = clip[:3] / clip[3]
    return int(round((ndc[0] + 1) / 2 * width)), int(round((1 - ndc[1]) / 2 * height))
