"""Triangle mesh geometry: loading (STL/OBJ), decimation and primitives.

Meshes are stored as a flat triangle soup — ``positions`` and ``normals`` are
``(3 * triangle_count, 3)`` float32 arrays — which uploads straight into a
vertex buffer and draws with a single ``glDrawArrays(GL_TRIANGLES, ...)``.
Nothing here touches OpenGL.
"""
from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)

# Above this many triangles a loaded mesh is decimated (see CadMesh).
DEFAULT_MAX_TRIANGLES = 50_000

_STL_RECORD = np.dtype([
    ("normal", "<f4", (3,)),
    ("vertices", "<f4", (3, 3)),
    ("attribute", "<u2"),
])


@dataclass
class MeshData:
    positions: np.ndarray  # (3T, 3) float32
    normals: np.ndarray    # (3T, 3) float32

    @property
    def triangle_count(self) -> int:
        return len(self.positions) // 3

    def bounds(self):
        if len(self.positions) == 0:
            return np.zeros(3, np.float32), np.zeros(3, np.float32)
        return self.positions.min(axis=0), self.positions.max(axis=0)


def empty_mesh() -> MeshData:
    return MeshData(np.zeros((0, 3), np.float32), np.zeros((0, 3), np.float32))


def _face_normals(tris: np.ndarray) -> np.ndarray:
    """Unit normals for (T, 3, 3) triangles (counter-clockwise front faces)."""
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    length = np.linalg.norm(n, axis=1, keepdims=True)
    return np.divide(n, length, out=np.zeros_like(n), where=length > 1e-20)


def _from_triangles(tris: np.ndarray, face_normals: np.ndarray = None) -> MeshData:
    tris = np.asarray(tris, dtype=np.float32).reshape(-1, 3, 3)
    computed = _face_normals(tris)
    if face_normals is None:
        normals = computed
    else:
        normals = np.asarray(face_normals, dtype=np.float32).reshape(-1, 3)
        # Many exporters write zero normals; fall back to the geometric normal.
        missing = np.linalg.norm(normals, axis=1) < 1e-6
        normals = np.where(missing[:, None], computed, normals)
    return MeshData(tris.reshape(-1, 3).copy(), np.repeat(normals, 3, axis=0).astype(np.float32))


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_stl(path: str) -> MeshData:
    """Load a binary or ASCII STL file."""
    size = os.path.getsize(path)
    with open(path, "rb") as fh:
        header = fh.read(84)
    if len(header) == 84:
        count = int(np.frombuffer(header[80:84], "<u4")[0])
        if 84 + count * _STL_RECORD.itemsize == size:
            records = np.fromfile(path, dtype=_STL_RECORD, count=count, offset=84)
            return _from_triangles(records["vertices"], records["normal"])
    if header[:5].lower() == b"solid":
        return _load_ascii_stl(path)
    raise ValueError(f"{path}: not a valid STL file")


def _load_ascii_stl(path: str) -> MeshData:
    vertices = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            parts = line.split()
            if parts and parts[0] == "vertex":
                vertices.append([float(v) for v in parts[1:4]])
    if len(vertices) % 3:
        raise ValueError(f"{path}: truncated ASCII STL")
    return _from_triangles(np.array(vertices, dtype=np.float32)) if vertices else empty_mesh()


def load_obj(path: str) -> MeshData:
    """Load an OBJ file. Polygons are fan-triangulated; materials and UVs are ignored."""
    points, normals = [], []
    tri_points, tri_normals = [], []

    def index(token: str, count: int) -> int:
        i = int(token)
        return i - 1 if i > 0 else count + i  # OBJ allows negative (relative) indices

    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            parts = line.split()
            if not parts:
                continue
            if parts[0] == "v":
                points.append([float(v) for v in parts[1:4]])
            elif parts[0] == "vn":
                normals.append([float(v) for v in parts[1:4]])
            elif parts[0] == "f" and len(parts) >= 4:
                corners = []
                for token in parts[1:]:
                    fields = token.split("/")
                    v = index(fields[0], len(points))
                    n = index(fields[2], len(normals)) if len(fields) > 2 and fields[2] else None
                    corners.append((v, n))
                for k in range(1, len(corners) - 1):
                    tri = (corners[0], corners[k], corners[k + 1])
                    tri_points.append([points[v] for v, _ in tri])
                    tri_normals.append([normals[n] if n is not None else None for _, n in tri])

    if not tri_points:
        return empty_mesh()
    tris = np.array(tri_points, dtype=np.float32)
    mesh = _from_triangles(tris)
    # Use the file's per-vertex normals where every corner of a face has one.
    per_vertex = mesh.normals.reshape(-1, 3, 3)
    for i, corner_normals in enumerate(tri_normals):
        if all(n is not None for n in corner_normals):
            per_vertex[i] = corner_normals
    lengths = np.linalg.norm(mesh.normals, axis=1, keepdims=True)
    mesh.normals = np.divide(mesh.normals, lengths, out=mesh.normals, where=lengths > 1e-20)
    return mesh


def load_mesh(path: str) -> MeshData:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".stl":
        return load_stl(path)
    if ext == ".obj":
        return load_obj(path)
    raise ValueError(f"Unsupported mesh format: {path}")


# ---------------------------------------------------------------------------
# Decimation
# ---------------------------------------------------------------------------

def _cluster(positions: np.ndarray, cell: float):
    """Snap vertices to a grid of ``cell``-sized boxes; return (triangles, kept count)."""
    lo = positions.min(axis=0)
    keys = np.floor((positions - lo) / cell).astype(np.int64)
    _, inverse, counts = np.unique(keys, axis=0, return_inverse=True, return_counts=True)
    inverse = inverse.reshape(-1)
    centres = np.zeros((len(counts), 3), np.float64)
    np.add.at(centres, inverse, positions)
    centres /= counts[:, None]

    ids = inverse.reshape(-1, 3)
    keep = (ids[:, 0] != ids[:, 1]) & (ids[:, 1] != ids[:, 2]) & (ids[:, 0] != ids[:, 2])
    ids = ids[keep]
    # Drop duplicate faces created by the collapse (same three clusters).
    if len(ids):
        _, unique_rows = np.unique(np.sort(ids, axis=1), axis=0, return_index=True)
        ids = ids[np.sort(unique_rows)]
    return centres[ids].astype(np.float32), len(ids)


def decimate(mesh: MeshData, max_triangles: int) -> MeshData:
    """Reduce ``mesh`` to at most ``max_triangles`` by vertex clustering.

    Coarse but robust and fast; fine for display meshes. Returns the input
    unchanged when it is already small enough.
    """
    if max_triangles <= 0 or mesh.triangle_count <= max_triangles:
        return mesh
    lo, hi = mesh.bounds()
    diag = float(np.linalg.norm(hi - lo)) or 1.0
    # Binary search the cell size: bigger cells → fewer triangles.
    small, large = diag * 1e-5, diag
    best = None
    for _ in range(24):
        cell = math.sqrt(small * large)
        tris, count = _cluster(mesh.positions, cell)
        if count <= max_triangles:
            best = tris
            large = cell
        else:
            small = cell
        if best is not None and count <= max_triangles and count > 0.9 * max_triangles:
            break
    if best is None or len(best) == 0:
        return mesh
    return _from_triangles(best)


# ---------------------------------------------------------------------------
# Primitives (unit size, centred on the origin)
# ---------------------------------------------------------------------------

def unit_cube() -> MeshData:
    """1×1×1 cube with outward-facing, counter-clockwise triangles."""
    corners = np.array([[x, y, z] for x in (-0.5, 0.5) for y in (-0.5, 0.5) for z in (-0.5, 0.5)],
                       dtype=np.float32)

    def c(x, y, z):
        return corners[(x > 0) * 4 + (y > 0) * 2 + (z > 0)]

    faces = [  # each quad listed counter-clockwise seen from outside
        (c(1, -1, -1), c(1, 1, -1), c(1, 1, 1), c(1, -1, 1)),        # +X
        (c(-1, -1, 1), c(-1, 1, 1), c(-1, 1, -1), c(-1, -1, -1)),    # -X
        (c(-1, 1, -1), c(-1, 1, 1), c(1, 1, 1), c(1, 1, -1)),        # +Y
        (c(-1, -1, 1), c(-1, -1, -1), c(1, -1, -1), c(1, -1, 1)),    # -Y
        (c(-1, -1, 1), c(1, -1, 1), c(1, 1, 1), c(-1, 1, 1)),        # +Z
        (c(1, -1, -1), c(-1, -1, -1), c(-1, 1, -1), c(1, 1, -1)),    # -Z
    ]
    tris = []
    for a, b, cc, d in faces:
        tris.append((a, b, cc))
        tris.append((a, cc, d))
    return _from_triangles(np.array(tris, dtype=np.float32))


def unit_cube_edges() -> np.ndarray:
    """The 12 edges of the unit cube as (24, 3) line-segment endpoints."""
    edges = []
    for axis in range(3):
        for a in (-0.5, 0.5):
            for b in (-0.5, 0.5):
                start = [0.0, 0.0, 0.0]
                others = [i for i in range(3) if i != axis]
                start[others[0]], start[others[1]] = a, b
                end = list(start)
                start[axis], end[axis] = -0.5, 0.5
                edges.extend([start, end])
    return np.array(edges, dtype=np.float32)


def uv_sphere(segments: int = 24, rings: int = 12) -> MeshData:
    """Unit-diameter sphere with smooth per-vertex normals."""
    def point(ring, seg):
        theta = math.pi * ring / rings
        phi = 2.0 * math.pi * seg / segments
        return (math.sin(theta) * math.cos(phi), math.cos(theta), math.sin(theta) * math.sin(phi))

    tris = []
    for r in range(rings):
        for s in range(segments):
            p00, p01 = point(r, s), point(r, s + 1)
            p10, p11 = point(r + 1, s), point(r + 1, s + 1)
            if r != 0:
                tris.append((p00, p01, p10))
            if r != rings - 1:
                tris.append((p01, p11, p10))
    unit = np.array(tris, dtype=np.float32).reshape(-1, 3)
    return MeshData(unit * 0.5, unit.copy())


def unit_disc(segments: int = 40) -> MeshData:
    """Flat disc of diameter 1 in the XZ plane, facing up (+Y)."""
    tris = []
    for s in range(segments):
        a0, a1 = 2.0 * math.pi * s / segments, 2.0 * math.pi * (s + 1) / segments
        # Counter-clockwise seen from above (+Y).
        tris.append(((0.0, 0.0, 0.0), (0.5 * math.cos(a1), 0.0, 0.5 * math.sin(a1)),
                     (0.5 * math.cos(a0), 0.0, 0.5 * math.sin(a0))))
    positions = np.array(tris, dtype=np.float32).reshape(-1, 3)
    normals = np.tile(np.array([0.0, 1.0, 0.0], dtype=np.float32), (len(positions), 1))
    return MeshData(positions, normals)


def unit_circle_segments(segments: int = 64) -> np.ndarray:
    """Circle of diameter 1 in the XZ plane as (2N, 3) line-segment endpoints."""
    points = []
    for s in range(segments):
        for k in (s, s + 1):
            a = 2.0 * math.pi * k / segments
            points.append((0.5 * math.cos(a), 0.0, 0.5 * math.sin(a)))
    return np.array(points, dtype=np.float32)


def unit_annulus(inner: float = 0.86, segments: int = 64) -> MeshData:
    """Flat ring in the XZ plane facing up: outer diameter 1, inner diameter ``inner``."""
    tris = []
    ro, ri = 0.5, 0.5 * inner
    for s in range(segments):
        a0, a1 = 2.0 * math.pi * s / segments, 2.0 * math.pi * (s + 1) / segments
        o0 = (ro * math.cos(a0), 0.0, ro * math.sin(a0))
        o1 = (ro * math.cos(a1), 0.0, ro * math.sin(a1))
        i0 = (ri * math.cos(a0), 0.0, ri * math.sin(a0))
        i1 = (ri * math.cos(a1), 0.0, ri * math.sin(a1))
        tris += [(i0, o1, o0), (i0, i1, o1)]   # counter-clockwise seen from above
    positions = np.array(tris, dtype=np.float32).reshape(-1, 3)
    normals = np.tile(np.array([0.0, 1.0, 0.0], dtype=np.float32), (len(positions), 1))
    return MeshData(positions, normals)
