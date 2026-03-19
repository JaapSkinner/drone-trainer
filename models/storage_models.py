"""Data models for persistent storage.

Defines the data structures used to serialize/deserialize application
settings and connection configurations to/from JSON storage.
"""

from dataclasses import dataclass, field, asdict, fields
from typing import Optional


@dataclass
class AppSettings:
    """Application-wide settings persisted across sessions.
    
    Covers viewport settings, input configuration, and MAVLink global
    settings.  Stored as a single JSON object (one instance per app).
    
    Attributes:
        zoom_sensitivity: Viewport zoom sensitivity multiplier
        input_type: Active input type name (e.g. "controller", "wasd", "arrow_keys")
        input_sensitivity: Input device sensitivity multiplier

        # MAVLink global settings
        default_connection_string: Default MAVLink connection string
        default_mocap_rate_hz: Default motion capture send rate in Hz
        default_setpoint_rate_hz: Default setpoint send rate in Hz
        telemetry_rate_hz: Telemetry receive/process rate in Hz
        heartbeat_interval: Heartbeat message interval in seconds
        connection_timeout: Connection attempt timeout in seconds
        enable_setpoint_sanitization: Enable safety checks on setpoints
        max_position_magnitude: Maximum position setpoint in meters
        max_velocity_magnitude: Maximum velocity setpoint in m/s
        max_yaw_rate: Maximum yaw rate in rad/s
        source_system_id: Source system ID for outgoing MAVLink messages
        source_component_id: Source component ID for outgoing MAVLink messages
        auto_reconnect: Auto-reconnect on connection loss
        reconnect_interval: Interval between reconnection attempts in seconds
        auto_connect_discovered: Auto-connect to discovered MAVLink devices
        window_geometry: Optional window geometry dict {'x':..,'y':..,'w':..,'h':..}
        active_panel: Tag of the active dock panel at shutdown
        last_locked_object: Name of the object the viewport was locked to (or empty)
        object_mavlink_configs: Mapping of scene object name to minimal MAVLink config dict
    """
    # Viewport
    zoom_sensitivity: float = 1.0

    # Input
    input_type: str = "controller"
    input_sensitivity: float = 1.0

    # MAVLink global settings
    default_connection_string: str = "udpin:0.0.0.0:14550"
    default_mocap_rate_hz: float = 100.0
    default_setpoint_rate_hz: float = 50.0
    telemetry_rate_hz: float = 20.0
    heartbeat_interval: float = 1.0
    connection_timeout: float = 5.0
    enable_setpoint_sanitization: bool = True
    max_position_magnitude: float = 100.0
    max_velocity_magnitude: float = 10.0
    max_yaw_rate: float = 3.14159
    source_system_id: int = 255
    source_component_id: int = 0
    auto_reconnect: bool = True
    reconnect_interval: float = 5.0
    auto_connect_discovered: bool = False

    # UI / session state (new)
    window_geometry: Optional[dict] = None
    active_panel: str = "home"
    last_locked_object: str = ""
    # Camera state to restore viewport on next launch
    camera_distance: float = 10.0
    camera_angle_x: float = 30.0
    camera_angle_y: float = 45.0
    # Sizes for main splitter panes (list of ints) so layout can be restored
    splitter_sizes: Optional[list] = None
    # Additional UI preferences
    window_maximized: bool = False
    ui_theme: str = "default"
    font_point_size: int = 11
    last_active_connection: str = ""
    # Per-object minimal MAVLink configs: { object_name: {enabled: bool, linked_connection_name: str, system_id: int, send_mocap: bool} }
    object_mavlink_configs: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize to a plain dictionary."""
        # Use asdict then prune non-serializable entries if necessary
        data = asdict(self)
        # Ensure None window_geometry becomes null in JSON (allowed)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "AppSettings":
        """Deserialize from a dictionary, ignoring unknown keys."""
        known = {f.name for f in fields(cls)}
        # Copy only known keys
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


@dataclass
class ConnectionEntry:
    """A single MAVLink connection configuration stored persistently.
    
    Multiple entries may exist in storage.  Each entry has a unique *name*
    that acts as its primary key.
    
    Attributes:
        name: Unique user-friendly name for this connection
        connection_string: MAVLink connection string
        system_id: MAVLink system ID (1-255)
        component_id: MAVLink component ID
        source_system: Source system ID for outgoing messages
        source_component: Source component ID for outgoing messages
        heartbeat_interval: Heartbeat interval in seconds
        mocap_rate_hz: Motion capture send rate in Hz
        linked_object_name: Name of the scene object linked to this connection
    """
    name: str
    connection_string: str = "udpin:0.0.0.0:14550"
    system_id: int = 1
    component_id: int = 1
    source_system: int = 255
    source_component: int = 0
    heartbeat_interval: float = 1.0
    mocap_rate_hz: float = 100.0
    linked_object_name: str = ""

    def to_dict(self) -> dict:
        """Serialize to a plain dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ConnectionEntry":
        """Deserialize from a dictionary, ignoring unknown keys."""
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})
