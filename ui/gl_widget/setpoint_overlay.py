"""Viewport overlay for commanded setpoints and ghost mode (issue #33).

* Setpoint — red ball with a short heading tick (the setpoint's +X / nose).
* Ghost mode — translucent copy of the ball where the pending move is, joined
  to the setpoint by a light dashed line.
* While an object is away from its setpoint, a yellow dashed line joins them.
* When an object overlaps its setpoint it is drawn translucent, so the
  setpoint is always visible.

Shown for the controlled object, and for any other commanded object that
hasn't reached its setpoint yet.
"""
import numpy as np

from models import frames
from models.polyline import Polyline, dashed_segments
from models.sphere import Sphere

SETPOINT_COLOUR = (0.86, 0.10, 0.10, 1.0)
GHOST_ALPHA = 0.35
LINE_COLOUR = (0.85, 0.65, 0.13, 1.0)
GHOST_LINE_COLOUR = (0.86, 0.10, 0.10, 0.45)
BALL_RADIUS = 0.06
HEADING_LENGTH = 0.22
OVERLAP_ALPHA = 0.3


class SetpointOverlay:
    def __init__(self, control_service, object_service):
        self.control = control_service
        self.objects = object_service

    def _distance(self, obj, state):
        return float(np.linalg.norm(np.asarray(obj.pose[:3]) - np.asarray(state.setpoint[:3])))

    def _overlap_distance(self, obj):
        return obj.bounding_radius() + BALL_RADIUS

    def visible_states(self):
        """(object, state) pairs whose setpoint should be drawn."""
        controlled = self.objects.get_controlled_object() if self.objects is not None else None
        for obj, state in self.control.states().items():
            if obj is controlled or self._distance(obj, state) > self._overlap_distance(obj):
                yield obj, state

    def alpha_for(self, obj) -> float:
        """Opacity multiplier for scene objects this frame."""
        state = self.control.state(obj)
        if state is None or not any(o is obj for o, _ in self.visible_states()):
            return 1.0
        return OVERLAP_ALPHA if self._distance(obj, state) < self._overlap_distance(obj) else 1.0

    @staticmethod
    def _ball(pose, alpha=1.0):
        r, g, b, _ = SETPOINT_COLOUR
        ball = Sphere(name="setpoint", radius=BALL_RADIUS, colour=(r, g, b, alpha))
        ball.set_pose((*pose[:3], *frames.IDENTITY_QUAT))
        return ball

    @staticmethod
    def _heading_segment(pose):
        start = np.asarray(pose[:3])
        end = start + HEADING_LENGTH * np.asarray(frames.rotate_vector(pose[3:], (1.0, 0.0, 0.0)))
        return np.asarray([start, end], dtype=np.float32)

    def drawables(self):
        items = []
        for obj, state in self.visible_states():
            items.append(self._ball(state.setpoint))
            items.append(Polyline(self._heading_segment(state.setpoint), SETPOINT_COLOUR, width=3.0))

            if self._distance(obj, state) > self._overlap_distance(obj):
                items.append(Polyline(dashed_segments(obj.pose[:3], state.setpoint[:3]), LINE_COLOUR, width=2.5))

            if self.control.ghost_mode and state.ghost_pending:
                items.append(self._ball(state.ghost, GHOST_ALPHA))
                r, g, b, _ = SETPOINT_COLOUR
                items.append(Polyline(self._heading_segment(state.ghost), (r, g, b, GHOST_ALPHA), width=3.0))
                items.append(Polyline(dashed_segments(state.setpoint[:3], state.ghost[:3], 0.05, 0.05),
                                      GHOST_LINE_COLOUR, width=1.5))
        return items
