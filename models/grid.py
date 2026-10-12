import numpy as np

from models.render_items import DrawItem, Lines
from models.scene_object import SceneObject


DEFAULT_COLOUR = (0.68, 0.68, 0.68, 1.0)


class Grid(SceneObject):
    """Ground grid on the scene's XZ plane (Y up).

    Left at ``DEFAULT_COLOUR`` the viewport draws it in the theme's grid colour.
    """

    helper = True

    def __init__(self, pose=None, name=None, colour=None, controllable=False,
                 half_extent=10, spacing=1.0):
        super().__init__(pose, name or "Unnamed Grid", shaded=False, controllable=False,
                         colour=colour if colour is not None else DEFAULT_COLOUR)
        self.half_extent = int(half_extent)
        self.spacing = float(spacing)
        self._lines = Lines(self._build_lines(), name="grid")

    def _build_lines(self) -> np.ndarray:
        n, s = self.half_extent, self.spacing
        lines = []
        for i in range(-n, n + 1):
            lines += [(i * s, 0.0, -n * s), (i * s, 0.0, n * s)]
            lines += [(-n * s, 0.0, i * s), (n * s, 0.0, i * s)]
        return np.array(lines, dtype=np.float32)

    def local_items(self):
        return [DrawItem(self._lines, colour=self.effective_colour(), lit=False, width=1.0)]
