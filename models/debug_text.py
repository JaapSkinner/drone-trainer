from OpenGL.GL import *
from OpenGL.GLUT import *
from OpenGL.GLU import *
import numpy as np

from models.scene_object import SceneObject


class DebugText(SceneObject):
    def __init__(self, pose=None, name=None, offset: tuple = None, text=None, colour=None, dimensions=None):
        super().__init__(pose, name, shaded=False)
        if name is None:
            self.name = "Unnamed Grid"

        if offset is None:
            offset = (0.0, 0.0, 0.0)

        self.offset = offset
        if len(offset) == 2:
            self.offset = (*offset, 0.0)

        self.value = 0.0

        if text is None:
            text = "Debug"

        self.text = text

        self.dimensions = None
        self.set_dimensions(dimensions)

        if colour is not None and len(colour) == 3:
            colour = (*colour, 1.0)

        self.colour = colour if colour else (0.0, 0.0, 0.0, 1.0)  # Default color (0 - 1) (r, g, b, a)

    def update(self, value, dimensions=None):
        """Update the debug text value."""
        self.value = value
        if dimensions:
            self.set_dimensions(dimensions)

    def set_offset(self, new_offset: tuple = None):
        if new_offset is None:
            new_offset = (0.0, 0.0, 0.0)
        if len(new_offset) == 2:
            new_offset = (*new_offset, 0.0)
        if len(new_offset) != 3:
            raise ValueError("Offset must be a tuple of length 3 (x, y, z)")
        self.offset = new_offset

    def set_dimensions(self, new_dimensions=None):
        if new_dimensions is None:
            new_dimensions = (800, 600)
        if isinstance(new_dimensions, (int, float)):
            new_dimensions = (new_dimensions, new_dimensions)
        if len(new_dimensions) != 2:
            raise ValueError("Dimensions must be a tuple of length 2 (width, height)")
        self.dimensions = new_dimensions



    def _draw(self):
        """Draw debug text at specified position."""
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(0, self.dimensions[0], 0, self.dimensions[1], -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()
        glColor4f(*self.colour)
        glRasterPos2f(10 + self.offset[0], self.dimensions[1] - 20 - self.offset[1] - self.offset[2])
        fps_text = f"{self.text}: {self.value:.1f}"
        for ch in fps_text:
            glutBitmapCharacter(GLUT_BITMAP_HELVETICA_18, ord(ch))
        glPopMatrix()
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)