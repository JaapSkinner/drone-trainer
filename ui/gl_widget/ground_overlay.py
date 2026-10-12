"""Ground cues: a soft shadow under each object, a height line from each drone down to the
floor, and a ring on the floor under the selected object (fainter for the one under the mouse).

The shadow sits straight below the object (not cast by the light), so its
position shows where over the floor the object is, and it grows fainter and
wider as the object climbs, which makes height easy to judge.
"""
from typing import List

import numpy as np

from models import mesh_data
from models.gate_frame import GateFrame
from models.picking import pickable
from models.render_items import DrawItem, Lines, Mesh, scale_matrix, translate_scale_matrix
from models.scene_object import SceneObject
from ui import theme

_DISC = Mesh.from_mesh_data(mesh_data.unit_disc(), "shadow disc")
# A band of triangles rather than a wide line: many GL drivers draw every line 1 px wide.
_RING = Mesh.from_mesh_data(mesh_data.unit_annulus(0.84), "selection ring")
_UP = Lines(np.array([(0.0, 0.0, 0.0), (0.0, 1.0, 0.0)], dtype=np.float32), name="height line")

GROUND_LIFT = 0.003      # m: just above the grid so it never z-fights with it
MIN_RADIUS, MAX_RADIUS = 0.08, 1.5
HEIGHT_LINE_FROM = 0.05  # m above the floor before a drone gets a height line


def _is_drone(obj) -> bool:
    return bool(obj.controllable or obj.tracked or obj.mavlink_config.enabled)


def shadow_radius_alpha(footprint: float, height: float, base_alpha: float):
    """Shadow disc radius and opacity for an object ``height`` m above the floor."""
    height = max(0.0, height)
    radius = min(MAX_RADIUS, max(MIN_RADIUS, footprint)) * (1.0 + 0.25 * height)
    return radius, base_alpha / (1.0 + 0.6 * height)


class GroundMarks(SceneObject):
    """The ground cues for one object (drawn as an overlay, never part of the scene)."""

    helper = True

    def __init__(self, obj, highlight=None, shadow_colour=(0, 0, 0, 0.3), line_colour=(0, 0, 0, 0.5),
                 ring_colour=(0, 0, 1, 1), shadow: bool = True):
        super().__init__(None, name=f"{obj.name} ground", shaded=False, controllable=False)
        self.target = obj
        self.update(highlight, shadow_colour, line_colour, ring_colour, shadow)

    def update(self, highlight, shadow_colour, line_colour, ring_colour, shadow: bool = True):
        """Follow the target and this frame's highlight/colours (marks are reused between frames)."""
        x, y, z = (float(v) for v in self.target.pose[:3])
        self.pose = (x, GROUND_LIFT, z, 1.0, 0.0, 0.0, 0.0)
        self.height = y
        self.highlight, self.shadow = highlight, shadow
        self.selected = highlight == "selected"
        self.shadow_colour, self.line_colour, self.ring_colour = shadow_colour, line_colour, ring_colour

    def model_matrix(self) -> np.ndarray:
        # Only ever a translation: cheaper than the general pose matrix.
        m = np.identity(4, dtype=np.float32)
        m[0, 3], m[1, 3], m[2, 3] = self.pose[0], self.pose[1], self.pose[2]
        return m
        self.shadow_colour, self.line_colour, self.ring_colour = shadow_colour, line_colour, ring_colour

    def local_items(self) -> List[DrawItem]:
        items = self._items()
        for item in items:
            item.ground = True
        return items

    def _items(self) -> List[DrawItem]:
        obj, height = self.target, self.height
        footprint = obj.bounding_radius()
        items = []
        if self.shadow and not isinstance(obj, GateFrame):   # a gate is a portal, not something hovering
            radius, alpha = shadow_radius_alpha(footprint, height - 0.5 * footprint, self.shadow_colour[3])
            r, g, b, _ = self.shadow_colour
            items.append(DrawItem(_DISC, scale_matrix(2.0 * radius), (r, g, b, alpha * obj.draw_alpha_scale),
                                  lit=False, falloff=True))
        r, g, b, _ = self.ring_colour
        if height > HEIGHT_LINE_FROM and (_is_drone(obj) or self.highlight):
            colour = (r, g, b, 0.9) if self.selected else self.line_colour
            items.append(DrawItem(_UP, scale_matrix(1.0, height, 1.0), colour, lit=False,
                                  width=2.0 if self.selected else 1.5))
        if self.highlight:
            ring = 2.0 * min(MAX_RADIUS, max(MIN_RADIUS, footprint)) * 1.3
            # A little above the shadow so the (later, translucent) shadow can't dim it.
            place = translate_scale_matrix((0.0, 0.002, 0.0), (ring, 1.0, ring))
            if self.selected:
                items.append(DrawItem(_DISC, place.copy(), (r, g, b, 0.16), lit=False, falloff=True))
                items.append(DrawItem(_RING, place, (r, g, b, 1.0), lit=False))
            else:
                items.append(DrawItem(_RING, translate_scale_matrix((0.0, 0.002, 0.0), (0.92 * ring, 1.0, 0.92 * ring)),
                                      (r, g, b, 0.55), lit=False))
        return items


class GroundOverlay:
    """Viewport overlay (see GLWidget.overlays) producing a GroundMarks for each visible object."""

    def __init__(self, object_service, hovered=None):
        """``hovered()`` returns the object under the mouse (or None)."""
        self.objects = object_service
        self.hovered = hovered or (lambda: None)
        self.enabled = True
        self._marks = {}   # id(object) → GroundMarks, reused while the object exists

    def drawables(self):
        if self.objects is None:
            return []
        selected = self.objects.get_selected_object()
        hovered = self.hovered()
        if not self.enabled and selected is None and hovered is None:
            return []
        shadow, line, ring = theme.rgba("viewport_shadow"), theme.rgba("viewport_height_line"), theme.rgba("accent")
        marks, alive = [], {}
        for obj in self.objects.get_objects():
            if not pickable(obj) or obj.pose[1] < -0.05:
                continue
            highlight = "selected" if obj is selected else "hover" if obj is hovered else None
            if not self.enabled and highlight is None:
                continue
            mark = self._marks.get(id(obj))
            if mark is None or mark.target is not obj:
                mark = GroundMarks(obj)
            mark.update(highlight, shadow, line, ring, shadow=self.enabled)
            alive[id(obj)] = mark
            marks.append(mark)
        self._marks = alive
        return marks
