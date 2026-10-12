import numpy as np

from models.render_items import DrawItem, Lines
from models.scene_object import SceneObject


def dashed_segments(start, end, dash=0.08, gap=0.05) -> np.ndarray:
    """Line-segment endpoints (2N, 3) for a dashed line from ``start`` to ``end``."""
    a, b = np.asarray(start, dtype=float), np.asarray(end, dtype=float)
    length = float(np.linalg.norm(b - a))
    if length < 1e-9:
        return np.zeros((0, 3), np.float32)
    direction = (b - a) / length
    points, s = [], 0.0
    while s < length:
        points += [a + direction * s, a + direction * min(s + dash, length)]
        s += dash + gap
    return np.asarray(points, dtype=np.float32)


class Polyline(SceneObject):
    """Unlit line segments in scene coordinates (for overlays: setpoint lines, paths…)."""

    helper = True

    def __init__(self, segments=None, colour=(0.0, 0.0, 0.0, 1.0), width=2.0, name=None):
        super().__init__(None, name or "Line", shaded=False, controllable=False, colour=colour)
        self.segments = np.asarray(segments if segments is not None else np.zeros((0, 3)), dtype=np.float32)
        self.width = float(width)

    def local_items(self):
        if len(self.segments) == 0:
            return []
        # Usually rebuilt every frame by an overlay, so drawn from memory rather than uploaded.
        if getattr(self, "_lines_source", None) is not self.segments:
            self._lines = Lines(self.segments, name=self.name, static=False)
            self._lines_source = self.segments
        return [DrawItem(self._lines, colour=self.effective_colour(), lit=False, width=self.width)]
