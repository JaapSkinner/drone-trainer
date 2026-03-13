from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Optional
import time


class PositionData:
    def __init__(self, name, x, y, z, x_rot, y_rot, z_rot):
        self.name = name
        self.x = x
        self.y = y
        self.z = z
        self.x_rot = x_rot
        self.y_rot = y_rot
        self.z_rot = z_rot


class MavlinkMessagePriority(Enum):
    """Priority levels for MAVLink messages.
    
    CRITICAL: Motion capture data and emergency commands (highest priority)
    HIGH: Setpoint commands for offboard control
    NORMAL: Standard telemetry and status messages (lowest priority)
    """
    CRITICAL = auto()  # Motion capture, kill commands
    HIGH = auto()      # Setpoints for offboard control
    NORMAL = auto()    # Telemetry (degrades first under bandwidth limits)


@dataclass
class MavlinkConnectionConfig:
    """Configuration for a MAVLink connection.
    
    Attributes:
        connection_string: MAVLink connection string (e.g., 'udpin:0.0.0.0:14550')
        system_id: MAVLink system ID for this connection (1-255)
        component_id: MAVLink component ID (default: 1)
        source_system: Source system ID for outgoing messages
        source_component: Source component ID for outgoing messages
        mocap_topic: Topic name for motion capture data messages
        setpoint_topic: Topic name for setpoint messages
        heartbeat_interval: Interval for sending heartbeats in seconds
        mocap_rate_hz: Target rate for motion capture data in Hz
        name: User-friendly name for this connection (must be unique)
        linked_object_name: Name of the scene object linked to this connection
    """
    connection_string: str
    system_id: int = 1
    component_id: int = 1
    source_system: int = 255
    source_component: int = 0
    mocap_topic: str = "ATT_POS_MOCAP"
    setpoint_topic: str = "SET_POSITION_TARGET_LOCAL_NED"
    heartbeat_interval: float = 1.0
    mocap_rate_hz: float = 100.0
    name: str = ""  # User-friendly name, auto-generated if empty
    linked_object_name: str = ""  # Name of linked scene object


@dataclass
class MavlinkTelemetryData:
    """Container for telemetry data received from a drone.
    
    Attributes:
        timestamp: Time when telemetry was received
        system_id: MAVLink system ID of the source drone
        
        # Attitude data
        roll: Roll angle in radians
        pitch: Pitch angle in radians
        yaw: Yaw angle in radians
        rollspeed: Roll rate in rad/s
        pitchspeed: Pitch rate in rad/s
        yawspeed: Yaw rate in rad/s
        
        # Position data (local NED frame)
        x: X position in meters
        y: Y position in meters
        z: Z position in meters (NED: negative is up)
        vx: X velocity in m/s
        vy: Y velocity in m/s
        vz: Z velocity in m/s
        
        # Status data
        armed: Whether the vehicle is armed
        mode: Current flight mode string
        battery_voltage: Battery voltage in volts
        battery_remaining: Battery remaining percentage (0-100)
        
        # Health indicators
        gps_fix_type: GPS fix type (0=no fix, 3=3D fix)
        satellites_visible: Number of visible GPS satellites
        estimator_status: Estimator status flags
    """
    timestamp: float = field(default_factory=time.time)
    system_id: int = 0
    
    # Attitude
    roll: float = 0.0
    pitch: float = 0.0
    yaw: float = 0.0
    rollspeed: float = 0.0
    pitchspeed: float = 0.0
    yawspeed: float = 0.0
    
    # Position (local NED)
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    vz: float = 0.0
    
    # Status
    armed: bool = False
    mode: str = "UNKNOWN"
    battery_voltage: float = 0.0
    battery_remaining: int = 0
    
    # Health
    gps_fix_type: int = 0
    satellites_visible: int = 0
    estimator_status: int = 0


@dataclass
class MavlinkConnectionStatus:
    """Status information for a MAVLink connection.
    
    Attributes:
        connected: Whether the connection is established
        system_id: System ID of the connected drone
        last_heartbeat: Timestamp of last received heartbeat
        message_rate_hz: Current message receive rate in Hz
        messages_sent: Total messages sent
        messages_received: Total messages received
        latency_ms: Estimated round-trip latency in milliseconds
    """
    connected: bool = False
    system_id: int = 0
    last_heartbeat: float = 0.0
    message_rate_hz: float = 0.0
    messages_sent: int = 0
    messages_received: int = 0
    latency_ms: float = 0.0


@dataclass
class SetpointData:
    """Setpoint data for offboard control.
    
    Attributes:
        x: Target X position in meters (NED frame)
        y: Target Y position in meters (NED frame)
        z: Target Z position in meters (NED frame, negative is up)
        vx: Target X velocity in m/s (optional)
        vy: Target Y velocity in m/s (optional)
        vz: Target Z velocity in m/s (optional)
        yaw: Target yaw angle in radians
        yaw_rate: Target yaw rate in rad/s (optional)
        type_mask: Bitmask indicating which fields are valid
        coordinate_frame: Coordinate frame for the setpoint
    """
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    vx: Optional[float] = None
    vy: Optional[float] = None
    vz: Optional[float] = None
    yaw: float = 0.0
    yaw_rate: Optional[float] = None
    type_mask: int = 0b0000111111111000  # Position + yaw only by default
    coordinate_frame: int = 1  # MAV_FRAME_LOCAL_NED


@dataclass 
class MocapData:
    """Motion capture data to send to the drone.
    
    Attributes:
        x: X position in meters
        y: Y position in meters  
        z: Z position in meters
        q: Quaternion [w, x, y, z] representing orientation
        timestamp_usec: Timestamp in microseconds (0 for auto)
    """
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    q: tuple = (1.0, 0.0, 0.0, 0.0)  # Identity quaternion (w, x, y, z)
    timestamp_usec: int = 0


@dataclass
class MavlinkObjectConfig:
    """MAVLink configuration for an individual scene object.
    
    This config determines how a scene object interacts with MAVLink.
    Objects can send mocap data, receive setpoints, or both.
    
    Attributes:
        enabled: Whether MAVLink is enabled for this object
        connection_string: MAVLink connection string (e.g., 'udpin:0.0.0.0:14550')
        system_id: Target MAVLink system ID (1-255)
        component_id: Target MAVLink component ID (default: 1)
        send_mocap: Whether to stream this object's pose as mocap data
        receive_setpoints: Whether to apply received setpoints to this object
        mocap_rate_hz: Rate to send mocap data (Hz), 0 = use global default
        use_global_connection: If True, use global connection instead of object-specific
        linked_connection_name: Name of the linked MAVLink connection
    """
    enabled: bool = False
    connection_string: str = "udpin:0.0.0.0:14550"
    system_id: int = 1
    component_id: int = 1
    send_mocap: bool = True
    receive_setpoints: bool = False
    mocap_rate_hz: float = 0.0  # 0 = use global default
    use_global_connection: bool = True
    linked_connection_name: str = ""  # Name of linked MAVLink connection


@dataclass
class MavlinkGlobalSettings:
    """Global MAVLink settings that apply to all connections.
    
    These settings are stored in the MavlinkService and can be configured
    via the Settings panel.
    
    Attributes:
        default_connection_string: Default connection string for new objects
        default_mocap_rate_hz: Default motion capture send rate in Hz
        default_setpoint_rate_hz: Default setpoint send rate in Hz
        telemetry_rate_hz: Telemetry receive/process rate in Hz
        heartbeat_interval: Interval for heartbeat messages in seconds
        connection_timeout: Timeout for connection attempts in seconds
        enable_setpoint_sanitization: Enable safety checks on setpoints
        max_position_magnitude: Maximum position setpoint distance in meters
        max_velocity_magnitude: Maximum velocity setpoint in m/s
        max_yaw_rate: Maximum yaw rate in rad/s
        source_system_id: Source system ID for outgoing messages
        source_component_id: Source component ID for outgoing messages
        auto_reconnect: Automatically attempt to reconnect on connection loss
        reconnect_interval: Interval between reconnection attempts in seconds
        auto_connect_discovered: Automatically connect to discovered MAVLink devices
    """
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
    auto_connect_discovered: bool = False  # Auto-connect to discovered devices


# Lookup tables used by DiscoveredDevice (defined outside the class to keep
# the dataclass field ordering simple — no default-after-required issue).
_MAV_TYPE_NAMES: "dict[int, str]" = {
    0:  "Generic",
    1:  "Fixed Wing",
    2:  "Quadrotor",
    3:  "Coaxial Heli",
    4:  "Helicopter",
    5:  "Antenna Tracker",
    6:  "GCS",
    7:  "Airship",
    8:  "Free Balloon",
    9:  "Rocket",
    10: "Ground Rover",
    11: "Surface Boat",
    12: "Submarine",
    13: "Hexarotor",
    14: "Octorotor",
    15: "Tricopter",
    16: "Flapping Wing",
    17: "Kite",
    18: "Onboard Controller",
    19: "VTOL Tailsitter (Duo)",
    20: "VTOL Tailsitter (Quad)",
    21: "VTOL Tiltrotor",
    22: "VTOL Fixed Rotor",
    23: "VTOL Tailsitter",
    24: "VTOL Tiltwing",
    26: "Gimbal",
    27: "ADSB",
    29: "Dodecarotor",
    30: "Camera",
    35: "Decarotor",
}

_MAV_AUTOPILOT_NAMES: "dict[int, str]" = {
    0:  "Generic",
    3:  "ArduPilot",
    4:  "OpenPilot",
    8:  "No Autopilot",
    12: "PX4",
    13: "SMACCMPilot",
    17: "ASLUAV",
    18: "SmartAP",
    20: "Reflex",
}


@dataclass
class DiscoveredDevice:
    """Information about a discovered MAVLink device.

    Attributes:
        address: IP address of the device (source of MAVLink packets)
        port: Port number where device was discovered
        system_id: MAVLink system ID extracted from heartbeat header (0 if unknown)
        component_id: MAVLink component ID extracted from heartbeat header (0 if unknown)
        last_seen: Timestamp when device was last seen
        connection_string: Constructed connection string for connecting

        # Fields decoded from HEARTBEAT payload
        vehicle_type: MAV_TYPE value (e.g. 2=quadrotor, 13=hexarotor).  -1 = unknown.
        autopilot: MAV_AUTOPILOT value (e.g. 12=PX4, 3=ArduPilot).  -1 = unknown.
        armed: Whether the vehicle reported itself as armed in the heartbeat.
        mavlink_version: MAVLink protocol version reported in the heartbeat (1 or 2).
    """
    address: str
    port: int
    system_id: int = 0
    component_id: int = 0
    last_seen: float = field(default_factory=time.time)
    connection_string: str = ""

    # Decoded from HEARTBEAT payload
    vehicle_type: int = -1    # MAV_TYPE (-1 = not decoded)
    autopilot: int = -1       # MAV_AUTOPILOT (-1 = not decoded)
    armed: bool = False
    mavlink_version: int = 0  # 1 or 2

    def __post_init__(self):
        """Generate connection string if not provided."""
        if not self.connection_string:
            self.connection_string = f"udpin:0.0.0.0:{self.port}"

    @property
    def vehicle_type_name(self) -> str:
        """Human-readable vehicle type string."""
        return _MAV_TYPE_NAMES.get(self.vehicle_type, f"Type {self.vehicle_type}")

    @property
    def autopilot_name(self) -> str:
        """Human-readable autopilot string."""
        return _MAV_AUTOPILOT_NAMES.get(self.autopilot, f"Autopilot {self.autopilot}")

    @property
    def display_name(self) -> str:
        """Short human-readable label suitable for a list entry.

        Examples:
            "PX4  Quadrotor  SysID 1  192.168.1.10:14550"
            "ArduPilot  Hexarotor  SysID 3  10.0.0.5:14540  [ARMED]"
        """
        parts = []
        if self.autopilot >= 0:
            parts.append(self.autopilot_name)
        if self.vehicle_type >= 0:
            parts.append(self.vehicle_type_name)
        if self.system_id > 0:
            parts.append(f"SysID {self.system_id}")
        parts.append(f"{self.address}:{self.port}")
        if self.armed:
            parts.append("[ARMED]")
        return "  ".join(parts)

