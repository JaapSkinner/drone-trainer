from models import mesh_data
from models.render_items import DrawItem, Lines, Mesh, scale_matrix
from models.scene_object import SceneObject

# Unit cube (and its 12 edges) shared by every box and gate.
_CUBE = Mesh.from_mesh_data(mesh_data.unit_cube(), "cube")
_CUBE_EDGES = Lines(mesh_data.unit_cube_edges(), name="cube edges")


class RectPrism(SceneObject):
    """A box with optional outlined edges."""

    def __init__(self, pose=None, name=None, dimensions=(1.0, 1.0, 1.0), colour=None,
                 edge_colour=(0.0, 0.0, 0.0), controllable=True):
        super().__init__(pose, name or "Unnamed Rectangular Prism", controllable=controllable,
                         colour=colour)
        self.dimensions = (1.0, 1.0, 1.0)
        self.set_dimensions(dimensions)
        self.edge_colour = self._rgba(edge_colour, (0.0, 0.0, 0.0, 1.0)) if edge_colour else None
        self.edge_width = 3.0

    def set_dimensions(self, dimensions=(1.0, 1.0, 1.0)):
        """Set the (x, y, z) size of the prism, or a single number for a cube."""
        if isinstance(dimensions, (int, float)):
            dimensions = (dimensions, dimensions, dimensions)
        if len(dimensions) != 3:
            raise ValueError("Dimensions must be a number or a tuple of length 3")
        self.dimensions = tuple(float(d) for d in dimensions)

    def bounding_radius(self) -> float:
        return 0.5 * float(sum(d * d for d in self.dimensions)) ** 0.5

    def local_items(self):
        size = scale_matrix(*self.dimensions)
        colour = self.effective_colour()
        # Faces are pushed back slightly so the outline never z-fights with them; a translucent
        # box hides its far faces so it reads as one see-through layer.
        items = [DrawItem(_CUBE, size, colour, lit=self.shaded, cull=colour[3] < 1.0,
                          offset=self.edge_colour is not None)]
        if self.edge_colour is not None:
            r, g, b, a = self.edge_colour
            items.append(DrawItem(_CUBE_EDGES, size.copy(), (r, g, b, a * self.draw_alpha_scale),
                                  lit=False, width=self.edge_width))
        return items
