"""Live data for plotting tools: what is sent and how it is encoded (no Qt, no sockets).

The target is PlotJuggler's **UDP Server** or **WebSocket Server** streaming
plugin with the **JSON** parser (PlotJuggler 3.x and 4.x). Its behaviour, from
the PlotJuggler sources (``plotjuggler_app/nlohmann_parsers.cpp``,
``plotjuggler_plugins/DataStreamUDP/udp_server.cpp``,
``plotjuggler_plugins/DataStreamWebsocket/websocket_server.cpp``):

* UDP: one JSON document per datagram, default port 9870.
  WebSocket: one JSON document per *text* message, default port 9871.
* Nested objects become series named by their path: ``{"a": {"b": 1}}`` is
  the series ``/a/b``. Arrays become ``name[i]``; booleans plot as 0/1;
  strings are ignored.
* The sample time is the arrival time (epoch seconds) unless "use field as
  timestamp if available" is ticked with a field name. We always send
  ``timestamp`` as epoch seconds, so the series line up either way; if one
  message lacked the field PlotJuggler would stop using it for good.

One message per tick carries everything::

    {"timestamp": 1760000000.12,
     "objects":   {"quad1": {"position": {"x":…,"y":…,"z":…}, "ned": {…},
                             "attitude_deg": {"roll":…,"pitch":…,"yaw":…}, "tracked": 1, "mocap_age_s": …}},
     "setpoints": {"quad1": {"position": {…}, "ned": {…}, "yaw_deg": …,
                             "error": {"x":…,"y":…,"z":…,"distance":…}}},
     "mocap":     {"quad1": {"position": {…}, "rate_hz": …, "age_s": …, "visible": 1}},
     "mavlink":   {"quad1": {"attitude_deg": {…}, "rates_dps": {…}, "ned": {…}, "velocity_ned": {…},
                             "battery_v": …, "battery_pct": …, "armed": 0}}}

``position`` is the scene frame (metres, Y up, as in the 3-D view). ``ned`` and
``attitude_deg`` use PX4's convention (North-East-Down, FRD body; roll, pitch,
yaw in degrees), so an object's motion capture and its vehicle's own estimate
plot on the same axes.
"""
import json
import math
from dataclasses import asdict, dataclass, fields
from typing import Dict, Iterable, Optional

from models import frames

DEFAULT_PORTS = {"udp": 9870, "websocket": 9871}
TRANSPORTS = tuple(DEFAULT_PORTS)


@dataclass
class PlotStreamConfig:
    enabled: bool = False
    transport: str = "udp"          # "udp" | "websocket"
    host: str = "127.0.0.1"
    port: int = DEFAULT_PORTS["udp"]
    rate_hz: float = 50.0
    # What to send
    objects: bool = True
    setpoints: bool = True
    motion_capture: bool = True
    mavlink: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "PlotStreamConfig":
        known = {f.name for f in fields(cls)}
        config = cls(**{k: v for k, v in (data or {}).items() if k in known})
        if config.transport not in TRANSPORTS:
            config.transport = "udp"
        config.port = int(config.port)
        config.rate_hz = min(500.0, max(1.0, float(config.rate_hz)))
        return config

    @property
    def address(self) -> str:
        """Where we send, as the user would type it into PlotJuggler."""
        if self.transport == "websocket":
            return f"ws://{self.host}:{self.port}"
        return f"udp://{self.host}:{self.port}"


# ---------------------------------------------------------------------------
# Building a sample
# ---------------------------------------------------------------------------

def series_key(name: str) -> str:
    """A name usable as one level of a PlotJuggler series path ('/' would split it)."""
    key = str(name).strip().replace("/", "_")
    return key or "unnamed"


def _xyz(v) -> dict:
    return {"x": float(v[0]), "y": float(v[1]), "z": float(v[2])}


def _rpy_deg(roll, pitch, yaw) -> dict:
    return {"roll": math.degrees(roll), "pitch": math.degrees(pitch), "yaw": math.degrees(yaw)}


def pose_fields(pose) -> dict:
    """Scene position plus the same pose in PX4's NED/FRD convention."""
    ned, q_ned = frames.scene_pose_to_ned(pose)
    roll, pitch, yaw = frames.quat_to_euler_xyz(q_ned)   # extrinsic X-Y-Z = aerospace yaw-pitch-roll
    return {"position": _xyz(pose[:3]), "ned": _xyz(ned), "attitude_deg": _rpy_deg(roll, pitch, yaw)}


def object_fields(obj, now: Optional[float] = None) -> dict:
    data = pose_fields(obj.pose)
    data["tracked"] = bool(obj.tracked)
    age = obj.tracking_age(now) if obj.tracked else None
    if age is not None:
        data["mocap_age_s"] = age
    return data


def setpoint_fields(obj, state) -> dict:
    setpoint = state.setpoint
    data = pose_fields(setpoint)
    data["yaw_deg"] = data.pop("attitude_deg")["yaw"]
    ex, ey, ez = (float(setpoint[i]) - float(obj.pose[i]) for i in range(3))
    data["error"] = {"x": ex, "y": ey, "z": ez, "distance": math.sqrt(ex * ex + ey * ey + ez * ez)}
    if getattr(state, "ghost_pending", False):
        data["ghost"] = _xyz(state.ghost[:3])
    return data


def subject_fields(info) -> dict:
    return {"position": _xyz(info.pose[:3]), "rate_hz": float(info.rate_hz), "age_s": float(info.age_s),
            "visible": info.age_s <= 1.0}


def telemetry_fields(t) -> dict:
    return {
        "attitude_deg": _rpy_deg(t.roll, t.pitch, t.yaw),
        "rates_dps": {"roll": math.degrees(t.rollspeed), "pitch": math.degrees(t.pitchspeed),
                      "yaw": math.degrees(t.yawspeed)},
        "ned": {"x": t.x, "y": t.y, "z": t.z},
        "velocity_ned": {"x": t.vx, "y": t.vy, "z": t.vz},
        "battery_v": t.battery_voltage,
        "battery_pct": t.battery_remaining,
        "armed": bool(t.armed),
    }


def build_sample(timestamp: float, config: PlotStreamConfig, objects: Iterable = (), control_states=None,
                 subjects: Iterable = (), telemetry: Optional[Dict[str, object]] = None,
                 now: Optional[float] = None) -> dict:
    """One message. ``control_states`` maps object → ControlState; ``telemetry`` maps a vehicle
    name → MavlinkTelemetryData; ``now`` is time.monotonic() for tracking ages."""
    sample = {"timestamp": float(timestamp)}
    objects = [o for o in objects if not getattr(o, "helper", False)]
    if config.objects and objects:
        sample["objects"] = {series_key(o.name): object_fields(o, now) for o in objects}
    if config.setpoints and control_states:
        names = {id(o): o.name for o in objects}
        sample["setpoints"] = {series_key(names.get(id(o), o.name)): setpoint_fields(o, state)
                               for o, state in control_states.items()}
    if config.motion_capture:
        subjects = list(subjects)
        if subjects:
            sample["mocap"] = {series_key(s.name): subject_fields(s) for s in subjects}
    if config.mavlink and telemetry:
        sample["mavlink"] = {series_key(name): telemetry_fields(t) for name, t in telemetry.items()}
    return sample


def _finite(value):
    """Drop NaN/inf (not valid JSON; PlotJuggler's parser would stop the stream)."""
    if isinstance(value, dict):
        return {k: v for k, v in ((k, _finite(v)) for k, v in value.items()) if v is not None}
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def encode(sample: dict) -> bytes:
    """Compact UTF-8 JSON for one message."""
    return json.dumps(_finite(sample), separators=(",", ":"), allow_nan=False).encode("utf-8")
