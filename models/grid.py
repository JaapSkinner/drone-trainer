import numpy as np
from OpenGL.GL import GL_CURRENT_BIT, GL_LINE_BIT, glColor4f, glLineWidth, glPopAttrib, glPushAttrib

from models.gl_buffers import draw_lines
from models.scene_object import SceneObject


class Grid(SceneObject):
    """Ground grid on the scene's XZ plane (Y up)."""

    def __init__(self, pose=None, name=None, colour=None, controllable=False,
                 half_extent=10, spacing=1.0):
        super().__init__(pose, name or "Unnamed Grid", shaded=False, controllable=False,
                         colour=colour if colour is not None else (0.68, 0.68, 0.68, 1.0))
        self.half_extent = int(half_extent)
        self.spacing = float(spacing)
        self._lines = self._build_lines()

    def _build_lines(self) -> np.ndarray:
        n, s = self.half_extent, self.spacing
        lines = []
        for i in range(-n, n + 1):
            lines += [(i * s, 0.0, -n * s), (i * s, 0.0, n * s)]
            lines += [(-n * s, 0.0, i * s), (n * s, 0.0, i * s)]
        return np.array(lines, dtype=np.float32)

    def _draw(self):
        glPushAttrib(GL_CURRENT_BIT | GL_LINE_BIT)
        try:
            glLineWidth(1.0)
            glColor4f(*self.colour)
            draw_lines(self._lines)
        finally:
            glPopAttrib()
