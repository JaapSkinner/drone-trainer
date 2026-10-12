"""Motion capture calibration: align the mocap world with the lab/scene frame.

A calibration is a rigid transform applied to every mocap pose *after* it has
been converted into the scene frame (models/frames.py)::

    p_cal = R · p + t        q_cal = q_R ⊗ q

It fixes things the mocap system's own calibration doesn't match, e.g. an
origin in the corner of the room instead of the middle of the flying area, or
axes rotated relative to the lab's "forward"/North. Everything downstream —
the viewport, tracked objects and the mocap streamed to PX4 — then uses the
calibrated frame.

Three ways to get one:

* :meth:`MocapCalibration.from_manual` — type in rotations and an offset.
* :func:`solve_origin_direction` — put an object where the origin should be,
  then move it along the desired +X axis. Keeps the vertical axis.
* :func:`solve_reference_points` — capture an object at two or more known
  positions; least-squares fit (yaw-only, or full 3-D with three or more points).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Sequence, Tuple

import numpy as np

from models import frames

Vec3 = Tuple[float, float, float]


class CalibrationError(ValueError):
    """The captured data can't determine a calibration (too few/degenerate points)."""


@dataclass
class MocapCalibration:
    rotation: Tuple[float, float, float, float] = frames.IDENTITY_QUAT  # (w, x, y, z)
    translation: Vec3 = (0.0, 0.0, 0.0)                                 # metres
    method: str = "none"           # how it was obtained (shown in the UI)
    rms_error_m: float = 0.0       # fit residual, for point-based methods

    def __post_init__(self):
        self.rotation = frames.quat_normalize(self.rotation)
        self.translation = tuple(float(v) for v in self.translation)
        self._matrix = frames.quat_to_matrix(self.rotation)
        # Applied to every mocap sample, so precompute (calibrations aren't changed in place).
        self._rows = tuple(tuple(float(v) for v in row) for row in self._matrix)
        self._identity = (frames.quats_equivalent(self.rotation, frames.IDENTITY_QUAT, tol=1e-12)
                          and not any(abs(v) > 1e-12 for v in self.translation))

    # -- applying ----------------------------------------------------------------

    @property
    def is_identity(self) -> bool:
        return self._identity

    def apply_point(self, p: Sequence[float]) -> Vec3:
        x, y, z = (float(c) for c in p)
        return tuple(r0 * x + r1 * y + r2 * z + t for (r0, r1, r2), t in zip(self._rows, self.translation))

    def apply(self, pose: Sequence[float]) -> tuple:
        """Calibrate a scene pose (x, y, z, qw, qx, qy, qz)."""
        if self.is_identity:
            return tuple(pose)
        return (*self.apply_point(pose[:3]),
                *frames.quat_normalize(frames.quat_multiply(self.rotation, pose[3:7])))

    def inverse(self) -> "MocapCalibration":
        q_inv = frames.quat_conjugate(self.rotation)
        t_inv = -(frames.quat_to_matrix(q_inv) @ np.asarray(self.translation))
        return MocapCalibration(q_inv, tuple(t_inv), self.method, self.rms_error_m)

    # -- describing ----------------------------------------------------------------

    def euler_deg(self) -> Vec3:
        """Rotation as extrinsic X, Y (vertical), Z angles in degrees."""
        return frames.quat_to_euler_deg(self.rotation)

    def describe(self) -> str:
        if self.is_identity:
            return "No calibration (mocap frame used as-is)"
        rx, ry, rz = self.euler_deg()
        tx, ty, tz = self.translation
        text = (f"Rotate X {rx:+.1f}°, Y {ry:+.1f}°, Z {rz:+.1f}° · "
                f"offset ({tx:+.3f}, {ty:+.3f}, {tz:+.3f}) m")
        if self.method in ("reference_points", "origin_direction") and self.rms_error_m:
            text += f" · fit error {1000 * self.rms_error_m:.1f} mm RMS"
        return text

    # -- constructing --------------------------------------------------------------

    @classmethod
    def from_manual(cls, rotation_deg: Sequence[float], offset_m: Sequence[float]) -> "MocapCalibration":
        return cls(frames.euler_deg_to_quat(*rotation_deg), tuple(offset_m), "manual")

    def to_dict(self) -> dict:
        return {"rotation": list(self.rotation), "translation": list(self.translation),
                "method": self.method, "rms_error_m": self.rms_error_m}

    @classmethod
    def from_dict(cls, data) -> "MocapCalibration":
        if not data:
            return cls()
        return cls(tuple(data.get("rotation", frames.IDENTITY_QUAT)),
                   tuple(data.get("translation", (0.0, 0.0, 0.0))),
                   str(data.get("method", "manual")),
                   float(data.get("rms_error_m", 0.0)))


def _yaw_rotation(theta: float) -> np.ndarray:
    """Rotation by ``theta`` about the vertical (+Y) axis."""
    c, s = math.cos(theta), math.sin(theta)
    return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])


MIN_DIRECTION_DISTANCE_M = 0.2


def solve_origin_direction(origin: Sequence[float], direction_point: Sequence[float],
                           origin_height_m: float = 0.0) -> MocapCalibration:
    """Calibration from two captured positions (both in the *uncalibrated* scene frame).

    ``origin`` becomes the new origin — at ``origin_height_m`` above the floor
    (the height of the object's tracked point when it sits on the floor) — and
    the horizontal direction from ``origin`` to ``direction_point`` becomes +X.
    The vertical axis is left as the mocap system reports it.
    """
    p0 = np.asarray(origin, dtype=float)
    d = np.asarray(direction_point, dtype=float) - p0
    horizontal = math.hypot(d[0], d[2])
    if horizontal < MIN_DIRECTION_DISTANCE_M:
        raise CalibrationError(
            f"Move the object at least {MIN_DIRECTION_DISTANCE_M:.1f} m horizontally from the origin "
            f"(moved {horizontal:.2f} m).")
    theta = math.atan2(d[2], d[0])
    rot = _yaw_rotation(theta)
    t = np.array([0.0, origin_height_m, 0.0]) - rot @ p0
    return MocapCalibration(frames.matrix_to_quat(rot), tuple(t), "origin_direction")


def _residuals(cal: MocapCalibration, measured: np.ndarray, targets: np.ndarray) -> np.ndarray:
    fitted = np.array([cal.apply_point(p) for p in measured])
    return np.linalg.norm(fitted - targets, axis=1)


@dataclass
class PointFit:
    calibration: MocapCalibration
    residuals_m: List[float] = field(default_factory=list)


def solve_reference_points(measured: Sequence[Sequence[float]], targets: Sequence[Sequence[float]],
                           keep_vertical: bool = True) -> PointFit:
    """Least-squares rigid fit mapping ``measured`` (uncalibrated) onto ``targets``.

    * 1 point: offset only.
    * ``keep_vertical`` (or exactly 2 points): rotation about the vertical axis
      plus offset — right when the mocap system's "up" is already correct.
    * Otherwise (3+ non-collinear points): full 3-D rotation (Kabsch).
    """
    P = np.asarray(measured, dtype=float).reshape(-1, 3)
    Q = np.asarray(targets, dtype=float).reshape(-1, 3)
    if len(P) != len(Q):
        raise CalibrationError("Each captured point needs a target position.")
    if len(P) == 0:
        raise CalibrationError("Capture at least one point.")

    cp, cq = P.mean(axis=0), Q.mean(axis=0)
    Pc, Qc = P - cp, Q - cq

    if len(P) == 1:
        rot = np.identity(3)
    elif keep_vertical or len(P) == 2:
        # Maximise Σ q·(R p) over rotations about +Y (closed form).
        a = float(np.sum(Qc[:, 0] * Pc[:, 0] + Qc[:, 2] * Pc[:, 2]))
        b = float(np.sum(Qc[:, 0] * Pc[:, 2] - Qc[:, 2] * Pc[:, 0]))
        if math.hypot(a, b) < 1e-9:
            raise CalibrationError("The points are too close together horizontally to fix a direction.")
        rot = _yaw_rotation(math.atan2(b, a))
    else:
        h = Pc.T @ Qc
        if np.linalg.matrix_rank(Pc, tol=1e-3) < 2 or np.linalg.matrix_rank(Qc, tol=1e-3) < 2:
            raise CalibrationError("The points are in a line; a full 3-D fit needs three points "
                                   "that form a triangle (or tick “keep vertical axis”).")
        u, _s, vt = np.linalg.svd(h)
        d = np.sign(np.linalg.det(vt.T @ u.T)) or 1.0
        rot = vt.T @ np.diag([1.0, 1.0, d]) @ u.T

    t = cq - rot @ cp
    cal = MocapCalibration(frames.matrix_to_quat(rot), tuple(t), "reference_points")
    residuals = _residuals(cal, P, Q)
    cal.rms_error_m = float(math.sqrt(np.mean(residuals ** 2)))
    return PointFit(cal, [float(r) for r in residuals])
