"""PyOpenGL options that must be set before anything imports ``OpenGL.GL``.

PyOpenGL checks ``glGetError`` after every call by default, which costs more
than many of the calls themselves. The app turns it off (``main.py``); tests
leave it on so GL mistakes fail loudly. ``DRONE_TRAINER_GL_CHECKS=1`` turns it
back on in the app for debugging.
"""
import os


def configure(error_checking: bool = None):
    """Call first thing, before importing ``OpenGL.GL`` (or anything that does)."""
    import OpenGL
    if error_checking is None:
        error_checking = os.environ.get("DRONE_TRAINER_GL_CHECKS") == "1"
    OpenGL.ERROR_CHECKING = bool(error_checking)
    if not error_checking:
        # PyOpenGL 3.1's EGL error module forgets to define _error_checker when checks are
        # off, so importing OpenGL.EGL would fail (headless/Wayland EGL only).
        try:
            from OpenGL.raw.EGL import _errors as egl_errors
        except ImportError:   # no EGL support in this PyOpenGL build: nothing to patch
            return
        if not hasattr(egl_errors, "_error_checker"):
            egl_errors._error_checker = None
