import numpy as np

from models.render_items import DrawItem, Lines, scale_matrix
from models.scene_object import SceneObject

# X red, Y green, Z blue — one unit long.
_POINTS = np.array([(0, 0, 0), (1, 0, 0), (0, 0, 0), (0, 1, 0), (0, 0, 0), (0, 0, 1)], dtype=np.float32)
_COLOURS = np.array([(1, 0, 0), (1, 0, 0), (0, 1, 0), (0, 1, 0), (0, 0, 1), (0, 0, 1)], dtype=np.float32)
_AXES = Lines(_POINTS, _COLOURS, name="axes")


class Axes(SceneObject):
    """Scene origin axes."""

    helper = True

    def __init__(self, pose=None, name=None, controllable=False, length=1.0):
        super().__init__(pose, name or "Unnamed Axes", shaded=False, controllable=controllable)
        self.length = float(length)

    def local_items(self):
        # Per-vertex colours; only the alpha of the object's colour applies (fading).
        alpha = self.draw_alpha_scale
        return [DrawItem(_AXES, scale_matrix(self.length), (1.0, 1.0, 1.0, alpha), lit=False, width=3.0)]
