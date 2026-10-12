"""What the renderer draws, without any OpenGL: geometry and draw items.

Scene objects describe themselves as a few :class:`DrawItem` s (geometry, a 4×4
model matrix in the scene frame, a colour and a little state); the renderer in
``ui/gl_widget/scene_renderer.py`` owns every GL call. That keeps objects
testable without a GPU and lets the renderer batch, sort and cache freely.

Geometry is immutable and shared: every box uses the same unit cube, every
quadcopter loaded from the same file the same :class:`Mesh`. The renderer
uploads each piece of ``static`` geometry once and frees it when the geometry
object is garbage collected. Non-static geometry (lines rebuilt every frame)
is drawn straight from memory.
"""
from dataclasses import dataclass, field
from typing import Optional, Sequence, Tuple

import numpy as np

from models import frames

RGBA = Tuple[float, float, float, float]
IDENTITY = np.identity(4, dtype=np.float32)


class Mesh:
    """Triangles in local coordinates: ``positions`` and per-vertex ``normals``, both (3T, 3)."""

    __slots__ = ("positions", "normals", "name", "static", "__weakref__")

    def __init__(self, positions, normals, name: str = "", static: bool = True):
        self.positions = np.ascontiguousarray(positions, dtype=np.float32).reshape(-1, 3)
        self.normals = np.ascontiguousarray(normals, dtype=np.float32).reshape(-1, 3)
        if self.positions.shape != self.normals.shape:
            raise ValueError("positions and normals must have the same shape")
        self.name = name
        self.static = static

    @classmethod
    def from_mesh_data(cls, data, name: str = "", static: bool = True) -> "Mesh":
        return cls(data.positions, data.normals, name, static)

    @property
    def vertex_count(self) -> int:
        return len(self.positions)

    @property
    def triangle_count(self) -> int:
        return len(self.positions) // 3

    def __repr__(self):
        return f"Mesh({self.name or '?'}, {self.triangle_count} triangles)"


class Lines:
    """Line segments: ``positions`` (2N, 3), optionally a colour per vertex ``colours`` (2N, 4)."""

    __slots__ = ("positions", "colours", "name", "static", "__weakref__")

    def __init__(self, positions, colours=None, name: str = "", static: bool = True):
        self.positions = np.ascontiguousarray(positions, dtype=np.float32).reshape(-1, 3)
        if colours is not None:
            colours = np.asarray(colours, dtype=np.float32)
            if colours.shape[1] == 3:
                colours = np.hstack([colours, np.ones((len(colours), 1), np.float32)])
            colours = np.ascontiguousarray(colours)
            if len(colours) != len(self.positions):
                raise ValueError("one colour per vertex")
        self.colours = colours
        self.name = name
        self.static = static

    @property
    def vertex_count(self) -> int:
        return len(self.positions)

    def __repr__(self):
        return f"Lines({self.name or '?'}, {len(self.positions) // 2} segments)"


@dataclass
class DrawItem:
    """One draw call: ``geometry`` placed by ``model`` (row-major 4×4, scene frame)."""

    geometry: object                # Mesh | Lines
    model: np.ndarray = field(default_factory=lambda: IDENTITY)   # never modified in place
    colour: RGBA = (1.0, 1.0, 1.0, 1.0)
    lit: bool = True                # meshes: shaded by the light (False = flat colour)
    cull: bool = False              # meshes: skip back faces (closed surfaces)
    offset: bool = False            # meshes: pushed back in depth so outlines drawn on them win
    width: float = 1.0              # lines: width in pixels
    # Meshes: per-axis factor applied to normals before the model's rotation. (1, 1, 1) is
    # right for rotation with uniform scale, and for axis-aligned normals (boxes) at any
    # scale; a mesh scaled non-uniformly by (sx, sy, sz) needs (1/sx², 1/sy², 1/sz²).
    normal_scale: Tuple[float, float, float] = (1.0, 1.0, 1.0)

    @property
    def translucent(self) -> bool:
        return self.colour[3] < 1.0

    @property
    def is_mesh(self) -> bool:
        return isinstance(self.geometry, Mesh)


# ---------------------------------------------------------------------------
# Matrices (row-major numpy, column vectors: p_world = M @ p_local)
# ---------------------------------------------------------------------------

def pose_matrix(pose: Sequence[float]) -> np.ndarray:
    """Rigid transform for a pose (x, y, z, qw, qx, qy, qz)."""
    m = np.identity(4, dtype=np.float32)
    m[:3, :3] = frames.quat_to_matrix(pose[3:7])
    m[:3, 3] = pose[:3]
    return m


def scale_matrix(sx: float, sy: Optional[float] = None, sz: Optional[float] = None) -> np.ndarray:
    sy = sx if sy is None else sy
    sz = sx if sz is None else sz
    return np.diag(np.array((sx, sy, sz, 1.0), dtype=np.float32))


def translate_scale_matrix(translation, scale) -> np.ndarray:
    m = np.diag(np.array((*scale, 1.0), dtype=np.float32))
    m[:3, 3] = translation
    return m
