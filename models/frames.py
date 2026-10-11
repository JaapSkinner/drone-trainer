"""Coordinate frames and rotation maths.

Every conversion between motion-capture, scene and PX4 frames goes through this
module. Don't hand-roll axis swaps anywhere else.

Frames
------
scene
    The viewport world, and the frame of ``SceneObject.pose``. Right-handed,
    **+Y up**, metres. Orientation is a unit quaternion ``(w, x, y, z)`` that
    rotates body axes into scene axes. At identity a body faces +X with its
    "up" along +Y.
vicon
    Vicon Tracker world as sent by the UDP object stream. Right-handed,
    **+Z up**, millimetres. Rotation arrives as Euler angles in radians
    ``(rx, ry, rz)`` applied about the fixed X, then Y, then Z axes, i.e.
    ``R = Rz(rz) · Ry(ry) · Rx(rx)`` (roll, pitch, yaw).
optitrack
    Motive world as sent over NatNet. Right-handed, metres, quaternion
    ``(qx, qy, qz, qw)``. Up axis is +Y by default (Motive streaming setting
    "Up Axis"); a Z-up mapping is provided too.
ned
    PX4 local frame, North-East-Down, metres. Bodies are FRD.

Axis mappings (all proper rotations — never mirror an axis):

* vicon → scene:  ``(x, y, z) → (x, z, -y)``   (−90° about X)
* scene → ned:    ``(x, y, z) → (x, z, -y)``   (−90° about X)
* hence vicon → ned is ``(x, y, z) → (x, -y, -z)``: Vicon's X axis is treated
  as North, i.e. the standard FLU → FRD conversion.

Which way "North" points in the lab is set by how the Vicon/OptiTrack origin is
calibrated. Verify on hardware before flying (see docs/ROADMAP.md, WP2.1/WP4.3).
"""
from __future__ import annotations

import math
from typing import Sequence, Tuple

import numpy as np

Quat = Tuple[float, float, float, float]          # (w, x, y, z)
Vec3 = Tuple[float, float, float]
Pose = Tuple[float, float, float, float, float, float, float]  # (x, y, z, qw, qx, qy, qz)

IDENTITY_QUAT: Quat = (1.0, 0.0, 0.0, 0.0)
IDENTITY_POSE: Pose = (0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0)


# ---------------------------------------------------------------------------
# Quaternion basics — all quaternions are (w, x, y, z)
# ---------------------------------------------------------------------------

def quat_normalize(q: Sequence[float]) -> Quat:
    w, x, y, z = (float(c) for c in q)
    n = math.sqrt(w * w + x * x + y * y + z * z)
    if n < 1e-12:
        return IDENTITY_QUAT
    return (w / n, x / n, y / n, z / n)


def quat_multiply(a: Sequence[float], b: Sequence[float]) -> Quat:
    """Hamilton product ``a ⊗ b`` (apply ``b`` first, then ``a``)."""
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return (
        w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
        w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
        w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
        w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
    )


def quat_conjugate(q: Sequence[float]) -> Quat:
    w, x, y, z = q
    return (w, -x, -y, -z)


def quat_from_axis_angle(axis: Sequence[float], angle_rad: float) -> Quat:
    ax = np.asarray(axis, dtype=float)
    n = np.linalg.norm(ax)
    if n < 1e-12:
        return IDENTITY_QUAT
    ax = ax / n
    s = math.sin(angle_rad / 2.0)
    return (math.cos(angle_rad / 2.0), ax[0] * s, ax[1] * s, ax[2] * s)


def quat_to_matrix(q: Sequence[float]) -> np.ndarray:
    """3×3 rotation matrix (column vectors) for a unit quaternion."""
    w, x, y, z = quat_normalize(q)
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def matrix_to_quat(m: np.ndarray) -> Quat:
    """Unit quaternion (w ≥ 0) for a 3×3 rotation matrix."""
    m = np.asarray(m, dtype=float)
    trace = m[0, 0] + m[1, 1] + m[2, 2]
    if trace > 0:
        s = 2.0 * math.sqrt(trace + 1.0)
        q = (0.25 * s, (m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s)
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = 2.0 * math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2])
        q = ((m[2, 1] - m[1, 2]) / s, 0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s)
    elif m[1, 1] > m[2, 2]:
        s = 2.0 * math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2])
        q = ((m[0, 2] - m[2, 0]) / s, (m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s)
    else:
        s = 2.0 * math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1])
        q = ((m[1, 0] - m[0, 1]) / s, (m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s)
    q = quat_normalize(q)
    return q if q[0] >= 0 else tuple(-c for c in q)


def rotate_vector(q: Sequence[float], v: Sequence[float]) -> Vec3:
    return tuple(float(c) for c in quat_to_matrix(q) @ np.asarray(v, dtype=float))


def quats_equivalent(a: Sequence[float], b: Sequence[float], tol: float = 1e-6) -> bool:
    """True if two quaternions represent the same rotation (q and -q are equal)."""
    return abs(abs(float(np.dot(quat_normalize(a), quat_normalize(b)))) - 1.0) < tol


def quat_angle(a: Sequence[float], b: Sequence[float]) -> float:
    """Angle (radians, 0..π) of the rotation taking ``a`` to ``b``."""
    d = abs(float(np.dot(quat_normalize(a), quat_normalize(b))))
    return 2.0 * math.acos(min(1.0, d))


def quat_slerp(a: Sequence[float], b: Sequence[float], t: float) -> Quat:
    """Spherical interpolation from ``a`` (t=0) to ``b`` (t=1) the short way round."""
    qa, qb = np.asarray(quat_normalize(a)), np.asarray(quat_normalize(b))
    dot = float(np.dot(qa, qb))
    if dot < 0.0:
        qb, dot = -qb, -dot
    if dot > 0.9995:  # nearly identical: lerp is accurate and avoids dividing by ~0
        return quat_normalize(qa + t * (qb - qa))
    theta = math.acos(dot)
    s = math.sin(theta)
    return quat_normalize((math.sin((1 - t) * theta) / s) * qa + (math.sin(t * theta) / s) * qb)


# ---------------------------------------------------------------------------
# Euler angles — extrinsic X, then Y, then Z (R = Rz · Ry · Rx)
# ---------------------------------------------------------------------------

def euler_xyz_to_quat(rx: float, ry: float, rz: float) -> Quat:
    """Rotation about fixed X by ``rx``, then fixed Y by ``ry``, then fixed Z by ``rz`` (radians)."""
    qx = quat_from_axis_angle((1, 0, 0), rx)
    qy = quat_from_axis_angle((0, 1, 0), ry)
    qz = quat_from_axis_angle((0, 0, 1), rz)
    return quat_normalize(quat_multiply(qz, quat_multiply(qy, qx)))


def quat_to_euler_xyz(q: Sequence[float]) -> Vec3:
    """Inverse of :func:`euler_xyz_to_quat`. ``ry`` is limited to ±90°."""
    m = quat_to_matrix(q)
    ry = math.asin(max(-1.0, min(1.0, -m[2, 0])))
    if abs(m[2, 0]) < 1.0 - 1e-9:
        rx = math.atan2(m[2, 1], m[2, 2])
        rz = math.atan2(m[1, 0], m[0, 0])
    else:  # gimbal lock: fold everything into rz
        rx = 0.0
        rz = math.atan2(-m[0, 1], m[1, 1])
    return (rx, ry, rz)


def euler_deg_to_quat(rx_deg: float, ry_deg: float, rz_deg: float) -> Quat:
    return euler_xyz_to_quat(math.radians(rx_deg), math.radians(ry_deg), math.radians(rz_deg))


def quat_to_euler_deg(q: Sequence[float]) -> Vec3:
    return tuple(math.degrees(a) for a in quat_to_euler_xyz(q))


# ---------------------------------------------------------------------------
# Frame transforms
# ---------------------------------------------------------------------------

class FrameTransform:
    """A fixed rotation from one world frame to another, applied to poses.

    Positions are rotated (and scaled); orientations are re-expressed so that a
    body aligned with the source frame's axes stays aligned with the target's.
    """

    def __init__(self, rotation: np.ndarray, scale: float = 1.0):
        self.rotation = np.asarray(rotation, dtype=float)
        if abs(np.linalg.det(self.rotation) - 1.0) > 1e-9:
            raise ValueError("Frame transforms must be proper rotations (det = +1)")
        self.scale = float(scale)
        self._q = matrix_to_quat(self.rotation)

    def position(self, p: Sequence[float]) -> Vec3:
        return tuple(float(c) for c in self.rotation @ (np.asarray(p, dtype=float) * self.scale))

    def orientation(self, q: Sequence[float]) -> Quat:
        return quat_normalize(quat_multiply(self._q, quat_multiply(q, quat_conjugate(self._q))))

    def pose(self, pose: Sequence[float]) -> Pose:
        return (*self.position(pose[:3]), *self.orientation(pose[3:7]))

    def inverse(self) -> "FrameTransform":
        return FrameTransform(self.rotation.T, 1.0 / self.scale)


# −90° about X: (x, y, z) → (x, z, -y)
_Z_UP_TO_Y_UP = np.array([[1.0, 0.0, 0.0],
                          [0.0, 0.0, 1.0],
                          [0.0, -1.0, 0.0]])

VICON_TO_SCENE = FrameTransform(_Z_UP_TO_Y_UP, scale=0.001)   # millimetres → metres
OPTITRACK_Y_UP_TO_SCENE = FrameTransform(np.eye(3))
OPTITRACK_Z_UP_TO_SCENE = FrameTransform(_Z_UP_TO_Y_UP)
SCENE_TO_NED = FrameTransform(_Z_UP_TO_Y_UP)
NED_TO_SCENE = SCENE_TO_NED.inverse()


def vicon_to_scene_pose(translation_mm: Sequence[float], euler_rad: Sequence[float]) -> Pose:
    """Convert one Vicon UDP object sample to a scene pose."""
    q_vicon = euler_xyz_to_quat(*euler_rad)
    return (*VICON_TO_SCENE.position(translation_mm), *VICON_TO_SCENE.orientation(q_vicon))


def optitrack_to_scene_pose(position_m: Sequence[float], quat_xyzw: Sequence[float],
                            up_axis: str = "y") -> Pose:
    """Convert a NatNet rigid body sample (quaternion in x, y, z, w order) to a scene pose."""
    qx, qy, qz, qw = quat_xyzw
    transform = OPTITRACK_Z_UP_TO_SCENE if up_axis.lower() == "z" else OPTITRACK_Y_UP_TO_SCENE
    return (*transform.position(position_m), *transform.orientation((qw, qx, qy, qz)))


def scene_pose_to_ned(pose: Sequence[float]) -> Tuple[Vec3, Quat]:
    """Split a scene pose into a NED position and an FRD→NED attitude quaternion."""
    return SCENE_TO_NED.position(pose[:3]), SCENE_TO_NED.orientation(pose[3:7])


def ned_to_scene_pose(position_ned: Sequence[float], q_ned: Sequence[float] = IDENTITY_QUAT) -> Pose:
    return (*NED_TO_SCENE.position(position_ned), *NED_TO_SCENE.orientation(q_ned))


def gl_model_matrix(pose: Sequence[float]) -> np.ndarray:
    """4×4 model matrix for a pose, laid out for ``glMultMatrixf`` (column-major)."""
    m = np.identity(4, dtype=np.float32)
    m[:3, :3] = quat_to_matrix(pose[3:7])
    m[:3, 3] = pose[:3]
    return m.T.copy()
