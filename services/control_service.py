"""Commanded setpoints for controllable objects (issue #33).

Each controlled object gets a ``ControlState``:

* ``setpoint`` — where the object is commanded to be (drawn as a red ball; what
  gets sent to the vehicle).
* ``ghost`` — in ghost mode, edits go here instead, previewed as a translucent
  ball, until "Send position" commits it to the setpoint.

Objects whose pose comes from motion capture are only *commanded*. Every other
object behaves as a simple simulated vehicle and flies towards its setpoint at
a limited speed, so the Command panel is usable (and testable) without a lab.

Lives on the GUI thread, like ObjectService.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Dict, Optional, Sequence

import numpy as np
from PyQt5.QtCore import QObject, QTimer, pyqtSignal

from models import frames

POSE_EPSILON = 1e-4


def _same_pose(a, b, tol=POSE_EPSILON) -> bool:
    return (max(abs(x - y) for x, y in zip(a[:3], b[:3])) < tol
            and frames.quat_angle(a[3:], b[3:]) < tol)


@dataclass
class ControlState:
    setpoint: tuple
    ghost: tuple

    @property
    def ghost_pending(self) -> bool:
        return not _same_pose(self.setpoint, self.ghost)


class ControlService(QObject):
    setpoints_changed = pyqtSignal(object)   # the object whose setpoint/ghost changed
    ghost_mode_changed = pyqtSignal(bool)

    SIM_SPEED_MPS = 1.5
    SIM_TURN_RATE_RAD_S = math.radians(180)
    TICK_MS = 16

    def __init__(self, object_service=None, simulate=True, parent=None):
        super().__init__(parent)
        self.object_service = object_service
        self.simulate = simulate
        self._ghost_mode = False
        self._states: Dict[object, ControlState] = {}
        self._last_tick = None
        if object_service is not None:
            object_service.object_removed.connect(self.forget)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_timer)
        self._timer.start(self.TICK_MS)

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def ghost_mode(self) -> bool:
        return self._ghost_mode

    def set_ghost_mode(self, enabled: bool):
        if enabled == self._ghost_mode:
            return
        self._ghost_mode = enabled
        # Entering or leaving ghost mode starts from the current setpoint.
        for obj, state in self._states.items():
            state.ghost = state.setpoint
            self.setpoints_changed.emit(obj)
        self.ghost_mode_changed.emit(enabled)

    def state(self, obj) -> Optional[ControlState]:
        return self._states.get(obj)

    def states(self):
        return dict(self._states)

    def ensure_state(self, obj) -> ControlState:
        state = self._states.get(obj)
        if state is None:
            pose = tuple(obj.pose)
            state = self._states[obj] = ControlState(pose, pose)
        return state

    def forget(self, obj):
        self._states.pop(obj, None)

    def setpoint(self, obj) -> tuple:
        return self.ensure_state(obj).setpoint

    def ghost(self, obj) -> tuple:
        return self.ensure_state(obj).ghost

    def target(self, obj) -> tuple:
        """The pose edits apply to: the ghost in ghost mode, else the setpoint."""
        state = self.ensure_state(obj)
        return state.ghost if self._ghost_mode else state.setpoint

    def has_pending_ghost(self, obj) -> bool:
        state = self._states.get(obj)
        return bool(self._ghost_mode and state is not None and state.ghost_pending)

    @staticmethod
    def is_externally_driven(obj) -> bool:
        """True when motion capture moves the object (so we must not)."""
        return bool(obj.tracked and not obj.pose_locked)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    @staticmethod
    def _normalised(pose: Sequence[float]) -> tuple:
        return (*(float(v) for v in pose[:3]), *frames.quat_normalize(pose[3:7]))

    def sync_from_object(self, obj):
        """Make the setpoint (and ghost) the object's current pose."""
        pose = tuple(obj.pose)
        self._states[obj] = ControlState(pose, pose)
        self.setpoints_changed.emit(obj)

    def set_target(self, obj, pose):
        """Set the setpoint — or, in ghost mode, the ghost."""
        pose = self._normalised(pose)
        state = self.ensure_state(obj)
        if self._ghost_mode:
            state.ghost = pose
        else:
            state.setpoint = state.ghost = pose
        self.setpoints_changed.emit(obj)

    def set_setpoint_now(self, obj, pose):
        """Set the setpoint directly, ignoring ghost mode (safety actions such as HOME)."""
        pose = self._normalised(pose)
        state = self.ensure_state(obj)
        state.setpoint = state.ghost = pose
        self.setpoints_changed.emit(obj)

    def move_target(self, obj, delta_position=(0.0, 0.0, 0.0), rotation=None):
        """Shift the target by ``delta_position`` (m) and rotate it by ``rotation``
        (a quaternion applied in the scene frame, e.g. a yaw about +Y)."""
        current = self.target(obj)
        position = tuple(c + d for c, d in zip(current[:3], delta_position))
        q = current[3:]
        if rotation is not None:
            q = frames.quat_multiply(rotation, q)
        self.set_target(obj, (*position, *q))

    def commit_ghost(self, obj) -> tuple:
        """Ghost mode "Send position": the ghost becomes the setpoint."""
        state = self.ensure_state(obj)
        state.setpoint = state.ghost
        self.setpoints_changed.emit(obj)
        return state.setpoint

    # ------------------------------------------------------------------
    # Simulated vehicles
    # ------------------------------------------------------------------

    def _on_timer(self):
        now = time.monotonic()
        dt = 0.0 if self._last_tick is None else min(0.1, now - self._last_tick)
        self._last_tick = now
        self.tick(dt)

    def tick(self, dt: float):
        """Move simulated objects towards their setpoints for ``dt`` seconds."""
        if not self.simulate or dt <= 0:
            return
        for obj, state in list(self._states.items()):
            if self.is_externally_driven(obj):
                continue
            pose, target = obj.pose, state.setpoint
            if _same_pose(pose, target, tol=1e-6):
                continue
            offset = np.asarray(target[:3]) - np.asarray(pose[:3])
            distance = float(np.linalg.norm(offset))
            step = self.SIM_SPEED_MPS * dt
            position = target[:3] if distance <= step else tuple(np.asarray(pose[:3]) + offset * (step / distance))
            angle = frames.quat_angle(pose[3:], target[3:])
            turn = self.SIM_TURN_RATE_RAD_S * dt
            q = target[3:] if angle <= turn else frames.quat_slerp(pose[3:], target[3:], turn / angle)
            obj.set_pose((*position, *q))
