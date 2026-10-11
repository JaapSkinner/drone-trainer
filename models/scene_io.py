"""Scene (de)serialisation: scene objects ↔ plain JSON-compatible dicts.

Each object becomes ``{"type": ..., <common fields>, <type-specific fields>}``.
Unknown keys are ignored on load, and unknown types are skipped with a
warning, so older/newer scene files load as well as they can.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, fields
from typing import Callable, Dict, List, Tuple, Type

from models.axes import Axes
from models.cad_mesh import CadMesh
from models.gate_frame import GateFrame
from models.grid import Grid
from models.rect_prism import RectPrism
from models.scene_object import SceneObject
from models.sphere import Sphere
from models.structs import MavlinkObjectConfig
from services.paths import APP_ROOT

logger = logging.getLogger(__name__)

SCENE_FORMAT_VERSION = 1


def _portable_path(path: str) -> str:
    """Store paths inside the app relative to it, so scenes move between machines."""
    absolute = os.path.abspath(path)
    try:
        rel = os.path.relpath(absolute, APP_ROOT)
    except ValueError:  # different drive on Windows
        return absolute
    return path if rel.startswith("..") else rel.replace(os.sep, "/")


# type name → (class, extra fields → dict, dict → constructor kwargs)
_TYPES: Dict[str, Tuple[Type[SceneObject], Callable, Callable]] = {
    "box": (
        RectPrism,
        lambda o: {"dimensions": list(o.dimensions),
                   "edge_colour": list(o.edge_colour) if o.edge_colour else None},
        lambda d: {"dimensions": tuple(d.get("dimensions", (1, 1, 1))),
                   "edge_colour": d.get("edge_colour", (0, 0, 0))},
    ),
    "sphere": (
        Sphere,
        lambda o: {"radius": o.radius},
        lambda d: {"radius": float(d.get("radius", 0.1))},
    ),
    "mesh": (
        CadMesh,
        lambda o: {"filename": _portable_path(o.filename), "scale": list(o.scale),
                   "max_triangles": o.max_triangles, "shaded": o.shaded},
        lambda d: {"filename": d["filename"], "scale": tuple(d.get("scale", (0.05,) * 3)),
                   "max_triangles": int(d.get("max_triangles", 50_000)),
                   "shaded": bool(d.get("shaded", True))},
    ),
    "gate": (
        GateFrame,
        lambda o: {"width": o.width, "height": o.height, "bar": o.bar},
        lambda d: {"width": float(d.get("width", 1.0)), "height": float(d.get("height", 1.0)),
                   "bar": float(d.get("bar", 0.06))},
    ),
    "grid": (
        Grid,
        lambda o: {"half_extent": o.half_extent, "spacing": o.spacing},
        lambda d: {"half_extent": int(d.get("half_extent", 10)), "spacing": float(d.get("spacing", 1.0))},
    ),
    "axes": (
        Axes,
        lambda o: {"length": o.length},
        lambda d: {"length": float(d.get("length", 1.0))},
    ),
}
_TYPE_BY_CLASS = {cls: name for name, (cls, _, _) in _TYPES.items()}


def type_name(obj: SceneObject) -> str:
    return _TYPE_BY_CLASS.get(type(obj), type(obj).__name__)


def object_to_dict(obj: SceneObject) -> dict:
    name = _TYPE_BY_CLASS.get(type(obj))
    if name is None:
        raise TypeError(f"Don't know how to save {type(obj).__name__}")
    _, extra, _ = _TYPES[name]
    data = {
        "type": name,
        "name": obj.name,
        "pose": list(obj.pose),
        "colour": list(obj.colour),
        "rendered": obj.rendered,
        "controllable": obj.controllable,
        "tracked": obj.tracked,
        "tracking_id": obj.tracking_id,
        "pose_locked": obj.pose_locked,
        "gate_order": obj.gate_order,
        "mavlink": asdict(obj.mavlink_config),
    }
    data.update(extra(obj))
    return data


def object_from_dict(data: dict) -> SceneObject:
    kind = data.get("type")
    if kind not in _TYPES:
        raise ValueError(f"Unknown object type {kind!r}")
    cls, _, kwargs_from = _TYPES[kind]
    obj = cls(name=data.get("name"), **kwargs_from(data))
    if "pose" in data:
        obj.set_pose(data["pose"])
    if data.get("colour") is not None:
        obj.colour = SceneObject._rgba(data["colour"], obj.colour)
    obj.rendered = bool(data.get("rendered", True))
    obj.controllable = bool(data.get("controllable", obj.controllable))
    obj.tracking_id = data.get("tracking_id") or None
    obj.tracked = bool(data.get("tracked", False)) and obj.tracking_id is not None
    obj.pose_locked = bool(data.get("pose_locked", False))
    obj.gate_order = int(data["gate_order"]) if data.get("gate_order") is not None else None
    mav = data.get("mavlink")
    if isinstance(mav, dict):
        known = {f.name for f in fields(MavlinkObjectConfig)}
        obj.mavlink_config = MavlinkObjectConfig(**{k: v for k, v in mav.items() if k in known})
    return obj


def scene_to_dict(objects) -> dict:
    saved = []
    for obj in objects:
        try:
            saved.append(object_to_dict(obj))
        except TypeError as exc:
            logger.warning("Not saving %s: %s", obj.name, exc)
    return {"format": "drone-trainer-scene", "version": SCENE_FORMAT_VERSION, "objects": saved}


def scene_from_dict(data: dict) -> List[SceneObject]:
    items = data.get("objects", []) if isinstance(data, dict) else data
    objects = []
    for item in items or []:
        try:
            objects.append(object_from_dict(item))
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Skipping object %r in scene: %s", item.get("name") if isinstance(item, dict) else item, exc)
    return objects


def save_scene(objects, path: str):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(scene_to_dict(objects), fh, indent=2)
    os.replace(tmp, path)  # never leave a half-written scene behind


def load_scene(path: str) -> List[SceneObject]:
    with open(path, "r", encoding="utf-8") as fh:
        return scene_from_dict(json.load(fh))
