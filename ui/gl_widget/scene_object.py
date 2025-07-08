
from OpenGL.GL import *
from OpenGL.GLUT import *
from OpenGL.GLU import *

class SceneObject:
    def __init__(self, x, y, z, x_rot, y_rot, z_rot, color, size, name, length=0.5, transparency=1.0, tracked=False):
        self.x_pos = x
        self.y_pos = y
        self.z_pos = z
        self.x_rot = x_rot
        self.y_rot = y_rot
        self.z_rot = z_rot
        self.color = color
        self.size = size
        self.length = length
        self.transparency = transparency
        self.tracked = tracked
        self.name = name

        self.x_vel = 0.0  # Adding velocity attributes
        self.y_vel = 0.0
        self.z_vel = 0.0

    def set_position(self, x, y, z):
        """Set the position of the object."""
        self.x_pos = x
        self.y_pos = y
        self.z_pos = z
        
    def set_rotation(self, x_rot, y_rot, z_rot):
        """Set the rotation of the object."""
        self.x_rot = x_rot
        self.y_rot = y_rot
        self.z_rot = z_rot
        
    def set_velocity(self, x_vel, y_vel, z_vel):
        """Set the velocity of the object."""
        self.x_vel = x_vel
        self.y_vel = y_vel
        self.z_vel = z_vel     

    def draw(self):
        # Draw solid rectangle
        glPushMatrix()
        glTranslatef(self.x_pos, self.y_pos, self.z_pos)
        glRotatef(self.x_rot, 1.0, 0.0, 0.0)
        glRotatef(self.y_rot, 0.0, 1.0, 0.0)
        glRotatef(self.z_rot, 0.0, 0.0, 1.0)
        glScalef(self.length, self.size, self.size)
        glColor4f(*self.color, self.transparency)
        glutSolidCube(1.0)
        glPopMatrix()

        # Draw wireframe rectangle
        glPushMatrix()
        glTranslatef(self.x_pos, self.y_pos, self.z_pos)
        glRotatef(self.x_rot, 1.0, 0.0, 0.0)
        glRotatef(self.y_rot, 0.0, 1.0, 0.0)
        glRotatef(self.z_rot, 0.0, 0.0, 1.0)
        glScalef(self.length, self.size, self.size)
        glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)
        glLineWidth(3.0)
        glColor3f(0.0, 0.0, 0.0)
        glutSolidCube(1.0)
        glPopMatrix()

        # Ensure OpenGL state is reset to default after rendering
        glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)  # Reset polygon mode to fill
        glLineWidth(1.0)  # Reset line width