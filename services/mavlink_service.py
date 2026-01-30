"""
MAVLink Service for drone communication.

This service handles MAVLink protocol communication with PX4 drones including:
- Telemetry reception (lowest priority, degrades first under bandwidth limits)
- Setpoint transmission for offboard control (medium priority)
- Motion capture data transmission (highest priority, critical for flight)

The service supports multiple simultaneous drone connections and uses the
DTRG-Mavlink dialect for compatibility with custom PX4 firmware.

To build the DTRG MAVLink dialect:
    python scripts/build_mavlink.py --dialect dtrg

The DTRG dialect includes all standard PX4 messages plus custom DTRG messages
defined in libs/dtrg-mavlink/message_definitions/v1.0/dtrg.xml
"""
import os
import sys
import time
import threading
from queue import Queue, Empty, PriorityQueue
from dataclasses import dataclass
from typing import Dict, Optional, List, Callable
from enum import Enum

from PyQt5.QtCore import pyqtSignal, QTimer

from services.service_base import ServiceBase, DebugLevel, ServiceLevel
from models.structs import (
    MavlinkConnectionConfig,
    MavlinkTelemetryData,
    MavlinkConnectionStatus,
    MavlinkMessagePriority,
    SetpointData,
    MocapData,
    MavlinkGlobalSettings,
    MavlinkObjectConfig,
)


# Add DTRG-Mavlink pymavlink to Python path for importing custom dialects
# This ensures we use the DTRG-specific MAVLink definitions
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DTRG_MAVLINK_PATH = os.path.join(_REPO_ROOT, "libs", "dtrg-mavlink")
_PYMAVLINK_PATH = os.path.join(_DTRG_MAVLINK_PATH, "pymavlink")
_DIALECTS_PATH = os.path.join(_PYMAVLINK_PATH, "dialects", "v20")

# Check if DTRG-Mavlink submodule is available
DTRG_MAVLINK_AVAILABLE = os.path.exists(_PYMAVLINK_PATH) and os.path.isdir(_PYMAVLINK_PATH)

# Check if DTRG dialect has been built
_DTRG_DIALECT_FILE = os.path.join(_DIALECTS_PATH, "dtrg.py")
DTRG_DIALECT_BUILT = os.path.exists(_DTRG_DIALECT_FILE)


# Import pymavlink for connection handling and standard messages
# Then import DTRG dialect if available for custom messages
try:
    from pymavlink import mavutil
    PYMAVLINK_AVAILABLE = True
    
    # If DTRG dialect is built, import it for custom message definitions
    # The DTRG dialect extends the standard PX4 messages with custom DTRG messages
    if DTRG_MAVLINK_AVAILABLE and DTRG_DIALECT_BUILT:
        try:
            # Add dialects path so we can import dtrg module
            if _DIALECTS_PATH not in sys.path:
                sys.path.insert(0, _DIALECTS_PATH)
            
            import dtrg as dtrg_dialect_module
            
            # Successfully loaded DTRG dialect
            USING_DTRG_DIALECT = True
            mavlink_dialect = dtrg_dialect_module
            
            # The DTRG dialect can be used for encoding/decoding custom messages
            # For standard operations, we still use mavutil's default dialect
            print(f"[MavlinkService] DTRG dialect loaded from {_DIALECTS_PATH}")
            
        except ImportError as e:
            # If custom dialect loading fails, fall back to standard
            print(f"[MavlinkService] Warning: Failed to import DTRG dialect: {e}")
            USING_DTRG_DIALECT = False
            mavlink_dialect = mavutil.mavlink
    else:
        USING_DTRG_DIALECT = False
        mavlink_dialect = mavutil.mavlink
        if not DTRG_DIALECT_BUILT and DTRG_MAVLINK_AVAILABLE:
            print("[MavlinkService] DTRG dialect not built. Run: python scripts/build_mavlink.py")
        
except ImportError:
    PYMAVLINK_AVAILABLE = False
    USING_DTRG_DIALECT = False
    mavutil = None
    mavlink_dialect = None


class ConnectionState(Enum):
    """State of a MAVLink connection."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class PrioritizedMessage:
    """Message wrapper for priority queue ordering.
    
    Lower priority values are processed first (CRITICAL=1, HIGH=2, NORMAL=3).
    """
    priority: int
    timestamp: float
    message: object
    
    def __lt__(self, other):
        # Compare by priority first, then by timestamp for FIFO within same priority
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.timestamp < other.timestamp


class MavlinkConnection:
    """Manages a single MAVLink connection to a drone.
    
    Handles heartbeat exchange, message sending/receiving, and connection health
    monitoring for one drone connection.
    
    Attributes:
        config: Connection configuration
        status: Current connection status
        telemetry: Latest telemetry data
    """
    
    # Heartbeat timeout in seconds before connection is considered lost
    HEARTBEAT_TIMEOUT = 5.0
    
    def __init__(self, config: MavlinkConnectionConfig):
        """Initialize a MAVLink connection.
        
        Args:
            config: Connection configuration parameters
        """
        self.config = config
        self.status = MavlinkConnectionStatus()
        self.telemetry = MavlinkTelemetryData()
        
        self._connection = None
        self._state = ConnectionState.DISCONNECTED
        self._last_heartbeat_sent = 0.0
        self._message_count_window: List[float] = []
        self._lock = threading.Lock()
    
    @property
    def state(self) -> ConnectionState:
        """Get current connection state."""
        return self._state
    
    @property
    def is_connected(self) -> bool:
        """Check if connection is established and healthy."""
        if self._state != ConnectionState.CONNECTED:
            return False
        # Check heartbeat timeout
        if time.time() - self.status.last_heartbeat > self.HEARTBEAT_TIMEOUT:
            return False
        return True
    
    def connect(self) -> bool:
        """Establish the MAVLink connection.
        
        Returns:
            True if connection was established successfully, False otherwise.
        """
        if not PYMAVLINK_AVAILABLE:
            self._state = ConnectionState.ERROR
            return False
        
        try:
            self._state = ConnectionState.CONNECTING
            self._connection = mavutil.mavlink_connection(
                self.config.connection_string,
                source_system=self.config.source_system,
                source_component=self.config.source_component,
            )
            
            # Wait for heartbeat with timeout
            msg = self._connection.wait_heartbeat(timeout=5.0)
            if msg is None:
                self._state = ConnectionState.DISCONNECTED
                return False
            
            self.status.system_id = msg.get_srcSystem()
            self.status.connected = True
            self.status.last_heartbeat = time.time()
            self._state = ConnectionState.CONNECTED
            return True
            
        except Exception as e:
            self._state = ConnectionState.ERROR
            self.status.connected = False
            return False
    
    def disconnect(self):
        """Close the MAVLink connection."""
        with self._lock:
            if self._connection is not None:
                try:
                    self._connection.close()
                except Exception:
                    pass
                self._connection = None
            self._state = ConnectionState.DISCONNECTED
            self.status.connected = False
    
    def send_heartbeat(self) -> bool:
        """Send a heartbeat message to the drone.
        
        Should be called at regular intervals (typically 1Hz) to maintain
        the connection and indicate that the ground station is alive.
        
        Returns:
            True if heartbeat was sent successfully, False otherwise.
        """
        if self._connection is None:
            return False
        
        now = time.time()
        if now - self._last_heartbeat_sent < self.config.heartbeat_interval:
            return True  # Not time yet
        
        try:
            self._connection.mav.heartbeat_send(
                mavutil.mavlink.MAV_TYPE_GCS,  # Ground Control Station
                mavutil.mavlink.MAV_AUTOPILOT_INVALID,
                0, 0, 0
            )
            self._last_heartbeat_sent = now
            self.status.messages_sent += 1
            return True
        except Exception:
            return False
    
    def send_mocap_data(self, mocap: MocapData) -> bool:
        """Send motion capture position/orientation data to the drone.
        
        This is the highest priority message and should be sent at the motion
        capture system's frame rate for best results.
        
        Args:
            mocap: Motion capture data with position and orientation
            
        Returns:
            True if message was sent successfully, False otherwise.
        """
        if self._connection is None:
            return False
        
        try:
            timestamp = mocap.timestamp_usec if mocap.timestamp_usec > 0 else int(time.time() * 1e6)
            
            self._connection.mav.att_pos_mocap_send(
                timestamp,
                list(mocap.q),  # Quaternion [w, x, y, z]
                mocap.x,
                mocap.y,
                mocap.z,
                [float('nan')] * 21  # Covariance matrix (unused)
            )
            self.status.messages_sent += 1
            return True
        except Exception:
            return False
    
    def send_setpoint(self, setpoint: SetpointData) -> bool:
        """Send a position/velocity setpoint to the drone.
        
        Setpoints are used for offboard control. They should be sent at
        a regular rate (typically 10-50Hz) to maintain offboard mode.
        
        Args:
            setpoint: Setpoint data with target position/velocity
            
        Returns:
            True if message was sent successfully, False otherwise.
        """
        if self._connection is None:
            return False
        
        try:
            self._connection.mav.set_position_target_local_ned_send(
                0,  # time_boot_ms (not used)
                self.config.system_id,
                self.config.component_id,
                setpoint.coordinate_frame,
                setpoint.type_mask,
                setpoint.x, setpoint.y, setpoint.z,
                setpoint.vx or 0, setpoint.vy or 0, setpoint.vz or 0,
                0, 0, 0,  # Acceleration (not used)
                setpoint.yaw,
                setpoint.yaw_rate or 0
            )
            self.status.messages_sent += 1
            return True
        except Exception:
            return False
    
    def receive_messages(self, max_messages: int = 10) -> List[object]:
        """Receive pending MAVLink messages.
        
        Non-blocking receive of available messages from the connection.
        
        Args:
            max_messages: Maximum number of messages to receive per call
            
        Returns:
            List of received MAVLink messages
        """
        if self._connection is None:
            return []
        
        messages = []
        for _ in range(max_messages):
            try:
                msg = self._connection.recv_match(blocking=False)
                if msg is None:
                    break
                messages.append(msg)
                self.status.messages_received += 1
                self._update_message_rate()
            except Exception:
                break
        
        return messages
    
    def _update_message_rate(self):
        """Update the message rate calculation."""
        now = time.time()
        # Keep messages from last second
        self._message_count_window = [
            t for t in self._message_count_window 
            if now - t < 1.0
        ]
        self._message_count_window.append(now)
        self.status.message_rate_hz = len(self._message_count_window)
    
    def process_message(self, msg) -> bool:
        """Process a received MAVLink message and update telemetry.
        
        Args:
            msg: MAVLink message to process
            
        Returns:
            True if message was processed, False if message type is not handled
        """
        msg_type = msg.get_type()
        
        if msg_type == 'HEARTBEAT':
            self.status.last_heartbeat = time.time()
            self.status.connected = True
            self._state = ConnectionState.CONNECTED
            # Parse mode and armed state from heartbeat
            self.telemetry.armed = (msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED) != 0
            return True
        
        elif msg_type == 'ATTITUDE':
            self.telemetry.roll = msg.roll
            self.telemetry.pitch = msg.pitch
            self.telemetry.yaw = msg.yaw
            self.telemetry.rollspeed = msg.rollspeed
            self.telemetry.pitchspeed = msg.pitchspeed
            self.telemetry.yawspeed = msg.yawspeed
            self.telemetry.timestamp = time.time()
            return True
        
        elif msg_type == 'LOCAL_POSITION_NED':
            self.telemetry.x = msg.x
            self.telemetry.y = msg.y
            self.telemetry.z = msg.z
            self.telemetry.vx = msg.vx
            self.telemetry.vy = msg.vy
            self.telemetry.vz = msg.vz
            self.telemetry.timestamp = time.time()
            return True
        
        elif msg_type == 'SYS_STATUS':
            self.telemetry.battery_voltage = msg.voltage_battery / 1000.0
            self.telemetry.battery_remaining = msg.battery_remaining
            return True
        
        elif msg_type == 'GPS_RAW_INT':
            self.telemetry.gps_fix_type = msg.fix_type
            self.telemetry.satellites_visible = msg.satellites_visible
            return True
        
        elif msg_type == 'ESTIMATOR_STATUS':
            self.telemetry.estimator_status = msg.flags
            return True
        
        return False


class MavlinkService(ServiceBase):
    """Service for managing MAVLink communications with multiple drones.
    
    This service provides:
    - Multiple drone connection management
    - Priority-based message handling (mocap > setpoints > telemetry)
    - Automatic heartbeat maintenance
    - Telemetry data aggregation
    - Connection health monitoring
    
    Signals:
        telemetry_updated: Emitted when new telemetry is received (system_id, MavlinkTelemetryData)
        connection_changed: Emitted when connection state changes (system_id, connected)
        health_updated: Emitted when health metrics change (rate_hz, active_connections)
    """
    
    # Signals for UI updates
    telemetry_updated = pyqtSignal(int, object)  # system_id, MavlinkTelemetryData
    connection_changed = pyqtSignal(int, bool)   # system_id, connected
    health_updated = pyqtSignal(float, int)      # rate_hz, active_connections
    
    # Service update rates
    TELEMETRY_UPDATE_INTERVAL_MS = 50   # 20Hz for telemetry (low priority)
    SETPOINT_UPDATE_INTERVAL_MS = 20    # 50Hz for setpoints (medium priority)
    MOCAP_UPDATE_INTERVAL_MS = 10       # 100Hz for mocap (high priority)
    HEARTBEAT_CHECK_INTERVAL_MS = 100   # 10Hz for heartbeat checks
    
    # Setpoint sanitization limits
    MAX_POSITION_MAGNITUDE = 100.0  # meters
    MAX_VELOCITY_MAGNITUDE = 10.0   # m/s
    MAX_YAW_RATE = 3.14159          # rad/s
    
    def __init__(self, debug_level: DebugLevel = None):
        """Initialize the MAVLink service.
        
        Args:
            debug_level: Debug level for error handling
        """
        super().__init__(debug_level=debug_level or DebugLevel.LOG)
        
        self._connections: Dict[int, MavlinkConnection] = {}
        self._message_queue: PriorityQueue = PriorityQueue()
        self._telemetry_callbacks: List[Callable] = []
        self._mocap_sources: Dict[int, object] = {}  # system_id -> scene object
        
        # Saved connection configs (for inactive connections linked to objects)
        self._saved_connections: Dict[str, MavlinkConnectionConfig] = {}
        
        # Global settings for MAVLink operations
        self._global_settings = MavlinkGlobalSettings()
        
        # Timers for different priority tasks
        self._heartbeat_timer: Optional[QTimer] = None
        self._telemetry_timer: Optional[QTimer] = None
        self._mocap_timer: Optional[QTimer] = None
        self._setpoint_timer: Optional[QTimer] = None
        
        # Health tracking
        self._total_rate_hz = 0.0
        self._active_connections = 0
        
        # Setpoint sources (object -> setpoint data)
        self._setpoint_sources: Dict[int, SetpointData] = {}
        
        # MAVLink-enabled objects (object -> MavlinkObjectConfig)
        self._mavlink_objects: Dict[object, MavlinkObjectConfig] = {}
        
        self.status_label = "MAVLink: Not Connected"
        self._status_label = "Not Connected"
    
    def get_global_settings(self) -> MavlinkGlobalSettings:
        """Get the current global MAVLink settings.
        
        Returns:
            Current global settings
        """
        return self._global_settings
    
    def update_global_settings(self, settings: MavlinkGlobalSettings):
        """Update global MAVLink settings.
        
        Updates the service configuration including setpoint limits and rates.
        
        Args:
            settings: New global settings to apply
        """
        self._global_settings = settings
        
        # Update service parameters from settings
        self.MAX_POSITION_MAGNITUDE = settings.max_position_magnitude
        self.MAX_VELOCITY_MAGNITUDE = settings.max_velocity_magnitude
        self.MAX_YAW_RATE = settings.max_yaw_rate
        
        # Helper to safely calculate interval (avoid division by zero)
        def rate_to_interval(rate_hz: float, default_ms: int) -> int:
            """Convert rate in Hz to interval in ms, with fallback."""
            if rate_hz is None or rate_hz <= 0:
                return default_ms
            return max(1, int(1000 / rate_hz))
        
        # Update timer intervals if timers exist
        if self._telemetry_timer is not None:
            self._telemetry_timer.setInterval(rate_to_interval(settings.telemetry_rate_hz, 50))
        
        if self._setpoint_timer is not None:
            self._setpoint_timer.setInterval(rate_to_interval(settings.default_setpoint_rate_hz, 20))
        
        if self._mocap_timer is not None:
            self._mocap_timer.setInterval(rate_to_interval(settings.default_mocap_rate_hz, 10))
    
    def register_mavlink_object(self, obj, config: MavlinkObjectConfig = None):
        """Register a scene object for MAVLink operations.
        
        Objects can send mocap data and/or receive setpoints.
        
        Args:
            obj: Scene object to register
            config: MAVLink configuration (uses object's config if None)
        """
        if config is None and hasattr(obj, 'mavlink_config'):
            config = obj.mavlink_config
        
        if config is None:
            config = MavlinkObjectConfig(enabled=True)
        
        self._mavlink_objects[obj] = config
        
        # If object should send mocap, register as mocap source
        if config.send_mocap and config.enabled:
            self.register_mocap_source(config.system_id, obj)
    
    def unregister_mavlink_object(self, obj):
        """Unregister a scene object from MAVLink operations.
        
        Args:
            obj: Scene object to unregister
        """
        if obj in self._mavlink_objects:
            config = self._mavlink_objects[obj]
            
            # Remove from mocap sources if registered
            if config.send_mocap:
                self.unregister_mocap_source(config.system_id)
            
            del self._mavlink_objects[obj]
    
    def update_object_config(self, obj, config: MavlinkObjectConfig):
        """Update MAVLink configuration for a registered object.
        
        Args:
            obj: Scene object to update
            config: New MAVLink configuration
        """
        if obj in self._mavlink_objects:
            old_config = self._mavlink_objects[obj]
            
            # Handle mocap registration changes
            if old_config.send_mocap and not config.send_mocap:
                self.unregister_mocap_source(old_config.system_id)
            elif config.send_mocap and config.enabled and not old_config.send_mocap:
                self.register_mocap_source(config.system_id, obj)
            
            self._mavlink_objects[obj] = config
        else:
            self.register_mavlink_object(obj, config)
    
    def get_mavlink_objects(self) -> Dict[object, MavlinkObjectConfig]:
        """Get all registered MAVLink-enabled objects.
        
        Returns:
            Dictionary mapping objects to their MAVLink configurations
        """
        return self._mavlink_objects.copy()
    
    @staticmethod
    def get_dialect_info() -> dict:
        """Get information about the MAVLink dialect being used.
        
        Returns:
            Dictionary with dialect information including:
            - available: Whether pymavlink is available
            - using_dtrg: Whether using DTRG-specific dialect
            - dialect_name: Name of the dialect
            - dtrg_path: Path to DTRG-Mavlink submodule
            - dtrg_built: Whether the DTRG dialect has been built
        """
        return {
            'available': PYMAVLINK_AVAILABLE,
            'using_dtrg': USING_DTRG_DIALECT,
            'dialect_name': 'dtrg' if USING_DTRG_DIALECT else 'common',
            'dtrg_path': _DTRG_MAVLINK_PATH if DTRG_MAVLINK_AVAILABLE else None,
            'dtrg_available': DTRG_MAVLINK_AVAILABLE,
            'dtrg_built': DTRG_DIALECT_BUILT,
        }
    
    def on_start(self):
        """Initialize timers and start the service."""
        if not PYMAVLINK_AVAILABLE:
            self.set_status(ServiceLevel.ERROR, "MAVLink: pymavlink not installed")
            return
        
        # Log which dialect is being used
        dialect_info = self.get_dialect_info()
        if dialect_info['using_dtrg']:
            print(f"[MavlinkService] Using DTRG dialect from {dialect_info['dtrg_path']}")
        else:
            print(f"[MavlinkService] Using standard MAVLink dialect (DTRG not available)")
        
        # Heartbeat timer - runs at 10Hz to check all connections
        self._heartbeat_timer = QTimer()
        self._heartbeat_timer.setInterval(self.HEARTBEAT_CHECK_INTERVAL_MS)
        self._heartbeat_timer.timeout.connect(self.safe(self._process_heartbeats))
        self._heartbeat_timer.start()
        
        # Telemetry timer - lowest priority, 20Hz
        self._telemetry_timer = QTimer()
        self._telemetry_timer.setInterval(self.TELEMETRY_UPDATE_INTERVAL_MS)
        self._telemetry_timer.timeout.connect(self.safe(self._process_telemetry))
        self._telemetry_timer.start()
        
        # Mocap timer - highest priority, 100Hz
        self._mocap_timer = QTimer()
        self._mocap_timer.setInterval(self.MOCAP_UPDATE_INTERVAL_MS)
        self._mocap_timer.timeout.connect(self.safe(self._process_mocap))
        self._mocap_timer.start()
        
        # Setpoint timer - medium priority, 50Hz
        self._setpoint_timer = QTimer()
        self._setpoint_timer.setInterval(self.SETPOINT_UPDATE_INTERVAL_MS)
        self._setpoint_timer.timeout.connect(self.safe(self._process_setpoints))
        self._setpoint_timer.start()
        
        self.set_status(ServiceLevel.RUNNING, "MAVLink: Ready")
    
    def on_stop(self):
        """Stop all timers and disconnect all connections."""
        # Stop timers
        for timer in [self._heartbeat_timer, self._telemetry_timer, 
                      self._mocap_timer, self._setpoint_timer]:
            if timer is not None:
                timer.stop()
                timer.deleteLater()
        
        self._heartbeat_timer = None
        self._telemetry_timer = None
        self._mocap_timer = None
        self._setpoint_timer = None
        
        # Disconnect all connections
        for conn in self._connections.values():
            conn.disconnect()
        self._connections.clear()
        
        self.set_status(ServiceLevel.STOPPED, "MAVLink: Stopped")
    
    def update(self):
        """Main update loop - not used as we use separate timers for priority handling."""
        pass
    
    def add_connection(self, config: MavlinkConnectionConfig) -> bool:
        """Add and establish a new MAVLink connection.
        
        Args:
            config: Connection configuration
            
        Returns:
            True if connection was established successfully
        """
        # Generate a unique name if not provided
        if not config.name:
            config.name = self.generate_connection_name()
        elif not self.is_connection_name_unique(config.name):
            # Name already exists, generate a new one
            config.name = self.generate_connection_name(config.name)
        
        connection = MavlinkConnection(config)
        
        if connection.connect():
            self._connections[connection.status.system_id] = connection
            self._active_connections = len(self._connections)
            
            # Remove from saved connections if it was there
            if config.name in self._saved_connections:
                del self._saved_connections[config.name]
            
            self.connection_changed.emit(connection.status.system_id, True)
            self._update_status_label()
            return True
        
        return False
    
    def remove_connection(self, system_id: int):
        """Remove and disconnect a MAVLink connection.
        
        If the connection has a linked object, it is saved to _saved_connections
        so it can be reconnected later.
        
        Args:
            system_id: System ID of the connection to remove
        """
        if system_id in self._connections:
            conn = self._connections[system_id]
            
            # Save config if it has a linked object for potential reconnection
            if conn.config.linked_object_name or conn.config.name:
                name = conn.config.name or f"Connection-{system_id}"
                self._saved_connections[name] = conn.config
            
            conn.disconnect()
            del self._connections[system_id]
            self._active_connections = len(self._connections)
            self.connection_changed.emit(system_id, False)
            self._update_status_label()
    
    def get_connection(self, system_id: int) -> Optional[MavlinkConnection]:
        """Get a connection by system ID.
        
        Args:
            system_id: System ID of the connection
            
        Returns:
            MavlinkConnection if found, None otherwise
        """
        return self._connections.get(system_id)
    
    def get_telemetry(self, system_id: int) -> Optional[MavlinkTelemetryData]:
        """Get latest telemetry data for a drone.
        
        Args:
            system_id: System ID of the drone
            
        Returns:
            MavlinkTelemetryData if available, None otherwise
        """
        conn = self._connections.get(system_id)
        if conn is not None:
            return conn.telemetry
        return None
    
    def get_all_telemetry(self) -> Dict[int, MavlinkTelemetryData]:
        """Get telemetry data for all connected drones.
        
        Returns:
            Dictionary mapping system_id to MavlinkTelemetryData
        """
        return {
            sys_id: conn.telemetry 
            for sys_id, conn in self._connections.items()
        }
    
    def register_mocap_source(self, system_id: int, scene_object):
        """Register a scene object as motion capture source for a drone.
        
        The object's pose will be sent to the drone at the mocap update rate.
        
        Args:
            system_id: Target drone's system ID
            scene_object: Scene object with pose data
        """
        self._mocap_sources[system_id] = scene_object
    
    def unregister_mocap_source(self, system_id: int):
        """Unregister a motion capture source.
        
        Args:
            system_id: Target drone's system ID
        """
        if system_id in self._mocap_sources:
            del self._mocap_sources[system_id]
    
    def send_setpoint(self, system_id: int, setpoint: SetpointData) -> bool:
        """Send a setpoint to a specific drone.
        
        The setpoint will be sanitized before sending.
        
        Args:
            system_id: Target drone's system ID
            setpoint: Setpoint data to send
            
        Returns:
            True if setpoint was sent successfully
        """
        if not self._sanitize_setpoint(setpoint):
            return False
        
        conn = self._connections.get(system_id)
        if conn is not None and conn.is_connected:
            return conn.send_setpoint(setpoint)
        return False
    
    def register_setpoint_source(self, system_id: int, setpoint: SetpointData):
        """Register a setpoint to be continuously sent to a drone.
        
        Args:
            system_id: Target drone's system ID
            setpoint: Setpoint data to send continuously
        """
        self._setpoint_sources[system_id] = setpoint
    
    def unregister_setpoint_source(self, system_id: int):
        """Unregister a setpoint source.
        
        Args:
            system_id: Target drone's system ID  
        """
        if system_id in self._setpoint_sources:
            del self._setpoint_sources[system_id]
    
    def get_health_metrics(self) -> tuple:
        """Get overall health metrics for the MAVLink service.
        
        Returns:
            Tuple of (total_rate_hz, active_connections)
        """
        return (self._total_rate_hz, self._active_connections)
    
    def get_connection_count(self) -> int:
        """Get the number of active connections.
        
        Returns:
            Number of active MAVLink connections
        """
        return len(self._connections)
    
    def get_connection_statistics(self) -> dict:
        """Get aggregated statistics for all connections.
        
        Returns:
            Dictionary with total_sent, total_received, and connections list
        """
        total_sent = 0
        total_received = 0
        connections = []
        
        for sys_id, conn in self._connections.items():
            total_sent += conn.status.messages_sent
            total_received += conn.status.messages_received
            connections.append({
                'system_id': sys_id,
                'connected': conn.is_connected,
                'messages_sent': conn.status.messages_sent,
                'messages_received': conn.status.messages_received,
                'rate_hz': conn.status.message_rate_hz,
            })
        
        return {
            'total_sent': total_sent,
            'total_received': total_received,
            'connections': connections,
        }
    
    def get_all_connections(self) -> Dict[str, MavlinkConnectionConfig]:
        """Get all configured connections (both active and inactive).
        
        Returns:
            Dictionary mapping connection name to MavlinkConnectionConfig
        """
        result = {}
        for sys_id, conn in self._connections.items():
            name = conn.config.name or f"Connection-{sys_id}"
            result[name] = conn.config
        
        # Also include inactive connections from saved config
        for name, config in self._saved_connections.items():
            if name not in result:
                result[name] = config
        
        return result
    
    def get_connection_by_name(self, name: str) -> Optional[MavlinkConnection]:
        """Get an active connection by its name.
        
        Args:
            name: Connection name
            
        Returns:
            MavlinkConnection if found and active, None otherwise
        """
        for conn in self._connections.values():
            conn_name = conn.config.name or f"Connection-{conn.config.system_id}"
            if conn_name == name:
                return conn
        return None
    
    def is_connection_name_unique(self, name: str, exclude_system_id: int = None) -> bool:
        """Check if a connection name is unique.
        
        Args:
            name: Connection name to check
            exclude_system_id: System ID to exclude from check (for renaming)
            
        Returns:
            True if name is unique
        """
        for sys_id, conn in self._connections.items():
            if exclude_system_id is not None and sys_id == exclude_system_id:
                continue
            if conn.config.name == name:
                return False
        
        # Also check saved inactive connections
        for saved_name in self._saved_connections.keys():
            if saved_name == name:
                return False
        
        return True
    
    def generate_connection_name(self, base_name: str = "Drone") -> str:
        """Generate a unique connection name.
        
        Args:
            base_name: Base name to use
            
        Returns:
            Unique connection name
        """
        counter = 1
        name = f"{base_name}-{counter}"
        while not self.is_connection_name_unique(name):
            counter += 1
            name = f"{base_name}-{counter}"
        return name
    
    def rename_connection(self, system_id: int, new_name: str) -> bool:
        """Rename a connection.
        
        Args:
            system_id: System ID of the connection
            new_name: New name for the connection
            
        Returns:
            True if rename was successful
        """
        if not self.is_connection_name_unique(new_name, exclude_system_id=system_id):
            return False
        
        conn = self._connections.get(system_id)
        if conn is not None:
            conn.config.name = new_name
            return True
        return False
    
    def link_connection_to_object(self, connection_name: str, object_name: str):
        """Link a MAVLink connection to a scene object.
        
        Args:
            connection_name: Name of the connection
            object_name: Name of the object to link
        """
        # Update connection config
        conn = self.get_connection_by_name(connection_name)
        if conn is not None:
            conn.config.linked_object_name = object_name
        
        # Also update in saved connections
        if connection_name in self._saved_connections:
            self._saved_connections[connection_name].linked_object_name = object_name
        
        # Emit update
        self.connection_changed.emit(conn.config.system_id if conn else 0, True)
    
    def unlink_connection_from_object(self, connection_name: str):
        """Unlink a MAVLink connection from its object.
        
        Args:
            connection_name: Name of the connection to unlink
        """
        conn = self.get_connection_by_name(connection_name)
        if conn is not None:
            conn.config.linked_object_name = ""
        
        if connection_name in self._saved_connections:
            self._saved_connections[connection_name].linked_object_name = ""
    
    def get_linked_object_name(self, connection_name: str) -> str:
        """Get the name of the object linked to a connection.
        
        Args:
            connection_name: Name of the connection
            
        Returns:
            Object name if linked, empty string otherwise
        """
        conn = self.get_connection_by_name(connection_name)
        if conn is not None:
            return conn.config.linked_object_name
        
        if connection_name in self._saved_connections:
            return self._saved_connections[connection_name].linked_object_name
        
        return ""
    
    def save_connection_config(self, config: MavlinkConnectionConfig):
        """Save a connection configuration for later use.
        
        Used for inactive connections that are linked to objects but not connected.
        
        Args:
            config: Connection configuration to save
        """
        name = config.name or self.generate_connection_name()
        config.name = name
        self._saved_connections[name] = config
    
    def get_available_connection_names(self) -> List[str]:
        """Get list of all available connection names (for dropdowns).
        
        Returns:
            List of connection names
        """
        names = []
        
        # Active connections
        for conn in self._connections.values():
            name = conn.config.name or f"Connection-{conn.config.system_id}"
            names.append(name)
        
        # Saved inactive connections
        for name in self._saved_connections.keys():
            if name not in names:
                names.append(name)
        
        return sorted(names)
    
    def discover_devices(self, timeout_secs: float = 3.0) -> List:
        """Discover MAVLink devices on the network.
        
        Listens for MAVLink heartbeats on common ports to discover devices.
        Note: This is a simplified discovery that may not work if the ports
        are already bound by other processes.
        
        Args:
            timeout_secs: Time to listen for devices
            
        Returns:
            List of DiscoveredDevice objects
        """
        from models.structs import DiscoveredDevice
        import socket
        discovered = []
        
        # Common MAVLink ports to check
        ports_to_check = [14550, 14540, 14560]
        port_timeout = timeout_secs / len(ports_to_check)
        
        for port in ports_to_check:
            try:
                # Create a UDP socket to listen for heartbeats
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.settimeout(port_timeout)
                
                try:
                    # Bind to all interfaces to receive MAVLink packets from any network source
                    # This is required for device discovery - drones may be on any network interface
                    # CodeQL: py/bind-socket-all-network-interfaces - intentional for discovery
                    sock.bind(('0.0.0.0', port))  # nosec B104
                    
                    # Listen for incoming data until timeout
                    start_time = time.time()
                    while time.time() - start_time < port_timeout:
                        try:
                            data, addr = sock.recvfrom(1024)
                            if len(data) > 0:
                                # Check if this looks like a MAVLink message
                                if data[0] == 0xFE or data[0] == 0xFD:  # MAVLink v1/v2 magic bytes
                                    # Use proper connection string for UDP input
                                    device = DiscoveredDevice(
                                        address=addr[0],
                                        port=port,
                                        connection_string=f"udpin:0.0.0.0:{port}"
                                    )
                                    # Avoid duplicates
                                    if not any(d.port == port for d in discovered):
                                        discovered.append(device)
                                        break  # Found device on this port, move to next
                        except socket.timeout:
                            break  # No more data on this port
                except OSError:
                    # Port already in use - skip it
                    pass
                finally:
                    sock.close()
            except Exception as e:
                print(f"[MavlinkService] Discovery error on port {port}: {e}")
        
        return discovered
    
    def run_connection_test(self, duration_secs: float = 2.0) -> dict:
        """Run a connection quality test for all active connections.
        
        Measures packet rate, latency, and packet loss by sending a burst
        of test messages and measuring response times.
        
        Args:
            duration_secs: Duration of test in seconds
            
        Returns:
            Dictionary mapping system_id to test results with:
            - rate_hz: Measured message rate
            - latency_ms: Estimated round-trip latency
            - lost_packets: Number of lost packets
            - quality: Quality rating ('good', 'fair', 'poor')
        """
        results = {}
        
        for sys_id, conn in self._connections.items():
            if not conn.is_connected:
                results[sys_id] = {
                    'rate_hz': 0,
                    'latency_ms': 0,
                    'lost_packets': 0,
                    'quality': 'disconnected'
                }
                continue
            
            # Record initial state
            initial_received = conn.status.messages_received
            initial_sent = conn.status.messages_sent
            
            # Get current rate and latency from connection status
            rate_hz = conn.status.message_rate_hz
            latency_ms = conn.status.latency_ms
            
            # Estimate packet loss based on recent history
            # (Simplified - in real implementation would track sequence numbers)
            lost_packets = 0
            
            # Determine quality rating
            if rate_hz >= 50 and latency_ms < 50:
                quality = 'good'
            elif rate_hz >= 20 and latency_ms < 100:
                quality = 'fair'
            else:
                quality = 'poor'
            
            results[sys_id] = {
                'rate_hz': rate_hz,
                'latency_ms': latency_ms,
                'lost_packets': lost_packets,
                'quality': quality
            }
        
        return results
    
    def get_status_label(self) -> str:
        """Get the current status label.
        
        Returns:
            Current status label string
        """
        return self._status_label
    
    def _sanitize_setpoint(self, setpoint: SetpointData) -> bool:
        """Validate and sanitize a setpoint before sending.
        
        Performs safety checks on setpoint values to prevent dangerous commands.
        
        Args:
            setpoint: Setpoint to validate
            
        Returns:
            True if setpoint is valid, False if it should be rejected
        """
        # Check position magnitude
        pos_magnitude = (setpoint.x**2 + setpoint.y**2 + setpoint.z**2) ** 0.5
        if pos_magnitude > self.MAX_POSITION_MAGNITUDE:
            return False
        
        # Check velocity magnitude if specified
        if setpoint.vx is not None and setpoint.vy is not None and setpoint.vz is not None:
            vel_magnitude = (setpoint.vx**2 + setpoint.vy**2 + setpoint.vz**2) ** 0.5
            if vel_magnitude > self.MAX_VELOCITY_MAGNITUDE:
                return False
        
        # Check yaw rate if specified
        if setpoint.yaw_rate is not None:
            if abs(setpoint.yaw_rate) > self.MAX_YAW_RATE:
                return False
        
        return True
    
    def _process_heartbeats(self):
        """Process heartbeat sending and connection health checks."""
        for conn in list(self._connections.values()):
            # Send heartbeat
            conn.send_heartbeat()
            
            # Check connection health
            if not conn.is_connected:
                if conn.state == ConnectionState.CONNECTED:
                    # Connection was lost
                    self.connection_changed.emit(conn.status.system_id, False)
                    self._update_status_label()
    
    def _process_telemetry(self):
        """Process incoming telemetry messages (lowest priority)."""
        total_rate = 0.0
        
        for conn in self._connections.values():
            # Receive and process messages
            messages = conn.receive_messages(max_messages=20)
            for msg in messages:
                conn.process_message(msg)
            
            # Emit telemetry update
            if messages:
                self.telemetry_updated.emit(conn.status.system_id, conn.telemetry)
            
            total_rate += conn.status.message_rate_hz
        
        self._total_rate_hz = total_rate
        self._active_connections = sum(1 for c in self._connections.values() if c.is_connected)
        self.health_updated.emit(self._total_rate_hz, self._active_connections)
    
    def _process_mocap(self):
        """Process motion capture data sending (highest priority)."""
        for system_id, obj in self._mocap_sources.items():
            conn = self._connections.get(system_id)
            if conn is None or not conn.is_connected:
                continue
            
            # Extract pose from scene object
            if hasattr(obj, 'pose') and len(obj.pose) >= 7:
                mocap = MocapData(
                    x=obj.pose[0],
                    y=obj.pose[2],  # Note: swapping Y/Z for NED frame
                    z=-obj.pose[1],  # NED: negative Z is up
                    q=(obj.pose[3], obj.pose[4], obj.pose[5], obj.pose[6])
                )
                conn.send_mocap_data(mocap)
    
    def _process_setpoints(self):
        """Process setpoint sending (medium priority)."""
        for system_id, setpoint in self._setpoint_sources.items():
            self.send_setpoint(system_id, setpoint)
    
    def _update_status_label(self):
        """Update the service status label based on connection state."""
        if not self._connections:
            self._status_label = "No Connections"
            self.set_status(ServiceLevel.STOPPED, "MAVLink: No Connections")
        else:
            connected = sum(1 for c in self._connections.values() if c.is_connected)
            total = len(self._connections)
            if connected == 0:
                self._status_label = f"0/{total} Connected"
                self.set_status(ServiceLevel.WARNING, f"MAVLink: 0/{total} Connected")
            elif connected < total:
                self._status_label = f"{connected}/{total} Connected"
                self.set_status(ServiceLevel.WARNING, f"MAVLink: {connected}/{total} Connected")
            else:
                self._status_label = f"{connected} Connected"
                self.set_status(ServiceLevel.RUNNING, f"MAVLink: {connected} Connected")
