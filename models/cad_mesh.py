import logging
import os
import threading
import weakref

import numpy as np

from models import mesh_data
from models.render_items import DrawItem, Mesh, scale_matrix
from models.scene_object import SceneObject

logger = logging.getLogger(__name__)

# Loaded meshes by (path, file mtime, max_triangles): several drones from the same file share
# one copy in memory and on the GPU. Weak, so a mesh goes once nothing uses it.
_cache = weakref.WeakValueDictionary()
_cache_lock = threading.Lock()


def load_display_mesh(filename, max_triangles=mesh_data.DEFAULT_MAX_TRIANGLES):
    """(Mesh, source triangle count) for ``filename``, decimated for display; shared between callers."""
    try:
        key = (os.path.abspath(filename), os.path.getmtime(filename), int(max_triangles))
    except OSError:
        key = None
    if key is not None:
        with _cache_lock:
            cached = _cache.get(key)
        if cached is not None:
            return cached, cached.source_triangle_count
    try:
        data = mesh_data.load_mesh(filename)
    except (OSError, ValueError) as exc:
        logger.error("Could not load mesh %s: %s", filename, exc)
        data = mesh_data.empty_mesh()
    source_count = data.triangle_count
    if max_triangles and data.triangle_count > max_triangles:
        data = mesh_data.decimate(data, max_triangles)
        logger.warning("Mesh %s has %d triangles; decimated to %d for display.",
                       filename, source_count, data.triangle_count)
    mesh = _DisplayMesh(data.positions, data.normals, os.path.basename(filename))
    mesh.source_triangle_count = source_count
    if key is not None and len(mesh.positions):
        with _cache_lock:
            _cache[key] = mesh
    return mesh, source_count


class _DisplayMesh(Mesh):
    __slots__ = ("source_triangle_count",)


class CadMesh(SceneObject):
    """A triangle mesh loaded from an STL (binary or ASCII) or OBJ file.

    The geometry is uploaded to the GPU once, in model space, and shared by every
    object loaded from the same file; moving the object only changes the matrix it
    is drawn with. Meshes with more than ``max_triangles`` triangles are decimated
    on load so a detailed CAD export can't stall the viewport.

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

        self._geometry, self.source_triangle_count = load_display_mesh(filename, self.max_triangles)
        self.triangle_count = self._geometry.triangle_count
        positions = self._geometry.positions
        self._model_radius = float(np.linalg.norm(positions, axis=1).max()) if len(positions) else 0.0

    @property
    def geometry(self) -> Mesh:
        if self._geometry is None:   # released, then drawn again
            self._geometry, _ = load_display_mesh(self.filename, self.max_triangles)
        return self._geometry

    def bounding_radius(self) -> float:
        return self._model_radius * max(self.scale)

    def local_items(self):
        sx, sy, sz = self.scale
        normal_scale = (1.0, 1.0, 1.0) if sx == sy == sz else (1 / (sx * sx), 1 / (sy * sy), 1 / (sz * sz))
        return [DrawItem(self.geometry, scale_matrix(sx, sy, sz), self.effective_colour(), lit=self.shaded,
                         cull=True, normal_scale=normal_scale)]

    def release_gl(self):
        # Drop this object's reference; the GPU copy goes once no other object uses the mesh.
        self._geometry = None
