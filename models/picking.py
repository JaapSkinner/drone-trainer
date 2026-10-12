"""Which object is under the mouse? Ray casting against what is drawn (no GL needed).

A click becomes a ray from the camera through that pixel
(:func:`screen_ray`). Each candidate object is first tested against its
bounding sphere, then against the actual triangles of its draw items, so a
click between a quadcopter's arms falls through to what is behind it.
"""
from typing import Iterable, Optional, Tuple

import numpy as np

from models.render_items import Mesh

_EPS = 1e-9


def screen_ray(camera, x: float, y: float, width: int, height: int) -> Tuple[np.ndarray, np.ndarray]:
    """World-space ray (origin, unit direction) through pixel (x, y) of a width × height view."""
    ndc_x = 2.0 * x / max(1, width) - 1.0
    ndc_y = 1.0 - 2.0 * y / max(1, height)
    view_proj = camera.projection_matrix(width / max(1, height)).astype(float) @ camera.view_matrix().astype(float)
    inverse = np.linalg.inv(view_proj)
    near = inverse @ np.array([ndc_x, ndc_y, -1.0, 1.0])
    far = inverse @ np.array([ndc_x, ndc_y, 1.0, 1.0])
    near, far = near[:3] / near[3], far[:3] / far[3]
    direction = far - near
    return near, direction / np.linalg.norm(direction)


def ray_sphere(origin, direction, centre, radius) -> Optional[float]:
    """Distance along the ray to a sphere (0 if the origin is inside), or None."""
    oc = np.asarray(origin, dtype=float) - np.asarray(centre, dtype=float)
    b = float(np.dot(oc, direction))
    c = float(np.dot(oc, oc)) - radius * radius
    disc = b * b - c
    if disc < 0:
        return None
    root = np.sqrt(disc)
    t = -b - root
    if t < 0:
        t = -b + root
    return t if t >= 0 else (0.0 if c <= 0 else None)


def ray_triangles(origin, direction, triangles: np.ndarray) -> Optional[float]:
    """Nearest hit of a ray on (T, 3, 3) triangles (both sides count), or None (Möller–Trumbore)."""
    if len(triangles) == 0:
        return None
    v0 = triangles[:, 0].astype(float)
    e1 = triangles[:, 1] - v0
    e2 = triangles[:, 2] - v0
    p = np.cross(direction, e2)
    det = np.einsum("ij,ij->i", e1, p)
    ok = np.abs(det) > _EPS
    inv_det = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
    s = origin - v0
    u = np.einsum("ij,ij->i", s, p) * inv_det
    q = np.cross(s, e1)
    v = (q @ direction) * inv_det
    t = np.einsum("ij,ij->i", e2, q) * inv_det
    hit = ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > _EPS)
    if not hit.any():
        return None
    return float(t[hit].min())


def ray_hits_object(obj, origin, direction) -> Optional[float]:
    """Distance along the ray to where it first meets ``obj``'s surface, or None."""
    radius = obj.bounding_radius()
    if radius > 0 and ray_sphere(origin, direction, obj.pose[:3], radius * 1.05) is None:
        return None
    best = None
    for item in obj.draw_items():
        if not isinstance(item.geometry, Mesh):
            continue
        # Into the item's local space; with an unnormalised direction t stays a world distance.
        inverse = np.linalg.inv(item.model.astype(float))
        local_origin = inverse[:3, :3] @ origin + inverse[:3, 3]
        local_direction = inverse[:3, :3] @ direction
        t = ray_triangles(local_origin, local_direction, item.geometry.positions.reshape(-1, 3, 3))
        if t is not None and (best is None or t < best):
            best = t
    return best


def pickable(obj) -> bool:
    """Objects the user can click: visible, and not scene furniture (grid, axes)."""
    return getattr(obj, "rendered", True) and not getattr(obj, "helper", False)


def pick(objects: Iterable, origin, direction):
    """(nearest pickable object hit by the ray, distance), or (None, None)."""
    best, best_t = None, None
    origin = np.asarray(origin, dtype=float)
    direction = np.asarray(direction, dtype=float)
    for obj in objects:
        if not pickable(obj):
            continue
        t = ray_hits_object(obj, origin, direction)
        if t is not None and (best_t is None or t < best_t):
            best, best_t = obj, t
    return best, best_t
