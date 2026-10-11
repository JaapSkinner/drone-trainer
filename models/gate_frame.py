"""Race gate: an upright rectangular frame you fly through.

The opening lies in the gate's local XY plane (local Y is up) and you pass
through along local ±Z. The pose is the centre of the opening.
"""
import numpy as np
from OpenGL.GL import GL_CURRENT_BIT, glColor4f, glPopAttrib, glPopMatrix, glPushAttrib, glPushMatrix, glScalef, glTranslatef

from models import frames
from models.rect_prism import _CUBE
from models.scene_object import SceneObject


class GateFrame(SceneObject):
    def __init__(self, pose=None, name=None, width=1.0, height=1.0, bar=0.06, colour=None,
                 controllable=False):
        super().__init__(pose, name or "Gate", controllable=controllable,
                         colour=colour if colour is not None else (1.0, 0.45, 0.0, 1.0))
        self.width = float(width)     # opening, m
        self.height = float(height)   # opening, m
        self.bar = float(bar)         # frame thickness, m

    def opening_half_extents(self):
        return self.width / 2.0, self.height / 2.0

    def bounding_radius(self) -> float:
        return 0.5 * float(np.hypot(self.width + 2 * self.bar, self.height + 2 * self.bar))

    def _bars(self):
        """(centre, size) of the four bars in local coordinates."""
        w, h, b = self.width, self.height, self.bar
        return [((0.0, (h + b) / 2, 0.0), (w + 2 * b, b, b)),
                ((0.0, -(h + b) / 2, 0.0), (w + 2 * b, b, b)),
                ((-(w + b) / 2, 0.0, 0.0), (b, h, b)),
                (((w + b) / 2, 0.0, 0.0), (b, h, b))]

    def _draw(self):
        glPushAttrib(GL_CURRENT_BIT)
        try:
            glColor4f(*self.effective_colour())
            for centre, size in self._bars():
                glPushMatrix()
                glTranslatef(*centre)
                glScalef(*size)
                _CUBE.draw()
                glPopMatrix()
        finally:
            glPopAttrib()


def gate_crossed(gate, start, end, margin=0.0) -> bool:
    """Did the segment ``start``→``end`` (scene positions) pass through ``gate``?

    Gate frames and boxes count as portals: the path must cross the gate's
    local XY plane inside its opening (box: its X/Y size). Any other object is
    a checkpoint: reaching within its bounding radius counts.
    """
    centre = np.asarray(gate.pose[:3], dtype=float)
    rot = frames.quat_to_matrix(gate.pose[3:])
    if isinstance(gate, GateFrame):
        half_w, half_h = gate.opening_half_extents()
    elif hasattr(gate, "dimensions"):
        half_w, half_h = gate.dimensions[0] / 2.0, gate.dimensions[1] / 2.0
    else:
        return float(np.linalg.norm(np.asarray(end) - centre)) <= gate.bounding_radius() + margin

    a = rot.T @ (np.asarray(start, dtype=float) - centre)
    b = rot.T @ (np.asarray(end, dtype=float) - centre)
    # Crossed when the ends are on opposite sides of the plane (or it ends on it).
    # Distances within 1 µm count as on the plane, so moving along it isn't a crossing.
    za = 0.0 if abs(a[2]) < 1e-6 else a[2]
    zb = 0.0 if abs(b[2]) < 1e-6 else b[2]
    if not (za * zb < 0 or (zb == 0 and za != 0)):
        return False
    t = a[2] / (a[2] - b[2])
    hit = a + t * (b - a)
    return abs(hit[0]) <= half_w + margin and abs(hit[1]) <= half_h + margin
