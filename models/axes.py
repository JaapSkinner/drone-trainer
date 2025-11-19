from OpenGL.GL import *
from OpenGL.GLUT import *
from OpenGL.GLU import *
import numpy as np

from models.scene_object import SceneObject


class Axes(SceneObject):
    def __init__(self, pose=None, name=None):
        super().__init__(pose, name, shaded=False)
        if name is None:
            self.name = "Unnamed Axes"


    def _draw(self):
        current_thickness = glGetFloatv(GL_LINE_WIDTH)
        glLineWidth(3.0)
        glBegin(GL_LINES)
        glColor3f(1.0, 0.0, 0.0)
        glVertex3f(0, 0, 0)
        glVertex3f(1, 0, 0)
        glColor3f(0.0, 1.0, 0.0)
        glVertex3f(0, 0, 0)
        glVertex3f(0, 1, 0)
        glColor3f(0.0, 0.0, 1.0)
        glVertex3f(0, 0, 0)
        glVertex3f(0, 0, 1)
        glEnd()
        glLineWidth(current_thickness)