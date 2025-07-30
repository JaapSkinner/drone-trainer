from OpenGL.GL import *
from OpenGL.GLUT import *
from OpenGL.GLU import *
import numpy as np

from models.scene_object import SceneObject


class RectPrism(SceneObject):
    def __init__(self, pose=None, name=None, dimensions=(1.0, 1.0, 1.0), colour=None, edge_colour=(0.0, 0.0, 0.0)):
        super().__init__(pose, name)
        if name is None:
            self.name = "Unnamed Rectangular Prism"

        if isinstance(dimensions, (int, float)):
            dimensions = (dimensions, dimensions, dimensions)

        self.dimensions = dimensions

        if colour is not None and len(colour) == 3:
            colour = (*colour, 1.0)

        if len(edge_colour) == 3:
            edge_colour = (*edge_colour, 1.0)

        self.colour = colour if colour else (0.5, 0.5, 0.5, 1.0)  # Default color (0 - 1) (r, g, b, a)
        self.edge_colour = edge_colour if edge_colour else (0.0, 0.0, 0.0, 1.0)  # Default edge color (0 - 1) (r, g, b, a)


    def set_dimensions(self, dimensions=(1.0,1.0,1.0)):
        """Set the dimensions of the rectangular prism."""
        if len(dimensions) == 3:
            self.dimensions = dimensions
        elif isinstance(dimensions, (int, float)):
            self.dimensions = (dimensions, dimensions, dimensions)
        else:
            raise ValueError("Dimensions must be a tuple of length 3 (length, width, height)")

    def _draw(self):
        # Draw solid rectangle
        glPushMatrix()
        glTranslatef(*self.pose[:3])
        glMultMatrixf(self.quat_to_matrix(self.pose[3:]))
        glScalef(*self.dimensions)
        glColor4f(*self.colour)
        glutSolidCube(1.0)
        glPopMatrix()

        # Draw wireframe rectangle
        glPushMatrix()
        glTranslatef(*self.pose[:3])

        glMultMatrixf(self.quat_to_matrix(self.pose[3:]))
        glScalef(*self.dimensions)
        glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)
        glLineWidth(3.0)
        glColor4f(*self.edge_colour)
        glutSolidCube(1.0)
        glPopMatrix()

        # Ensure OpenGL state is reset to default after rendering
        glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)  # Reset polygon mode to fill
        glLineWidth(1.0)  # Reset line width