from OpenGL.GL import (GL_BACK, GL_CULL_FACE, GL_CURRENT_BIT, GL_LIGHTING, GL_LINE_BIT,
                       GL_POLYGON_OFFSET_FILL, glColor4f, glCullFace, glDisable, glEnable,
                       glLineWidth, glPolygonOffset, glPopAttrib, glPushAttrib, glScalef)

from models import mesh_data
from models.gl_buffers import MeshBuffer, draw_lines
from models.scene_object import SceneObject

# Shared geometry for every box (tiny, so kept in client memory).
_CUBE = MeshBuffer(mesh_data.unit_cube(), use_vbo=False)
_CUBE_EDGES = mesh_data.unit_cube_edges()


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

    def _draw(self):
        glScalef(*self.dimensions)
        glPushAttrib(GL_CURRENT_BIT | GL_LINE_BIT)
        try:
            # Push the faces back slightly so the outline never z-fights with them.
            glEnable(GL_POLYGON_OFFSET_FILL)
            glPolygonOffset(1.0, 1.0)
            if self.is_translucent():
                # One see-through layer: hide the far faces of the box.
                glEnable(GL_CULL_FACE)
                glCullFace(GL_BACK)
            glColor4f(*self.colour)
            _CUBE.draw()
            glDisable(GL_CULL_FACE)
            glDisable(GL_POLYGON_OFFSET_FILL)

            if self.edge_colour is not None:
                glDisable(GL_LIGHTING)
                glLineWidth(self.edge_width)
                glColor4f(*self.edge_colour)
                draw_lines(_CUBE_EDGES)
        finally:
            glPopAttrib()
