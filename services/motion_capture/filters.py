"""Optional smoothing for mocap poses.

Position uses the first-order bilinear low-pass from the lab's Vicon interface
(``y = a·y₋₁ + b·(x + x₋₁)``); orientation uses an equivalent exponential
nlerp. Off by default — mocap is usually clean enough for display, and PX4
does its own filtering.
"""
from __future__ import annotations

import math
from typing import Optional

from models import frames


class PoseLowPass:
    def __init__(self, cutoff_hz: float):
        self.cutoff_hz = float(cutoff_hz)
        self._last_raw = None
        self._last_out = None
        self._last_t: Optional[float] = None

    def reset(self):
        self._last_raw = self._last_out = self._last_t = None

    def update(self, pose, t: float):
        """Feed a pose sampled at time ``t`` (seconds); returns the filtered pose."""
        pose = tuple(pose)
        if self._last_t is None or t <= self._last_t or self.cutoff_hz <= 0:
            self._last_raw, self._last_out, self._last_t = pose, pose, t
            return pose
        dt = t - self._last_t
        w = 2.0 * math.pi * self.cutoff_hz
        a = (2.0 - dt * w) / (2.0 + dt * w)
        b = dt * w / (2.0 + dt * w)
        position = tuple(a * yo + b * (x + xo) for x, xo, yo in
                         zip(pose[:3], self._last_raw[:3], self._last_out[:3]))

        alpha = 1.0 - math.exp(-dt * w)
        q_prev, q_new = self._last_out[3:], pose[3:]
        if sum(p * n for p, n in zip(q_prev, q_new)) < 0:  # take the short way round
            q_new = tuple(-c for c in q_new)
        q = frames.quat_normalize([p + alpha * (n - p) for p, n in zip(q_prev, q_new)])

        out = (*position, *q)
        self._last_raw, self._last_out, self._last_t = pose, out, t
        return out
