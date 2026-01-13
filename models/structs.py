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
        connection_string: MAVLink connection string (e.g., 'udp:127.0.0.1:14550')
        system_id: MAVLink system ID for this connection (1-255)
        component_id: MAVLink component ID (default: 1)
        source_system: Source system ID for outgoing messages
        source_component: Source component ID for outgoing messages
        mocap_topic: Topic name for motion capture data messages
        setpoint_topic: Topic name for setpoint messages
        heartbeat_interval: Interval for sending heartbeats in seconds
        mocap_rate_hz: Target rate for motion capture data in Hz
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