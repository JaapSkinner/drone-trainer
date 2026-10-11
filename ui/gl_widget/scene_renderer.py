"""Draws the scene with OpenGL. No Qt here, so it also runs in headless tests.

Frame order: flush deferred GL deletions → reset state → clear → camera →
opaque objects → translucent objects back-to-front (depth writes off).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional, Sequence, Tuple

import numpy as np
from OpenGL.GL import (GL_BLEND, GL_COLOR_BUFFER_BIT, GL_COLOR_MATERIAL, GL_CULL_FACE,
                       GL_DEPTH_BUFFER_BIT, GL_DEPTH_TEST, GL_DIFFUSE, GL_LEQUAL, GL_FALSE, GL_LIGHT0,
                       GL_LIGHTING, GL_MODELVIEW, GL_ONE_MINUS_SRC_ALPHA, GL_POSITION,
                       GL_PROJECTION, GL_SMOOTH, GL_SPECULAR, GL_AMBIENT, GL_SRC_ALPHA,
                       GL_TRUE, GL_AMBIENT_AND_DIFFUSE, GL_FRONT_AND_BACK, glBlendFunc, glClear,
                       glClearColor, glColorMaterial, glDepthFunc, glDepthMask, glDisable, glEnable,
                       glLightfv, glLoadMatrixf, glMatrixMode, glShadeModel, glViewport)

from models import gl_buffers


@dataclass
class Camera:
    """Orbit camera around ``target`` (scene frame, Y up). Angles in degrees."""
    distance: float = 10.0
    angle_x: float = 30.0   # elevation
    angle_y: float = 45.0   # azimuth around +Y
    target: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    fov_y_deg: float = 45.0
    near: float = 0.05
    far: float = 200.0

    def eye(self) -> np.ndarray:
        ax, ay = math.radians(self.angle_x), math.radians(self.angle_y)
        offset = np.array([math.sin(ay) * math.cos(ax), math.sin(ax), math.cos(ay) * math.cos(ax)])
        return np.asarray(self.target, dtype=float) + self.distance * offset

    def projection_matrix(self, aspect: float) -> np.ndarray:
        f = 1.0 / math.tan(math.radians(self.fov_y_deg) / 2.0)
        n, fa = self.near, self.far
        return np.array([
            [f / aspect, 0, 0, 0],
            [0, f, 0, 0],
            [0, 0, (fa + n) / (n - fa), 2 * fa * n / (n - fa)],
            [0, 0, -1, 0],
        ], dtype=np.float32)

    def view_matrix(self) -> np.ndarray:
        eye = self.eye()
        forward = np.asarray(self.target, dtype=float) - eye
        forward /= np.linalg.norm(forward)
        up = np.array([0.0, 1.0, 0.0])
        side = np.cross(forward, up)
        if np.linalg.norm(side) < 1e-9:  # looking straight up/down
            side = np.array([1.0, 0.0, 0.0])
        side /= np.linalg.norm(side)
        true_up = np.cross(side, forward)
        m = np.identity(4, dtype=np.float32)
        m[0, :3], m[1, :3], m[2, :3] = side, true_up, -forward
        m[:3, 3] = -m[:3, :3] @ eye
        return m


@dataclass
class SceneRenderer:
    background: Tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)
    # Directional light, deliberately off the default view diagonal so the
    # visible faces of a box get different shades.
    light_position: Tuple[float, float, float, float] = (4.0, 10.0, 2.0, 0.0)
    last_draw_count: int = field(default=0, init=False)

    def initialize(self):
        """Call once per GL context (from ``initializeGL``)."""
        gl_buffers.begin_context()

    def _apply_state(self):
        glEnable(GL_DEPTH_TEST)
        # LEQUAL: lines drawn later at the same depth (axes over the grid) win.
        glDepthFunc(GL_LEQUAL)
        glDepthMask(GL_TRUE)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDisable(GL_CULL_FACE)
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        glEnable(GL_COLOR_MATERIAL)
        glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
        glLightfv(GL_LIGHT0, GL_AMBIENT, [0.25, 0.25, 0.25, 1.0])
        glLightfv(GL_LIGHT0, GL_DIFFUSE, [0.85, 0.85, 0.85, 1.0])
        glLightfv(GL_LIGHT0, GL_SPECULAR, [1.0, 1.0, 1.0, 1.0])
        glShadeModel(GL_SMOOTH)

    def render(self, objects: Iterable, camera: Camera, width: int, height: int,
               viewport: Optional[Sequence[int]] = None, overlays: Iterable = (),
               alpha_for: Optional[Callable] = None):
        """Draw one frame.

        ``width``/``height`` set the aspect ratio. Pass ``viewport`` to also
        call glViewport (QOpenGLWidget sets the viewport itself).
        ``overlays`` are extra drawables (e.g. setpoint markers) and
        ``alpha_for(obj)`` scales each scene object's opacity for this frame.
        """
        gl_buffers.flush_pending_deletes()
        self._apply_state()
        if viewport is not None:
            glViewport(*viewport)
        glClearColor(*self.background)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        glMatrixMode(GL_PROJECTION)
        glLoadMatrixf(camera.projection_matrix(width / max(1, height)).T)
        glMatrixMode(GL_MODELVIEW)
        glLoadMatrixf(camera.view_matrix().T)
        glLightfv(GL_LIGHT0, GL_POSITION, list(self.light_position))

        visible = [o for o in objects if getattr(o, "rendered", True)]
        for obj in visible:
            obj.draw_alpha_scale = alpha_for(obj) if alpha_for is not None else 1.0
        visible += list(overlays)
        opaque = [o for o in visible if not o.is_translucent()]
        translucent = [o for o in visible if o.is_translucent()]
        eye = camera.eye()
        translucent.sort(key=lambda o: -float(np.linalg.norm(np.asarray(o.pose[:3]) - eye)))

        for obj in opaque:
            obj.draw()
        if translucent:
            glDepthMask(GL_FALSE)
            for obj in translucent:
                obj.draw()
            glDepthMask(GL_TRUE)
        self.last_draw_count = len(visible)
