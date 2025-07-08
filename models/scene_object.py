from OpenGL.GL import *
from OpenGL.GLUT import *
from OpenGL.GLU import *
from math import sin, cos
import numpy as np
from abc import ABC, abstractmethod

class SceneObject(ABC):
    def __init__(self, pose=None, name=None, rendered=True, shaded=True):
        self.pose = pose if pose else (0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0) # Default pose: position, quaternion (x, y, z, qw, qx, qy, qz)
        self.name = name if name else "Unnamed Object"
        self.tracked = False
        self.vicon_id = None  # Vicon ID for tracking, if applicable
        self.rendered = rendered
        self.shaded = shaded  # Whether the object should be shaded

        self.pose_delta = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]  # (dx, dy, dz, dqw, dqx, dqy, dqz)

    def set_name(self, name):
        """Set the name of the object."""
        if isinstance(name, str):
            self.name = name
        else:
            raise ValueError("Name must be a string")

    def set_tracked(self, tracked, vicon_id=None):
        """Set whether the object is tracked. If tracked is True, vicon_id must be provided."""
        if isinstance(tracked, bool):
            if tracked and vicon_id is not None:
                self.vicon_id = vicon_id
            elif tracked and vicon_id is None and self.vicon_id is None:
                raise ValueError("Vicon ID must be provided if tracked is True")
            self.tracked = tracked
        else:
            raise ValueError("Tracked must be a boolean value")

    def set_pose(self, pose):
        """Set the pose of the object."""
        if len(pose) == 7:
            self.pose = pose
        else:
            raise ValueError("Pose must be of length 7")

    def set_pose_delta(self,  pose_delta):
        """Set the pose delta of the object."""
        if len(pose_delta) == 7:
            self.pose_delta = pose_delta
        else:
            raise ValueError("Pose delta must be of length 7")
    
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

    @abstractmethod
    def _draw(self):
        """Abstract method to draw the object. Must be implemented by subclasses."""
        pass

    def draw(self):
        if not self.shaded:
            glDisable(GL_LIGHTING)
            self._draw()
            glEnable(GL_LIGHTING)
        else:
            self._draw()
