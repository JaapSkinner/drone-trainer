import logging
import os

import numpy as np

from OpenGL.GL import (GL_BACK, GL_CCW, GL_CULL_FACE, GL_NORMALIZE, glColor4f,
                       glCullFace, glEnable, glFrontFace, glScalef)

from models import mesh_data
from models.gl_buffers import MeshBuffer
from models.scene_object import SceneObject

logger = logging.getLogger(__name__)


class CadMesh(SceneObject):
    """A triangle mesh loaded from an STL (binary or ASCII) or OBJ file.

    The geometry is uploaded to the GPU once, in model space; moving the object
    only changes the matrix it is drawn with. Meshes with more than
    ``max_triangles`` triangles are decimated on load so a detailed CAD export
    can't stall the viewport.

    Args:
        filename: Path to the mesh file (usually under ``cad_files/``).
        name: Object name; defaults to the file name without extension.
        pose: Initial pose.
        scale: Uniform scale or (sx, sy, sz).
        colour: RGB or RGBA colour.
        shaded: Whether lighting is applied.
        max_triangles: Decimation threshold (0 disables decimation).
        controllable: Whether user input may move the object.
    """

    def __init__(self, filename, name=None, pose=None, scale=None, colour=None, shaded=True,
                 max_triangles=mesh_data.DEFAULT_MAX_TRIANGLES, controllable=True):
        if not name:
            name = os.path.splitext(os.path.basename(filename))[0]
        super().__init__(pose, name, shaded=shaded, controllable=controllable, colour=colour)

        self.filename = filename
        if scale is None:
            scale = 0.05
        if isinstance(scale, (int, float)):
            scale = (scale, scale, scale)
        self.scale = tuple(float(s) for s in scale)
        self.max_triangles = int(max_triangles)

        try:
            mesh = mesh_data.load_mesh(filename)
        except (OSError, ValueError) as exc:
            logger.error("Could not load mesh %s: %s", filename, exc)
            mesh = mesh_data.empty_mesh()

        self.source_triangle_count = mesh.triangle_count
        if self.max_triangles and mesh.triangle_count > self.max_triangles:
            mesh = mesh_data.decimate(mesh, self.max_triangles)
            logger.warning("Mesh %s has %d triangles; decimated to %d for display.",
                           filename, self.source_triangle_count, mesh.triangle_count)
        self.triangle_count = mesh.triangle_count
        self._model_radius = (float(np.linalg.norm(mesh.positions, axis=1).max())
                              if len(mesh.positions) else 0.0)
        self._buffer = MeshBuffer(mesh, use_vbo=True)

    def bounding_radius(self) -> float:
        return self._model_radius * max(self.scale)

    def _draw(self):
        glScalef(*self.scale)
        glEnable(GL_NORMALIZE)  # scaling would otherwise distort lighting
        glEnable(GL_CULL_FACE)
        glCullFace(GL_BACK)
        glFrontFace(GL_CCW)
        glColor4f(*self.effective_colour())
        self._buffer.draw()

    def release_gl(self):
        self._buffer.release()
