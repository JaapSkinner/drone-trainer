from OpenGL.GL import (GL_ENABLE_BIT, GL_LIGHTING, glDisable, glMultMatrixf,
                       glPopAttrib, glPopMatrix, glPushAttrib, glPushMatrix)
import time

import numpy as np
from abc import ABC, abstractmethod
from models import frames
from models.structs import MavlinkObjectConfig


class SceneObject(ABC):
    """Base class for all scene objects.
    
    Attributes:
        pose: Position and orientation tuple (x, y, z, qw, qx, qy, qz)
        name: Human-readable name for the object
        tracked: Whether this object follows a motion capture subject
        tracking_id: Name of the mocap subject (Vicon object / OptiTrack rigid body)
        pose_locked: Ignore mocap updates and keep the current pose
        last_tracking_update: time.monotonic() of the last mocap sample (or None)
        rendered: Whether to render this object
        shaded: Whether to apply shading
        colour: Base RGBA colour (alpha < 1 renders translucent)
        controllable: Whether this object can be controlled by user input
        mavlink_config: MAVLink configuration for this object
    """
    
    DEFAULT_COLOUR = (0.5, 0.5, 0.5, 1.0)
    # Scene furniture (grid, axes): kept by "clear all", listed separately in the UI.
    helper = False

    def __init__(self, pose=None, name=None, rendered=True, shaded=True, controllable=True,
                 mavlink_enabled=False, colour=None):
        """Initialize a scene object.
        
        Args:
            pose: Initial pose tuple (x, y, z, qw, qx, qy, qz)
            name: Object name
            rendered: Whether to render
            shaded: Whether to apply shading
            controllable: Whether user can control this object
            mavlink_enabled: Whether MAVLink is enabled for this object
        """
        self.pose = pose if pose else (0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0) # Default pose: position, quaternion (x, y, z, qw, qx, qy, qz)
        self.name = name if name else "Unnamed Object"
        self.tracked = False
        self.tracking_id = None
        self.pose_locked = False
        self.last_tracking_update = None
        self.rendered = rendered
        self.shaded = shaded  # Whether the object should be shaded
        self.controllable = controllable
        self.colour = self._rgba(colour, self.DEFAULT_COLOUR)
        # Set by the renderer each frame, e.g. to fade an object that hides its setpoint.
        self.draw_alpha_scale = 1.0

        self.pose_delta = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]  # (dx, dy, dz, dqw, dqx, dqy, dqz)
        
        # MAVLink configuration for this object
        self.mavlink_config = MavlinkObjectConfig(enabled=mavlink_enabled)

    @staticmethod
    def _rgba(colour, default):
        """Normalise an RGB/RGBA tuple (or None) to a 4-tuple of floats."""
        if colour is None:
            return tuple(default)
        colour = tuple(float(c) for c in colour)
        if len(colour) == 3:
            colour = (*colour, 1.0)
        if len(colour) != 4:
            raise ValueError("Colour must have 3 or 4 components")
        return colour

    def effective_colour(self):
        """Colour to draw with this frame (alpha scaled by the renderer)."""
        r, g, b, a = self.colour
        return (r, g, b, a * self.draw_alpha_scale)

    def is_translucent(self) -> bool:
        return self.effective_colour()[3] < 1.0

    def bounding_radius(self) -> float:
        """Approximate size: distance from the object's origin to its furthest point (m)."""
        return 0.25

    def set_name(self, name):
        """Set the name of the object."""
        if isinstance(name, str):
            self.name = name
        else:
            raise ValueError("Name must be a string")

    def set_tracked(self, tracked: bool, tracking_id: str = None):
        """Follow (or stop following) a motion capture subject."""
        if not isinstance(tracked, bool):
            raise ValueError("Tracked must be a boolean value")
        if tracking_id is not None:
            self.tracking_id = str(tracking_id).strip() or None
        if tracked and not self.tracking_id:
            raise ValueError("A tracking ID is required to enable tracking")
        self.tracked = tracked

    def tracking_age(self, now: float = None):
        """Seconds since the last mocap sample, or None if never tracked."""
        if self.last_tracking_update is None:
            return None
        return (time.monotonic() if now is None else now) - self.last_tracking_update

    def set_pose(self, pose):
        """Set the pose (x, y, z, qw, qx, qy, qz) in the scene frame."""
        if len(pose) != 7:
            raise ValueError("Pose must be of length 7")
        self.pose = tuple(float(v) for v in pose)

    def set_pose_delta(self,  pose_delta):
        """Set the pose delta of the object."""
        if len(pose_delta) == 7:
            self.pose_delta = pose_delta
        else:
            raise ValueError("Pose delta must be of length 7")
    
    # Thin wrappers kept for existing callers; new code should use models.frames.
    @staticmethod
    def axis_angle_to_quat(axis, angle):
        return np.array(frames.quat_from_axis_angle(axis, angle))

    @staticmethod
    def quat_mult(q1, q2):
        return np.array(frames.quat_multiply(q1, q2))

    @staticmethod
    def quat_to_matrix(q):
        """4×4 rotation matrix laid out for glMultMatrixf (column-major)."""
        m = np.identity(4, dtype=np.float32)
        m[:3, :3] = frames.quat_to_matrix(q)
        return m.T

    # MAVLink configuration methods
    def set_mavlink_enabled(self, enabled: bool):
        """Enable or disable MAVLink for this object.
        
        Args:
            enabled: Whether MAVLink should be enabled
        """
        self.mavlink_config.enabled = enabled
    
    def is_mavlink_enabled(self) -> bool:
        """Check if MAVLink is enabled for this object.
        
        Returns:
            True if MAVLink is enabled
        """
        return self.mavlink_config.enabled
    
    def set_mavlink_config(self, config: MavlinkObjectConfig):
        """Set the MAVLink configuration for this object.
        
        Args:
            config: MAVLink configuration to apply
        """
        self.mavlink_config = config
    
    def get_mavlink_config(self) -> MavlinkObjectConfig:
        """Get the MAVLink configuration for this object.
        
        Returns:
            Current MAVLink configuration
        """
        return self.mavlink_config

    @abstractmethod
    def _draw(self):
        """Draw the object in its own (local) coordinates.

        ``draw()`` has already applied the object's pose, so subclasses only
        apply their own scale/offsets.
        """

    def draw(self):
        glPushMatrix()
        glPushAttrib(GL_ENABLE_BIT)
        try:
            glMultMatrixf(frames.gl_model_matrix(self.pose))
            if not self.shaded:
                glDisable(GL_LIGHTING)
            self._draw()
        finally:
            glPopAttrib()
            glPopMatrix()

    def release_gl(self):
        """Free GPU resources (called when the object leaves the scene)."""
