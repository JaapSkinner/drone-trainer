from OpenGL.GL import *
from OpenGL.GLUT import *
from OpenGL.GLU import *
import numpy as np

from models.scene_object import SceneObject


class Grid(SceneObject):
    def __init__(self, pose=None, name=None, colour=None, controllable=False):
        super().__init__(pose, name, shaded=False, controllable=False)
        if name is None:
            self.name = "Unnamed Grid"

        if colour is not None and len(colour) == 3:
            colour = (*colour, 1.0)

        self.colour = colour if colour else (0.68, 0.68, 0.68, 1.0)  # Default color (0 - 1) (r, g, b, a)

    def _draw(self):
        current_thickness = glGetFloatv(GL_LINE_WIDTH)
        glLineWidth(1.0)
        glColor3f(*self.colour[:3])
        glBegin(GL_LINES)
        for i in range(-10, 11):
            glVertex3f(i, 0, -10)
            glVertex3f(i, 0, 10)
            glVertex3f(-10, 0, i)
            glVertex3f(10, 0, i)
        glEnd()
        glLineWidth(current_thickness)