
from OpenGL.GL import *
from OpenGL.GLUT import *
from OpenGL.GLU import *
from math import sin, cos
import numpy as np

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
        # Quaternion stored as [w, x, y, z]
        self.q = np.array([1.0, 0.0, 0.0, 0.0])

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
    
    @staticmethod
    def axis_angle_to_quat(axis, angle):
        half = 0.5 * angle
        w = cos(half)
        xyz = np.array(axis) * sin(half)
        return np.concatenate([[w], xyz])
    
    @staticmethod
    def quat_mult(q1, q2):
        w1, x1, y1, z1 = q1
        w2, x2, y2, z2 = q2
        return np.array([
            w1*w2 - x1*x2 - y1*y2 - z1*z2,
            w1*x2 + x1*w2 + y1*z2 - z1*y2,
            w1*y2 - x1*z2 + y1*w2 + z1*x2,
            w1*z2 + x1*y2 - y1*x2 + z1*w2
        ])
    
    @staticmethod
    def quat_to_matrix(q):
        w, x, y, z = q
        return np.array([
            [1 - 2*(y*y + z*z),   2*(x*y - z*w),     2*(x*z + y*w),     0],
            [2*(x*y + z*w),       1 - 2*(x*x + z*z), 2*(y*z - x*w),     0],
            [2*(x*z - y*w),       2*(y*z + x*w),     1 - 2*(x*x + y*y), 0],
            [0, 0, 0, 1]
        ], dtype=np.float32).T

    
    def draw(self):
        omega = np.array([self.x_rot, self.y_rot, self.z_rot])  # angle per frame (radians)
        angle = np.linalg.norm(omega)
        if angle > 1e-6:
            axis = omega / angle
            dq = self.axis_angle_to_quat(axis, angle)
            self.q = self.quat_mult(dq, self.q)
            self.q /= np.linalg.norm(self.q)  # keep it unit
            
            
        # Draw solid rectangle
        glPushMatrix()
        glTranslatef(self.x_pos, self.y_pos, self.z_pos)
        glMultMatrixf(self.quat_to_matrix(self.q))
        glScalef(self.length, self.size, self.size)
        glColor4f(*self.color, self.transparency)
        glutSolidCube(1.0)
        glPopMatrix()

        # Draw wireframe rectangle
        glPushMatrix()
        glTranslatef(self.x_pos, self.y_pos, self.z_pos)

        glMultMatrixf(self.quat_to_matrix(self.q))
        glScalef(self.length, self.size, self.size)
        glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)
        glLineWidth(3.0)
        glColor3f(0.0, 0.0, 0.0)
        glutSolidCube(1.0)
        glPopMatrix()

        # Ensure OpenGL state is reset to default after rendering
        glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)  # Reset polygon mode to fill
        glLineWidth(1.0)  # Reset line width