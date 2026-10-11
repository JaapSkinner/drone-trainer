import numpy as np
from OpenGL.GL import (GL_CURRENT_BIT, GL_LIGHTING, GL_LINE_BIT, glColor4f, glDisable, glLineWidth,
                       glPopAttrib, glPushAttrib)

from models.gl_buffers import draw_lines
from models.scene_object import SceneObject


def dashed_segments(start, end, dash=0.08, gap=0.05) -> np.ndarray:
    """Line-segment endpoints (2N, 3) for a dashed line from ``start`` to ``end``."""
    a, b = np.asarray(start, dtype=float), np.asarray(end, dtype=float)
    length = float(np.linalg.norm(b - a))
    if length < 1e-9:
        return np.zeros((0, 3), np.float32)
    direction = (b - a) / length
    points, s = [], 0.0
    while s < length:
        points += [a + direction * s, a + direction * min(s + dash, length)]
        s += dash + gap
    return np.asarray(points, dtype=np.float32)


class Polyline(SceneObject):
    """Unlit line segments in scene coordinates (for overlays: setpoint lines, paths…)."""

    helper = True

    def __init__(self, segments=None, colour=(0.0, 0.0, 0.0, 1.0), width=2.0, name=None):
        super().__init__(None, name or "Line", shaded=False, controllable=False, colour=colour)
        self.segments = np.asarray(segments if segments is not None else np.zeros((0, 3)), dtype=np.float32)
        self.width = float(width)

    def _draw(self):
        glPushAttrib(GL_CURRENT_BIT | GL_LINE_BIT)
        try:
            glDisable(GL_LIGHTING)
            glLineWidth(self.width)
            glColor4f(*self.effective_colour())
            draw_lines(self.segments)
        finally:
            glPopAttrib()
