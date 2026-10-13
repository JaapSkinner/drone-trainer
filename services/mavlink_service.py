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
import socket
import sys
import time
import threading
import logging
from collections import deque
from queue import PriorityQueue
from dataclasses import dataclass
from typing import Dict, Optional, List, Callable
from enum import Enum

from PyQt5.QtCore import pyqtSignal, QTimer, QThread

from services.service_base import ServiceBase, DebugLevel, ServiceLevel
from models import frames
from models.mavlink_links import is_serial, parse_endpoint, parse_link
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

logger = logging.getLogger(__name__)

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
            logger.info("DTRG dialect loaded from %s", _DIALECTS_PATH)
            
        except ImportError as e:
            # If custom dialect loading fails, fall back to standard
            logger.warning("Failed to import DTRG dialect: %s", e)
            USING_DTRG_DIALECT = False
            mavlink_dialect = mavutil.mavlink
    else:
        USING_DTRG_DIALECT = False
        mavlink_dialect = mavutil.mavlink
        if not DTRG_DIALECT_BUILT and DTRG_MAVLINK_AVAILABLE:
            logger.info("DTRG dialect not built; using standard dialect.")
        
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


class ConnectionTestWorker(QThread):
    """Worker thread to run connection tests off the UI thread.
    
    This prevents the UI from freezing during the test duration.
    Results are emitted via the test_complete signal.
    """
    
    test_complete = pyqtSignal(object)  # dict of test results
    error = pyqtSignal(str)
    
    def __init__(self, mavlink_service, duration_secs: float = 2.0, parent=None):
        """Initialize the connection test worker.
        
        Args:
            mavlink_service: MavlinkService instance to test
            duration_secs: Test duration in seconds
            parent: Parent QObject
        """
        super().__init__(parent)
        self._mavlink_service = mavlink_service
        self._duration_secs = duration_secs
    
    def run(self):
        """Run the connection test in a background thread."""
        if self._mavlink_service is None:
            self.error.emit("MAVLink service not available")
            return
        
        try:
            # Use the synchronous test method
            results = self._mavlink_service._run_connection_test_sync(self._duration_secs)
            self.test_complete.emit(results)
        except Exception as e:
            self.error.emit(str(e))


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
        self._message_times = deque()   # receive times in the last second (for the rate)
        self._lock = threading.Lock()
        self._console_output_callback = None  # set via set_console_output_callback()

        # Packet loss tracking: each sender (system, component) numbers its own packets.
        self._last_seq = {}        # (system, component) → last sequence number
        self._packets_dropped = 0  # Total dropped packets
        # The vehicle's autopilot is (status.system_id, _vehicle_component); anything else on the
        # link (QGC, a gimbal, another vehicle) must not update this vehicle's state.
        self._vehicle_component = 1
        self._other_systems = set()
        self.last_error = ""        # why the last connect() failed, for the UI

        # Relay to another ground station (config.forward_to), e.g. QGroundControl.
        self._forward_sock = None
        self._forward_addr = None
        self.forwarded_out = 0      # packets relayed vehicle → other GCS
        self.forwarded_in = 0       # packets relayed other GCS → vehicle

        # Round-trip time tracking
        self._ping_start_time = None
        self._last_ping_sent = 0.0

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
    
    @property
    def packets_dropped(self) -> int:
        """Get the total number of dropped packets detected."""
        return self._packets_dropped

    def connect(self) -> bool:
        """Establish the MAVLink connection.
        
        Returns:
            True if connection was established successfully, False otherwise.
        """
        if not PYMAVLINK_AVAILABLE:
            print(f"[MavlinkConnection] ERROR: pymavlink not available")
            self._state = ConnectionState.ERROR
            return False
        
        self.last_error = ""
        try:
            self._state = ConnectionState.CONNECTING
            self._connection = mavutil.mavlink_connection(
                self.config.connection_string,
                source_system=self.config.source_system,
                source_component=self.config.source_component,
            )

            # Prime the drone's MAVLink router by sending GCS heartbeats before
            # waiting for a response.  Many drones (PX4 + MAVLink router) won't
            # start unicasting back to our UDP address until they see at least one
            # incoming packet from us.  QGC triggers this same behaviour when you
            # manually add a UDP comm link and hit Connect.
            self._prime_connection()

            # Wait for a heartbeat from an autopilot. A GCS (QGC on the same network) or a
            # component such as a gimbal also sends heartbeats; those aren't the vehicle.
            msg = self._wait_vehicle_heartbeat(timeout=5.0)
            if msg is None:
                print(f"[MavlinkConnection] ERROR: No heartbeat received (timeout)")
                self.last_error = "no heartbeat"
                self._state = ConnectionState.DISCONNECTED
                return False
            
            self.status.system_id = msg.get_srcSystem()
            self._vehicle_component = msg.get_srcComponent()
            # Align config.system_id with the actual system ID from the first heartbeat
            # to ensure all subsequent operations target the correct drone.
            try:
                self.config.system_id = self.status.system_id
            except AttributeError:
                # If config has no system_id attribute, safely ignore to avoid breaking existing code.
                pass
            self.status.connected = True
            self.status.last_heartbeat = time.time()
            self._state = ConnectionState.CONNECTED
            self._open_forward()
            return True
            
        except Exception as e:
            print(f"[MavlinkConnection] ERROR: Connection failed: {e}")
            self.last_error = str(e) or type(e).__name__
            self._state = ConnectionState.ERROR
            self.status.connected = False
            return False

    # -- relaying to another ground station ------------------------------------------

    def _open_forward(self):
        """Start relaying to config.forward_to ("host:port"), if set."""
        self._close_forward()
        endpoint = parse_endpoint(getattr(self.config, "forward_to", ""))
        if endpoint is None:
            return
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setblocking(False)
            sock.bind(("0.0.0.0", 0))   # the other GCS replies to this address
        except OSError as exc:
            logger.warning("Can't open the forwarding socket for %s: %s", self.config.name, exc)
            return
        self._forward_sock, self._forward_addr = sock, endpoint
        logger.info("Relaying %s to %s:%d", self.config.name, *endpoint)

    def _close_forward(self):
        if self._forward_sock is not None:
            self._forward_sock.close()
        self._forward_sock = self._forward_addr = None

    @property
    def forwarding(self) -> bool:
        return self._forward_sock is not None

    def _forward_out(self, msg):
        if self._forward_sock is None:
            return
        try:
            self._forward_sock.sendto(bytes(msg.get_msgbuf()), self._forward_addr)
            self.forwarded_out += 1
        except OSError:
            pass   # the other GCS isn't running; keep trying with the next packet

    def pump_forward(self, max_packets: int = 200) -> int:
        """Pass packets from the other GCS on to the vehicle. Returns how many."""
        if self._forward_sock is None or self._connection is None:
            return 0
        count = 0
        for _ in range(max_packets):
            try:
                data, _ = self._forward_sock.recvfrom(65535)
            except (BlockingIOError, InterruptedError):
                break
            except OSError:   # e.g. Windows reports "port unreachable" this way when QGC is closed
                break
            with self._lock:
                if self._connection is None:
                    break
                self._connection.write(data)
            count += 1
        self.forwarded_in += count
        return count
    
    # Messages only a flight controller sends; applied only from the vehicle's autopilot.
    _VEHICLE_TELEMETRY = ('ATTITUDE', 'LOCAL_POSITION_NED', 'SYS_STATUS', 'GPS_RAW_INT', 'ESTIMATOR_STATUS')

    @staticmethod
    def is_vehicle_heartbeat(msg) -> bool:
        """A heartbeat from a flight controller (not a GCS, gimbal, camera …)."""
        return (msg.get_type() == 'HEARTBEAT' and msg.type != mavutil.mavlink.MAV_TYPE_GCS
                and msg.autopilot != mavutil.mavlink.MAV_AUTOPILOT_INVALID)

    def _wait_vehicle_heartbeat(self, timeout: float):
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            # Blocking with a timeout: None only once the time is up.
            msg = self._connection.recv_match(type='HEARTBEAT', blocking=True, timeout=remaining)
            if msg is None:
                return None
            if self.is_vehicle_heartbeat(msg):
                return msg

    def other_systems(self) -> set:
        """System IDs of other vehicles heard on this link (they are ignored)."""
        return set(self._other_systems)

    def _prime_connection(self, num_heartbeats: int = 3, interval: float = 0.5):
        """Send GCS heartbeats to prime the drone's MAVLink router.

        Some drones (PX4 with mavlink-router or similar) are passive: they only
        start unicasting telemetry back to a UDP endpoint after receiving at
        least one packet *from* that endpoint.  QGC works around this by sending
        heartbeats immediately on a manual UDP connect, which registers our
        IP:port with the router.  We replicate that behaviour here so the
        connection works on first attempt without needing QGC as a middleman.

        Args:
            num_heartbeats: Number of heartbeat packets to send before listening.
            interval: Delay in seconds between each heartbeat.
        """
        if self._connection is None:
            return
        try:
            for _ in range(num_heartbeats):
                self._connection.mav.heartbeat_send(
                    mavutil.mavlink.MAV_TYPE_GCS,
                    mavutil.mavlink.MAV_AUTOPILOT_INVALID,
                    0, 0, 0
                )
                time.sleep(interval)
        except Exception as e:
            # Non-fatal – we still try wait_heartbeat afterwards
            print(f"[MavlinkConnection] Warning: priming heartbeat send failed: {e}")

    def disconnect(self):
        """Close the MAVLink connection."""
        self._close_forward()
        with self._lock:
            if self._connection is not None:
                try:
                    self._connection.close()
                except Exception as e:
                    print(f"[MavlinkConnection] ERROR: Error closing connection: {e}")
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

    def send_ping(self) -> bool:
        """Send a PING message to measure round-trip time.

        Returns:
            True if ping was sent successfully
        """
        if self._connection is None:
            return False

        now = time.time()

        # Don't send pings too frequently (max 1 per second)
        if now - self._last_ping_sent < 1.0:
            return True

        try:
            # Send PING message with current timestamp in microseconds
            timestamp_usec = int(now * 1e6)
            self._connection.mav.ping_send(
                timestamp_usec,  # Time since system boot (we use current time)
                0,  # Ping sequence
                self.status.system_id,  # Target system
                0  # Target component (0 = all)
            )
            self._ping_start_time = now
            self._last_ping_sent = now
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
        except Exception as e:
            print(f"[MavlinkConnection] ERROR: Error sending mocap data: {e}")
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
            # Prefer the system ID learned from heartbeat if available, fall back to configured ID
            target_system = self.status.system_id or self.config.system_id
            target_component = self.config.component_id

            self._connection.mav.set_position_target_local_ned_send(
                0,  # time_boot_ms (not used)
                target_system,
                target_component,
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
        Also tracks packet loss by monitoring sequence numbers.

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
                if msg.get_type() != 'BAD_DATA':
                    self._forward_out(msg)

                # Track packet loss using sequence numbers (per sender: each counts its own,
                # wrapping at 256). MAVLink v1 and v2 both have them in the header.
                if msg.get_type() != 'BAD_DATA':
                    sender = (msg.get_srcSystem(), msg.get_srcComponent())
                    seq = msg.get_seq()
                    last = self._last_seq.get(sender)
                    if last is not None:
                        gap = (seq - last) % 256   # 1 = next packet, 0 = the same one heard twice
                        self._packets_dropped += max(0, gap - 1)
                    self._last_seq[sender] = seq

            except Exception:
                break
        
        return messages
    
    def _update_message_rate(self):
        """Update the message rate calculation."""
        now = time.time()
        # Keep messages from last second
        times = self._message_times
        times.append(now)
        while times and now - times[0] >= 1.0:
            times.popleft()
        self.status.message_rate_hz = len(times)
    
    def process_message(self, msg) -> bool:
        """Process a received MAVLink message and update telemetry.
        
        Args:
            msg: MAVLink message to process
            
        Returns:
            True if message was processed, False if message type is not handled
        """
        msg_type = msg.get_type()
        if msg_type == 'BAD_DATA':
            return False
        system, component = msg.get_srcSystem(), msg.get_srcComponent()
        vehicle = self.status.system_id or self.config.system_id
        if system != vehicle:
            # QGC, another vehicle on a shared link … never this vehicle's state.
            if self.is_vehicle_heartbeat(msg) or msg_type in self._VEHICLE_TELEMETRY:
                self._other_systems.add(system)
            return False
        from_autopilot = component == self._vehicle_component

        if msg_type == 'HEARTBEAT':
            if not (from_autopilot and self.is_vehicle_heartbeat(msg)):
                return False   # a gimbal, camera or companion computer on the vehicle
            self.status.last_heartbeat = time.time()
            self.status.connected = True
            self._state = ConnectionState.CONNECTED
            # Parse mode and armed state from heartbeat
            self.telemetry.armed = (msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED) != 0
            try:
                self.telemetry.mode = mavutil.mode_string_v10(msg)
            except (KeyError, AttributeError, TypeError):
                pass
            return True

        if msg_type in self._VEHICLE_TELEMETRY and not from_autopilot:
            return False
        
        elif msg_type == 'PING':
            # Respond to PING with same timestamp to measure RTT
            if self._ping_start_time is not None:
                now = time.time()
                rtt_ms = (now - self._ping_start_time) * 1000.0
                # Update latency with exponential moving average (smooth out spikes)
                if self.status.latency_ms == 0:
                    self.status.latency_ms = rtt_ms
                else:
                    # 80% old value, 20% new value
                    self.status.latency_ms = (0.8 * self.status.latency_ms) + (0.2 * rtt_ms)
                self._ping_start_time = None
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

        elif msg_type == 'STATUSTEXT':
            # Forward status text to console output callback if set
            text = msg.text if hasattr(msg, 'text') else ''
            if callable(self._console_output_callback):
                self._console_output_callback(f"[STATUS] {text.rstrip()}")
            return True

        elif msg_type == 'SERIAL_CONTROL':
            # Response from the NuttX shell (MAVLink console)
            if hasattr(msg, 'data') and hasattr(msg, 'count') and msg.count > 0:
                try:
                    text = bytes(msg.data[:msg.count]).decode('utf-8', errors='replace')
                    if callable(self._console_output_callback):
                        self._console_output_callback(text)
                except Exception:
                    pass
            return True

        return False

    def set_console_output_callback(self, callback):
        """Register a callback to receive console output lines.

        Args:
            callback: Callable that accepts a single str argument.
        """
        self._console_output_callback = callback

    def send_command_long(self, command: int, params: list = None) -> bool:
        """Send a MAV_CMD via COMMAND_LONG.

        Args:
            command: MAV_CMD id (e.g. mavutil.mavlink.MAV_CMD_DO_SET_MODE)
            params:  Up to 7 float parameters (padded with 0.0 if shorter)

        Returns:
            True if sent successfully.
        """
        if self._connection is None:
            return False
        p = list(params or [])
        p += [0.0] * (7 - len(p))
        try:
            self._connection.mav.command_long_send(
                self.status.system_id or self.config.system_id,
                self.config.component_id,
                command,
                0,          # confirmation
                p[0], p[1], p[2], p[3], p[4], p[5], p[6],
            )
            self.status.messages_sent += 1
            return True
        except Exception as e:
            print(f"[MavlinkConnection] ERROR sending COMMAND_LONG: {e}")
            return False

    def send_serial_control(self, text: str) -> bool:
        """Send a shell command to the drone via SERIAL_CONTROL (NuttX console).

        This is how the QGC MAVLink console works — it tunnels stdin/stdout
        through SERIAL_CONTROL messages on the SERIAL_CONTROL_DEV_SHELL device.

        Args:
            text: Command text to send (newline appended automatically)

        Returns:
            True if the message was sent successfully.
        """
        if self._connection is None:
            return False

        # SERIAL_CONTROL flags (bitmask):
        #   REPLY     = 1  — marks THIS message as a reply (don't set when sending commands)
        #   RESPOND   = 2  — ask the FC to send a reply back to us
        #   EXCLUSIVE = 4  — take exclusive ownership of the shell port
        #   BLOCKING  = 8  — block on writes
        #   MULTI     = 16 — keep sending replies until port is drained
        _SERIAL_CONTROL_DEV_SHELL = 10
        _FLAGS = 2 | 4 | 16   # RESPOND | EXCLUSIVE | MULTI

        line = (text.rstrip('\n') + '\n').encode('utf-8')

        chunk_size = 70
        try:
            for i in range(0, max(1, len(line)), chunk_size):
                chunk = line[i:i + chunk_size]
                data = list(chunk) + [0] * (chunk_size - len(chunk))
                self._connection.mav.serial_control_send(
                    _SERIAL_CONTROL_DEV_SHELL,
                    _FLAGS,
                    0,           # timeout ms
                    0,           # baud rate (unused for shell)
                    len(chunk),  # count
                    data,
                )
                self.status.messages_sent += 1
            return True
        except Exception as e:
            print(f"[MavlinkConnection] ERROR sending SERIAL_CONTROL: {e}")
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
    console_output = pyqtSignal(int, str)        # system_id, text line
    connection_test_complete = pyqtSignal(object)  # dict of test results
    connection_attempt_finished = pyqtSignal(str, bool, str)  # name, success, message

    # Service update rates
    TELEMETRY_UPDATE_INTERVAL_MS = 50   # 20Hz for telemetry (low priority)
    LINK_PUMP_INTERVAL_MS = 5           # read/relay links at 200 Hz
    MAX_MESSAGES_PER_PUMP = 1000        # per link per pump (bounded, so one link can't stall others)
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
        self._pump_timer: Optional[QTimer] = None
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

        # Background connection attempts (add_connection_async)
        self._attempting = set()
        self._attempt_lock = threading.Lock()
        self._reconnect_timer: Optional[QTimer] = None
    
    def get_global_settings(self) -> MavlinkGlobalSettings:
        """Get the current global MAVLink settings.
        
        Returns:
            Current global settings
        """
        return self._global_settings
    
    def update_global_settings(self, settings: MavlinkGlobalSettings):
        """Update global MAVLink settings.
        
        Updates the service configuration including setpoint limits and rates.
        Settings are stored in self._global_settings and read on-demand by
        methods like _sanitize_setpoint() rather than being copied to
        class-level constants.
        
        Safe to call from any thread: the timers live on the service thread,
        so the interval change is applied there.

        Args:
            settings: New global settings to apply
        """
        self._global_settings = settings
        self.call_in_service_thread(self._apply_timer_intervals)

    def _apply_timer_intervals(self):
        """Apply the rates in the global settings to the running timers.

        Must run on the service thread (QTimers can't be restarted from another
        thread — doing so was the cause of issue #40).
        """
        settings = self._global_settings

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

        if self._reconnect_timer is not None:
            self._reconnect_timer.setInterval(max(1000, int(1000 * (settings.reconnect_interval or 5.0))))
    
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
        self.update_object_config(obj, config)
    
    def unregister_mavlink_object(self, obj):
        """Unregister a scene object from MAVLink operations.
        
        Args:
            obj: Scene object to unregister
        """
        self._mavlink_objects.pop(obj, None)
        self._drop_mocap_source(obj)

    def update_object_config(self, obj, config: MavlinkObjectConfig):
        """Set (or replace) the MAVLink configuration for an object.

        Mocap routing is recomputed from scratch, so this is correct even when
        the caller edited the config object in place.

        * Linked to a named connection (``linked_connection_name``): mocap goes
          to that connection, looked up by name every tick (survives
          reconnects and system ID discovery).
        * Otherwise: legacy routing by ``config.system_id``.
        
        Args:
            obj: Scene object to update
            config: New MAVLink configuration
        """
        self._mavlink_objects[obj] = config
        self._drop_mocap_source(obj)
        if config.enabled and config.send_mocap and not config.linked_connection_name:
            self.register_mocap_source(config.system_id, obj)

    def _drop_mocap_source(self, obj):
        for system_id, source in list(self._mocap_sources.items()):
            if source is obj:
                del self._mocap_sources[system_id]

    def link_object(self, obj, connection_name: str):
        """Stream ``obj``'s pose to the named connection and record the link on both sides.

        Any other object linked to that connection is unlinked first.
        """
        for other, cfg in list(self._mavlink_objects.items()):
            if other is not obj and cfg.linked_connection_name == connection_name:
                self.unlink_object(other)
        cfg = obj.mavlink_config
        if cfg.linked_connection_name and cfg.linked_connection_name != connection_name:
            self.unlink_connection_from_object(cfg.linked_connection_name)
        cfg.enabled = True
        cfg.linked_connection_name = connection_name
        self.link_connection_to_object(connection_name, obj.name)
        self.update_object_config(obj, cfg)

    def unlink_object(self, obj, disable: bool = False):
        """Remove ``obj``'s connection link (and optionally disable MAVLink for it)."""
        cfg = obj.mavlink_config
        if cfg.linked_connection_name:
            self.unlink_connection_from_object(cfg.linked_connection_name)
        cfg.linked_connection_name = ""
        if disable:
            cfg.enabled = False
        self.update_object_config(obj, cfg)

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
            logger.error("MAVLink startup failed: pymavlink not installed")
            return
        
        # Log which dialect is being used
        dialect_info = self.get_dialect_info()
        if dialect_info['using_dtrg']:
            logger.info("Using DTRG MAVLink dialect from %s", dialect_info['dtrg_path'])
        else:
            logger.info("Using standard MAVLink dialect.")
        
        # Heartbeat timer - runs at 10Hz to check all connections
        self._heartbeat_timer = QTimer(self)
        self._heartbeat_timer.setInterval(self.HEARTBEAT_CHECK_INTERVAL_MS)
        self._heartbeat_timer.timeout.connect(self.safe(self._process_heartbeats))
        self._heartbeat_timer.start()
        
        # Telemetry timer - lowest priority, 20Hz
        # Link pump - read everything waiting on every link and relay to other GCSs. Fast, so
        # nothing backs up (a Pixhawk on USB sends 1000+ messages/s) and relayed QGC traffic
        # isn't delayed; the UI is only told at the telemetry rate.
        self._pump_timer = QTimer(self)
        self._pump_timer.setInterval(self.LINK_PUMP_INTERVAL_MS)
        self._pump_timer.timeout.connect(self.safe(self._pump_links))
        self._pump_timer.start()

        self._telemetry_timer = QTimer(self)
        self._telemetry_timer.setInterval(self.TELEMETRY_UPDATE_INTERVAL_MS)
        self._telemetry_timer.timeout.connect(self.safe(self._process_telemetry))
        self._telemetry_timer.start()
        
        # Mocap timer - highest priority, 100Hz
        self._mocap_timer = QTimer(self)
        self._mocap_timer.setInterval(self.MOCAP_UPDATE_INTERVAL_MS)
        self._mocap_timer.timeout.connect(self.safe(self._process_mocap))
        self._mocap_timer.start()
        
        # Setpoint timer - medium priority, 50Hz
        self._setpoint_timer = QTimer(self)
        self._setpoint_timer.setInterval(self.SETPOINT_UPDATE_INTERVAL_MS)
        self._setpoint_timer.timeout.connect(self.safe(self._process_setpoints))
        self._setpoint_timer.start()

        # Auto-reconnect: retry saved connections now and every reconnect_interval.
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.timeout.connect(self.safe(self._auto_reconnect))
        self._reconnect_timer.start()
        QTimer.singleShot(0, self.safe(self._auto_reconnect))

        # Settings may have been applied before the service started.
        self._apply_timer_intervals()

        self.set_status(ServiceLevel.RUNNING, "MAVLink: Ready")
        logger.info("MAVLink service started and ready.")
    
    def on_stop(self):
        """Stop all timers and disconnect all connections."""
        # Stop timers
        for timer in [self._heartbeat_timer, self._telemetry_timer, getattr(self, "_pump_timer", None),
                      self._mocap_timer, self._setpoint_timer, self._reconnect_timer]:
            if timer is not None:
                timer.stop()
                timer.deleteLater()
        
        self._heartbeat_timer = None
        self._telemetry_timer = None
        self._pump_timer = None
        self._mocap_timer = None
        self._setpoint_timer = None
        self._reconnect_timer = None

        # If a connection test worker is running, try to stop it cleanly
        if hasattr(self, '_test_worker') and self._test_worker is not None:
            try:
                if self._test_worker.isRunning():
                    # Wait briefly for it to finish
                    self._test_worker.wait(1000)
                self._test_worker.deleteLater()
            except Exception:
                pass
            finally:
                self._test_worker = None

    def update(self):
        """Main update loop - not used as we use separate timers for priority handling."""
        pass
    
    def _prepare_name(self, config: MavlinkConnectionConfig):
        if not config.name:
            config.name = self.generate_connection_name()
        elif config.name in self._saved_connections:
            pass  # reconnecting a saved connection: keep its name (objects link by name)
        elif not self.is_connection_name_unique(config.name):
            config.name = self.generate_connection_name(config.name)

    def add_connection(self, config: MavlinkConnectionConfig) -> bool:
        """Add and establish a new MAVLink connection (blocks for up to ~6 s).

        Prefer :meth:`add_connection_async` from the UI.
        
        Args:
            config: Connection configuration
            
        Returns:
            True if connection was established successfully
        """
        self._prepare_name(config)
        self._apply_identity(config)
        connection = MavlinkConnection(config)
        return self._finish_connect(connection, connection.connect())[0]

    def add_connection_async(self, config: MavlinkConnectionConfig) -> str:
        """Connect on a background thread; the result arrives via ``connection_attempt_finished``.

        Returns the connection's (possibly generated) name.
        """
        self._prepare_name(config)
        with self._attempt_lock:
            if config.name in self._attempting:
                return config.name
            self._attempting.add(config.name)
        threading.Thread(target=self._connect_worker, args=(config,), daemon=True,
                         name=f"mavlink-connect-{config.name}").start()
        return config.name

    @staticmethod
    def explain_connect_failure(connection_string: str, error: str = "") -> str:
        """What to tell the user when a connection didn't come up."""
        link = parse_link(connection_string)
        text = (error or "").lower()
        if link.kind == "serial":
            if "no module named 'serial'" in text:
                return "USB/serial links need pyserial: pip install pyserial (it's in requirements.txt)."
            if any(k in text for k in ("access is denied", "permission denied", "busy", "in use",
                                       "resource temporarily unavailable")):
                return (f"{link.device} is in use by another program (QGroundControl or Mission Planner?). "
                        "Only one program can open a serial port: close it there, or connect here and turn "
                        "on \"Share with QGroundControl\".")
            if any(k in text for k in ("could not open", "no such file", "cannot find", "filenotfound",
                                       "does not exist")):
                return f"{link.device} isn't there. Is the radio / USB cable plugged in? Try Refresh."
            if not text or text == "no heartbeat":
                return (f"No heartbeat on {link.device} at {link.baud} baud. Check the baud rate "
                        "(57600 SiK radio, 460800 ExpressLRS, any for a Pixhawk's own USB) and that the "
                        "vehicle is powered.")
            return f"Couldn't open {link.device}: {error}"
        if text and text != "no heartbeat":
            return f"Couldn't open {connection_string}: {error}"
        return (f"No heartbeat from {connection_string}. Check the vehicle is on and sending MAVLink to this "
                "PC, and that the address/port is right (if QGroundControl is open on the same port, only one "
                "of them gets the data).")

    def is_connecting(self, name: str) -> bool:
        with self._attempt_lock:
            return name in self._attempting

    def _apply_identity(self, config: MavlinkConnectionConfig):
        """Send as the MAVLink system/component set in Settings (not each connection's old default)."""
        settings = self._global_settings
        config.source_system = int(getattr(settings, "source_system_id", 245))
        config.source_component = int(getattr(settings, "source_component_id", 190))

    def _connect_worker(self, config: MavlinkConnectionConfig):
        self._apply_identity(config)
        connection = MavlinkConnection(config)
        try:
            ok = connection.connect()
        except Exception:
            logger.exception("MAVLink connect raised for %s", config.name)
            ok = False
        self.call_in_service_thread(self._finish_connect_async, connection, ok)

    def _finish_connect_async(self, connection, ok: bool):
        name = connection.config.name
        success, message = self._finish_connect(connection, ok)
        with self._attempt_lock:
            self._attempting.discard(name)
        self.connection_attempt_finished.emit(name, success, message)

    def _finish_connect(self, connection, ok: bool):
        """Register a connection whose connect() returned ``ok``. Returns (success, message)."""
        config = connection.config
        if not ok:
            connection.disconnect()  # free the socket so a retry can bind it again
            message = self.explain_connect_failure(config.connection_string, getattr(connection, "last_error", ""))
            logger.warning("Couldn't connect %s (%s): %s", config.name, config.connection_string,
                           getattr(connection, "last_error", "") or "no heartbeat")
            return False, message

        sys_id = connection.status.system_id
        existing = self._connections.get(sys_id)
        if existing is not None and existing is not connection:
            connection.disconnect()
            message = (f"'{existing.config.name}' already uses MAVLink system ID {sys_id}. Give each vehicle "
                       "a unique MAV_SYS_ID (PX4 parameter) so they can be told apart.")
            logger.warning(message)
            return False, message

        self._connections[sys_id] = connection
        self._active_connections = len(self._connections)
        config.auto_connect = True

        # Wire console output from this connection back through our signal
        connection.set_console_output_callback(
            lambda text, sid=sys_id: self.console_output.emit(sid, text)
        )

        # Drop the saved entry (by name, connection string or system ID) so it isn't listed twice.
        for saved_name, saved_config in list(self._saved_connections.items()):
            if (saved_name == config.name or saved_config.connection_string == config.connection_string
                    or saved_config.system_id == sys_id):
                del self._saved_connections[saved_name]

        self.connection_changed.emit(sys_id, True)
        logger.info("MAVLink connected: name=%s system_id=%s connection=%s",
                    config.name, sys_id, config.connection_string)
        self._update_status_label()
        return True, ""

    def disconnect_by_user(self, system_id: int):
        """Disconnect and don't reconnect automatically until the user connects again."""
        conn = self._connections.get(system_id)
        if conn is not None:
            conn.config.auto_connect = False
        self.remove_connection(system_id)

    def _auto_reconnect(self):
        """Retry saved connections that should be connected (settings: auto reconnect)."""
        if not self._global_settings.auto_reconnect:
            return
        for name, config in list(self._saved_connections.items()):
            if config.auto_connect and not self.is_connecting(name) and self.get_connection_by_name(name) is None:
                self.add_connection_async(config)

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
            logger.info("MAVLink disconnected: system_id=%s", system_id)
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

    def send_console_command(self, system_id: int, text: str) -> bool:
        """Send a shell command to the drone's MAVLink console (SERIAL_CONTROL/SHELL).

        Mirrors the QGC MAVLink Console — tunnels stdin over SERIAL_CONTROL
        messages so the NuttX shell on the flight controller receives the command
        and streams stdout back as further SERIAL_CONTROL messages (routed to
        the console_output signal).

        Args:
            system_id: Target drone's system ID
            text: Command string to send

        Returns:
            True if the message was sent successfully.
        """
        conn = self._connections.get(system_id)
        if conn is not None and conn.is_connected:
            return conn.send_serial_control(text)
        return False

    def send_command_long(self, system_id: int, command: int, params: list = None) -> bool:
        """Send a MAV_CMD via COMMAND_LONG to a specific drone.

        Args:
            system_id: Target drone's system ID
            command: MAV_CMD id
            params: Up to 7 float parameters

        Returns:
            True if sent successfully.
        """
        conn = self._connections.get(system_id)
        if conn is not None and conn.is_connected:
            return conn.send_command_long(command, params)
        return False

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
            old_name = conn.config.name
            conn.config.name = new_name
            self.rename_links(old_name, new_name)
            return True
        return False

    def rename_links(self, old_name: str, new_name: str, objects=()):
        """Point objects linked to connection ``old_name`` at ``new_name``.

        ``objects`` adds scene objects that may not be registered here yet.
        """
        if not old_name or old_name == new_name:
            return
        for obj in {id(o): o for o in [*self._mavlink_objects, *objects]}.values():
            cfg = getattr(obj, "mavlink_config", None)
            if cfg is not None and cfg.linked_connection_name == old_name:
                cfg.linked_connection_name = new_name
    
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
        
        # Emit update only for an active connection
        if conn is not None:
            self.connection_changed.emit(conn.config.system_id, True)
    
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
    
    def get_active_connections(self) -> Dict[int, 'MavlinkConnection']:
        """Get dictionary of currently active connections.
        
        Returns a copy of the active connections dictionary. Use this public
        method instead of accessing the internal _connections attribute.
        
        Returns:
            Dictionary mapping system_id to MavlinkConnection
        """
        return dict(self._connections)
    
    def remove_saved_connection(self, name: str) -> bool:
        """Remove a saved connection configuration by name.
        
        Use this public method instead of accessing the internal
        _saved_connections attribute directly.
        
        Args:
            name: Name of the saved connection to remove
            
        Returns:
            True if removed, False if not found
        """
        if name in self._saved_connections:
            del self._saved_connections[name]
            return True
        return False
    
    def discover_devices(self, timeout_secs: float = 3.0) -> List:
        """Discover MAVLink devices on the network.

        Listens for MAVLink heartbeats on common ports to discover devices.
        Before listening on each port, a GCS heartbeat is broadcast to that
        port so that passive drones (PX4 + mavlink-router style setups) that
        only begin sending once they receive an incoming packet will respond.
        This mirrors the behaviour of QGC's manual UDP "Connect" button.

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
        logger.info("Starting MAVLink discovery run (timeout=%.1fs)", timeout_secs)

        # Common MAVLink ports to check.
        # Each port needs at least 1.5 s to be sure of catching a 1 Hz PX4 heartbeat.
        ports_to_check = [14550, 14540, 14560]
        port_timeout = max(1.5, timeout_secs / len(ports_to_check))

        # --- Build a minimal MAVLink v1 GCS HEARTBEAT packet by hand ---
        # This avoids needing an active mavutil connection at this point and
        # lets us probe each port before binding a listener to it.
        # 
        # MAVLink v1 HEARTBEAT layout:
        #   Header: magic(1) + len(1) + seq(1) + sys(1) + comp(1) + msg_id(1)
        #   Payload (9 bytes):
        #     - custom_mode: uint32 (4 bytes, little-endian)
        #     - type: uint8 (1 byte) - MAV_TYPE_GCS = 6
        #     - autopilot: uint8 (1 byte) - MAV_AUTOPILOT_INVALID = 8
        #     - base_mode: uint8 (1 byte) - 0
        #     - system_status: uint8 (1 byte) - MAV_STATE_UNINIT = 0
        #     - mavlink_version: uint8 (1 byte) - 3
        #   Checksum: CRC-16/MCRF4XX (2 bytes)
        _HEARTBEAT_PAYLOAD = bytes([
            0, 0, 0, 0,  # custom_mode (uint32 little-endian)
            6,           # type (MAV_TYPE_GCS)
            8,           # autopilot (MAV_AUTOPILOT_INVALID)
            0,           # base_mode
            0,           # system_status (MAV_STATE_UNINIT)
            3,           # mavlink_version
        ])  # 9 bytes total
        _crc_extra = 50  # HEARTBEAT CRC extra byte
        
        # CRC-16/MCRF4XX over (len, seq, sys, comp, msg_id) + payload + crc_extra
        def _mavlink_crc(data: bytes) -> int:
            crc = 0xFFFF
            for b in data:
                tmp = b ^ (crc & 0xFF)
                tmp ^= (tmp << 4) & 0xFF
                crc = ((crc >> 8) ^ (tmp << 8) ^ (tmp << 3) ^ (tmp >> 4)) & 0xFFFF
            return crc

        _header = bytes([9, 0, 255, 0, 0])  # len=9, seq=0, sys=255, comp=0, msg_id=0
        _crc_input = _header + _HEARTBEAT_PAYLOAD + bytes([_crc_extra])
        _crc_val = _mavlink_crc(_crc_input)
        _HEARTBEAT_PACKET = (
            bytes([0xFE])          # magic
            + _header
            + _HEARTBEAT_PAYLOAD
            + bytes([_crc_val & 0xFF, (_crc_val >> 8) & 0xFF])
        )

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

                    # Probe: broadcast a GCS heartbeat so passive drones register our
                    # address and start sending.  This is what QGC does on a manual
                    # UDP connect and is the fix for the "works after QGC, not before" quirk.
                    try:
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                        sock.sendto(_HEARTBEAT_PACKET, ('<broadcast>', port))
                    except Exception:
                        pass  # Broadcast may fail on some interfaces; carry on listening anyway

                    # Listen for packets until we get the flight controller's HEARTBEAT
                    # or the timeout expires.
                    #
                    # Why not just break on the first heartbeat?
                    # A PX4 stack typically forwards heartbeats from *multiple* components:
                    #   - The companion / MAVLink router itself (autopilot=8 INVALID, type=18)
                    #   - The actual flight controller      (autopilot=12 PX4,     type=14)
                    # The companion heartbeat usually arrives first.  We keep reading until
                    # we find one with a real autopilot value, falling back to whatever we
                    # have if time runs out.
                    _MAV_AUTOPILOT_INVALID = 8  # MAV_AUTOPILOT_INVALID — not a real FC

                    start_time = time.time()
                    best_device = None   # best heartbeat decoded so far

                    while time.time() - start_time < port_timeout:
                        try:
                            data, addr = sock.recvfrom(1024)
                            if len(data) < 6:
                                continue

                            magic = data[0]
                            if magic not in (0xFE, 0xFD):
                                continue  # Not a MAVLink packet

                            # Skip if we already have a confirmed entry for this address
                            if any(d.address == addr[0] and d.port == port for d in discovered):
                                break

                            # --- Parse header ---
                            try:
                                if magic == 0xFE:
                                    plen          = data[1]
                                    sys_id        = data[3]
                                    comp_id       = data[4]
                                    msg_id        = data[5]
                                    payload_start = 6
                                    mav_version   = 1
                                else:
                                    plen          = data[1]
                                    sys_id        = data[5]
                                    comp_id       = data[6]
                                    msg_id        = data[7] | (data[8] << 8) | (data[9] << 16)
                                    payload_start = 10
                                    mav_version   = 2
                            except IndexError:
                                continue

                            # Only HEARTBEAT (msg_id 0) carries identity info
                            if msg_id != 0:
                                continue

                            # --- Decode HEARTBEAT payload ---
                            # bytes 0-3  custom_mode  (uint32 LE)
                            # byte  4    MAV_TYPE
                            # byte  5    MAV_AUTOPILOT
                            # byte  6    base_mode    (0x80 = ARMED)
                            vehicle_type   = -1
                            autopilot_type = -1
                            armed          = False
                            try:
                                if plen >= 7 and len(data) >= payload_start + plen:
                                    p              = data[payload_start: payload_start + plen]
                                    vehicle_type   = p[4]
                                    autopilot_type = p[5]
                                    armed          = bool(p[6] & 0x80)
                                    print(f"[MavlinkService] Discovery HB: sys={sys_id} comp={comp_id} "
                                          f"type={vehicle_type} autopilot={autopilot_type} "
                                          f"armed={armed} mav_v={mav_version}")
                            except IndexError:
                                pass

                            candidate = DiscoveredDevice(
                                address=addr[0],
                                port=port,
                                system_id=sys_id,
                                component_id=comp_id,
                                connection_string=f"udpin:0.0.0.0:{port}",
                                vehicle_type=vehicle_type,
                                autopilot=autopilot_type,
                                armed=armed,
                                mavlink_version=mav_version,
                            )

                            # Prefer a real flight controller over a companion/router.
                            # Keep reading if we only have an INVALID autopilot so far.
                            if best_device is None:
                                best_device = candidate

                            if autopilot_type != _MAV_AUTOPILOT_INVALID:
                                # Found the actual FC — no need to wait any longer
                                best_device = candidate
                                break
                            # else: companion HB — store as fallback and keep waiting

                        except socket.timeout:
                            break

                    if best_device is not None:
                        if not any(d.address == best_device.address and d.port == port
                                   for d in discovered):
                            discovered.append(best_device)
                except OSError as e:
                    # Port already in use - skip it
                    print(f"[MavlinkService] Discovery: Port {port} already in use")
                    logger.info("Discovery skipped port %s: already in use", port)
                finally:
                    sock.close()
            except Exception as e:
                print(f"[MavlinkService] ERROR: Discovery error on port {port}: {e}")
                logger.error("Discovery error on port %s: %s", port, e)

        logger.info("MAVLink discovery finished: %d device(s) found", len(discovered))
        return discovered
    
    def run_connection_test(self, duration_secs: float = 2.0):
        """Run a connection quality test for all active connections (non-blocking).
        
        Spawns a worker thread to run the test and emits results via the
        connection_test_complete signal. This prevents UI freezing during tests.
        
        Args:
            duration_secs: Duration of test in seconds
        """
        # Clean up any previous worker to avoid memory leaks
        if hasattr(self, '_test_worker') and self._test_worker is not None:
            if self._test_worker.isRunning():
                self._test_worker.wait(1000)  # Wait up to 1 second for completion
            self._test_worker.deleteLater()
            self._test_worker = None
        
        # Create and start worker thread
        self._test_worker = ConnectionTestWorker(self, duration_secs, parent=self)
        self._test_worker.test_complete.connect(self._on_connection_test_complete)
        self._test_worker.error.connect(self._on_connection_test_error)
        self._test_worker.finished.connect(self._on_test_worker_finished)
        self._test_worker.start()
    
    def _on_connection_test_error(self, error_msg: str):
        """Handle connection test error from worker thread.
        
        Emits empty results with error information.
        """
        self.log(f"Connection test error: {error_msg}", DebugLevel.LOG)
        # Emit empty results to signal completion with error
        self.connection_test_complete.emit({})
    
    def _on_test_worker_finished(self):
        """Clean up worker after completion."""
        if hasattr(self, '_test_worker') and self._test_worker is not None:
            self._test_worker.deleteLater()
            self._test_worker = None
    
    def _on_connection_test_complete(self, results: dict):
        """Handle connection test completion from worker thread."""
        self.connection_test_complete.emit(results)
    
    def _run_connection_test_sync(self, duration_secs: float = 2.0) -> dict:
        """Run a connection quality test synchronously (blocks caller).
        
        This is the internal implementation called by ConnectionTestWorker.
        Do not call from UI thread - use run_connection_test() instead.
        
        Args:
            duration_secs: Duration of test in seconds
            
        Returns:
            Dictionary mapping system_id to test results with:
            - rate_hz: Measured message rate
            - latency_ms: Round-trip time in milliseconds
            - lost_packets: Number of dropped packets detected
            - messages_sent: Total messages sent on this connection
            - messages_received: Total messages received on this connection
            - quality: Quality rating ('good', 'fair', 'poor')
        """
        results = {}
        
        # Send pings to all connections
        for conn in self._connections.values():
            if conn.is_connected:
                conn.send_ping()

        # Wait for pings to return and metrics to stabilize over the requested duration
        time.sleep(duration_secs)

        for sys_id, conn in self._connections.items():
            if not conn.is_connected:
                results[sys_id] = {
                    'rate_hz': 0,
                    'latency_ms': 0,
                    'lost_packets': 0,
                    'messages_sent': 0,
                    'messages_received': 0,
                    'quality': 'disconnected'
                }
                continue
            
            # Get current metrics from connection status
            rate_hz = conn.status.message_rate_hz
            latency_ms = conn.status.latency_ms
            messages_sent = conn.status.messages_sent
            messages_received = conn.status.messages_received
            lost_packets = conn.packets_dropped

            # Determine quality rating based on message rate and latency
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
                'messages_sent': messages_sent,
                'messages_received': messages_received,
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
        Uses limits from global settings (self._global_settings) for configurability.
        
        Args:
            setpoint: Setpoint to validate
            
        Returns:
            True if setpoint is valid, False if it should be rejected
        """
        # Get limits from global settings (configurable per-session)
        max_pos = self._global_settings.max_position_magnitude
        max_vel = self._global_settings.max_velocity_magnitude
        max_yaw = self._global_settings.max_yaw_rate
        
        # Check position magnitude
        pos_magnitude = (setpoint.x**2 + setpoint.y**2 + setpoint.z**2) ** 0.5
        if pos_magnitude > max_pos:
            return False
        
        # Check velocity magnitude if specified
        if setpoint.vx is not None and setpoint.vy is not None and setpoint.vz is not None:
            vel_magnitude = (setpoint.vx**2 + setpoint.vy**2 + setpoint.vz**2) ** 0.5
            if vel_magnitude > max_vel:
                return False
        
        # Check yaw rate if specified
        if setpoint.yaw_rate is not None:
            if abs(setpoint.yaw_rate) > max_yaw:
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
    
    def _pump_links(self):
        """Read every waiting message on every link, update its vehicle, relay to other GCSs."""
        for conn in list(self._connections.values()):
            messages = conn.receive_messages(max_messages=self.MAX_MESSAGES_PER_PUMP)
            for msg in messages:
                conn.process_message(msg)
            if messages:
                conn.telemetry_changed = True
            conn.pump_forward()

    def _process_telemetry(self):
        """Tell the UI about new telemetry (at the telemetry rate)."""
        total_rate = 0.0
        
        for conn in self._connections.values():
            if getattr(conn, "telemetry_changed", False):
                conn.telemetry_changed = False
                self.telemetry_updated.emit(conn.status.system_id, conn.telemetry)
            
            total_rate += conn.status.message_rate_hz
        
        self._total_rate_hz = total_rate
        self._active_connections = sum(1 for c in self._connections.values() if c.is_connected)
        self.health_updated.emit(self._total_rate_hz, self._active_connections)
    
    # Stop streaming mocap this long after the last motion capture sample, so the
    # vehicle's own external-vision timeout/failsafe takes over instead of it
    # being fed a frozen position.
    MOCAP_STALE_S = 0.25

    @classmethod
    def mocap_freshness(cls, obj, cfg=None) -> str:
        """Why an object's pose may (not) be sent as mocap: 'ok', 'not_tracked',
        'locked' or 'tracking_lost'."""
        if cfg is not None and getattr(cfg, "send_mocap_untracked", False):
            return "ok"
        if not getattr(obj, "tracked", False):
            return "not_tracked"
        if getattr(obj, "pose_locked", False):
            return "locked"
        last = getattr(obj, "last_tracking_update", None)
        if last is None or time.monotonic() - last > cls.MOCAP_STALE_S:
            return "tracking_lost"
        return "ok"

    def mocap_stream_state(self, obj) -> str:
        """For the UI: 'streaming', 'disabled', 'not_linked', 'not_connected',
        'not_tracked', 'locked' or 'tracking_lost'."""
        cfg = self._mavlink_objects.get(obj) or getattr(obj, "mavlink_config", None)
        if cfg is None or not cfg.enabled or not cfg.send_mocap:
            return "disabled"
        if not cfg.linked_connection_name and not any(o is obj for o in self._mocap_sources.values()):
            return "not_linked"
        if cfg.linked_connection_name:
            conn = self.get_connection_by_name(cfg.linked_connection_name)
            if conn is None or not conn.is_connected:
                return "not_connected"
        freshness = self.mocap_freshness(obj, cfg)
        return "streaming" if freshness == "ok" else freshness

    def _mocap_targets(self):
        """(connection, scene object) pairs that should receive mocap this tick."""
        targets = []
        for system_id, obj in list(self._mocap_sources.items()):
            conn = self._connections.get(system_id)
            cfg = self._mavlink_objects.get(obj)
            if conn is not None and conn.is_connected and self.mocap_freshness(obj, cfg) == "ok":
                targets.append((conn, obj))
        for obj, cfg in list(self._mavlink_objects.items()):
            if cfg.enabled and cfg.send_mocap and cfg.linked_connection_name:
                conn = self.get_connection_by_name(cfg.linked_connection_name)
                if conn is not None and conn.is_connected and self.mocap_freshness(obj, cfg) == "ok":
                    targets.append((conn, obj))
        return targets

    def _process_mocap(self):
        """Process motion capture data sending (highest priority)."""
        for conn, obj in self._mocap_targets():
            # Scene pose (Y up) → PX4 NED position and FRD attitude.
            if hasattr(obj, 'pose') and len(obj.pose) >= 7:
                position, q = frames.scene_pose_to_ned(obj.pose)
                mocap = MocapData(x=position[0], y=position[1], z=position[2], q=q)
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
