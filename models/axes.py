import numpy as np
from OpenGL.GL import GL_CURRENT_BIT, GL_LINE_BIT, glLineWidth, glPopAttrib, glPushAttrib

from models.gl_buffers import draw_lines
from models.scene_object import SceneObject

# X red, Y green, Z blue — one unit long.
_POINTS = np.array([(0, 0, 0), (1, 0, 0), (0, 0, 0), (0, 1, 0), (0, 0, 0), (0, 0, 1)], dtype=np.float32)
_COLOURS = np.array([(1, 0, 0), (1, 0, 0), (0, 1, 0), (0, 1, 0), (0, 0, 1), (0, 0, 1)], dtype=np.float32)


class Axes(SceneObject):
    """Scene origin axes."""

    def __init__(self, pose=None, name=None, controllable=False, length=1.0):
        super().__init__(pose, name or "Unnamed Axes", shaded=False, controllable=controllable)
        self.length = float(length)

    def _draw(self):
        glPushAttrib(GL_CURRENT_BIT | GL_LINE_BIT)
        try:
            glLineWidth(3.0)
            draw_lines(_POINTS * self.length, _COLOURS)
        finally:
            glPopAttrib()
