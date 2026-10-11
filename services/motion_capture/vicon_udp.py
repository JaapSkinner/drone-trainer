"""Vicon Tracker "UDP Object Stream" packets.

Ported from the UoA mocap lab interface by Angus Lynch (``ViconInterface`` on
the ``feature/13-motion-capture-service-refactor-and-optitrack-support``
branch). In Vicon Tracker, enable the UDP object stream and point it at the
IP of the machine running this app.

Packet layout (little-endian)::

    uint32  frame number
    uint8   number of items in this packet
    repeated per item:
        uint8   item id            (0 = object)
        uint16  item data size     (72 for objects)
        bytes   item data
    object item data:
        char[24]   object name, NUL padded
        float64 x3 translation X, Y, Z   (millimetres, Vicon world: Z up)
        float64 x3 rotation X, Y, Z      (radians, Euler XYZ — see models/frames.py)
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import List, Sequence, Tuple

OBJECT_ITEM_ID = 0
NAME_LENGTH = 24
_HEADER = struct.Struct("<IB")
_ITEM_HEADER = struct.Struct("<BH")
_OBJECT_VALUES = struct.Struct("<6d")
OBJECT_DATA_SIZE = NAME_LENGTH + _OBJECT_VALUES.size  # 72


@dataclass
class ViconObject:
    name: str
    translation_mm: Tuple[float, float, float]
    rotation_rad: Tuple[float, float, float]

    @property
    def occluded(self) -> bool:
        # An exactly all-zero sample is treated as "not visible" — that is how
        # occluded objects are expected to arrive. Confirm against the lab
        # system; a real pose is never exactly zero in all six values.
        return not any(self.translation_mm) and not any(self.rotation_rad)


@dataclass
class ViconFrame:
    frame_number: int
    objects: List[ViconObject]


class ViconPacketError(ValueError):
    pass


def parse_packet(data: bytes) -> ViconFrame:
    """Decode one UDP datagram. Unknown item types are skipped."""
    if len(data) < _HEADER.size:
        raise ViconPacketError(f"packet too short ({len(data)} bytes)")
    frame_number, item_count = _HEADER.unpack_from(data, 0)
    offset = _HEADER.size
    objects = []
    for _ in range(item_count):
        if offset + _ITEM_HEADER.size > len(data):
            raise ViconPacketError("truncated item header")
        item_id, size = _ITEM_HEADER.unpack_from(data, offset)
        offset += _ITEM_HEADER.size
        if offset + size > len(data):
            raise ViconPacketError("truncated item data")
        if item_id == OBJECT_ITEM_ID and size >= OBJECT_DATA_SIZE:
            raw_name = data[offset:offset + NAME_LENGTH]
            name = raw_name.split(b"\x00", 1)[0].decode("utf-8", errors="replace").strip()
            values = _OBJECT_VALUES.unpack_from(data, offset + NAME_LENGTH)
            objects.append(ViconObject(name, tuple(values[:3]), tuple(values[3:])))
        offset += size
    return ViconFrame(frame_number, objects)


def build_packet(frame_number: int,
                 objects: Sequence[Tuple[str, Sequence[float], Sequence[float]]]) -> bytes:
    """Encode a packet (for tests and ``scripts/fake_vicon.py``).

    ``objects`` is a sequence of ``(name, translation_mm, rotation_rad)``.
    """
    parts = [_HEADER.pack(frame_number & 0xFFFFFFFF, len(objects))]
    for name, translation, rotation in objects:
        encoded = name.encode("utf-8")[:NAME_LENGTH].ljust(NAME_LENGTH, b"\x00")
        parts.append(_ITEM_HEADER.pack(OBJECT_ITEM_ID, OBJECT_DATA_SIZE))
        parts.append(encoded + _OBJECT_VALUES.pack(*translation, *rotation))
    return b"".join(parts)
