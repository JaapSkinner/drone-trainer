"""
Motion capture service with selectable provider backends.

Supports:
- Vicon-style raw UDP pose packets
- OptiTrack via NatNet (when available)
"""
import logging
import socket
import struct
import time
from enum import Enum

from PyQt5.QtCore import pyqtSignal, QTimer

from models.structs import PositionData
from services.service_base import ServiceBase, DebugLevel, ServiceLevel

logger = logging.getLogger(__name__)


class MotionCaptureSource(Enum):
    VICON = "vicon"
    OPTITRACK = "optitrack"


class MotionCaptureService(ServiceBase):
    """Service for receiving motion capture pose updates."""

    position_updated = pyqtSignal(PositionData)

    def __init__(self, debug_level=DebugLevel.LOG):
        super().__init__(debug_level)
        self.source = MotionCaptureSource.VICON
        self.address = "0.0.0.0"
        self.port = 51001
        self.frequency_hz = 100.0
        self.tracked_object_name = "tracked_object"

        self.connected = False
        self.tracking = False

        self._socket = None
        self._timer = None
        self._last_packet_time = 0.0
        self._natnet_client = None
        self._natnet_missing_logged = False

    def configure(self, source=None, address=None, port=None, frequency_hz=None, tracked_object_name=None):
        """Update motion capture connection settings."""
        if source is not None:
            if isinstance(source, MotionCaptureSource):
                self.source = source
            else:
                text = str(source).strip().lower()
                self.source = MotionCaptureSource.OPTITRACK if text == MotionCaptureSource.OPTITRACK.value else MotionCaptureSource.VICON
        if address is not None:
            self.address = str(address).strip() or "0.0.0.0"
        if port is not None:
            self.port = max(1, min(65535, int(port)))
        if frequency_hz is not None:
            self.frequency_hz = max(1.0, float(frequency_hz))
        if tracked_object_name is not None:
            self.tracked_object_name = str(tracked_object_name).strip() or "tracked_object"

    def get_config(self):
        return {
            "source": self.source.value,
            "address": self.address,
            "port": self.port,
            "frequency_hz": self.frequency_hz,
            "tracked_object_name": self.tracked_object_name,
        }

    def connect(self):
        """Connect to the configured motion capture source."""
        self.disconnect()

        if self.source == MotionCaptureSource.OPTITRACK:
            return self._connect_optitrack()
        return self._connect_udp()

    def _connect_udp(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self.address, self.port))
            sock.setblocking(False)
            self._socket = sock
            self.connected = True
            self.set_status(ServiceLevel.RUNNING, f"{self.source.value} connected ({self.address}:{self.port})")
            logger.info("MotionCaptureService connected UDP socket on %s:%s", self.address, self.port)
            return True
        except Exception as exc:
            self._socket = None
            self.connected = False
            self.set_status(ServiceLevel.ERROR, f"connect failed ({exc})")
            logger.warning("MotionCaptureService UDP connect failed: %s", exc)
            return False

    def _connect_optitrack(self):
        try:
            from natnet import NatNetClient  # type: ignore
        except Exception:
            if not self._natnet_missing_logged:
                logger.warning("OptiTrack selected but NatNet package is not installed")
                self._natnet_missing_logged = True
            self.connected = False
            self.set_status(ServiceLevel.ERROR, "NatNet package not available")
            return False

        try:
            self._natnet_client = NatNetClient()
            self.connected = True
            self.set_status(ServiceLevel.RUNNING, "optitrack configured")
            logger.info("MotionCaptureService configured OptiTrack/NatNet client")
            return True
        except Exception as exc:
            self._natnet_client = None
            self.connected = False
            self.set_status(ServiceLevel.ERROR, f"optitrack connect failed ({exc})")
            logger.warning("MotionCaptureService OptiTrack setup failed: %s", exc)
            return False

    def disconnect(self):
        self.stop_tracking()
        if self._socket is not None:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None
        self._natnet_client = None
        self.connected = False
        self.set_status(ServiceLevel.STOPPED, "disconnected")

    def start_tracking(self):
        if not self.connected:
            self.set_status(ServiceLevel.WARNING, "not connected")
            return False
        self.tracking = True
        self.set_status(ServiceLevel.RUNNING, f"tracking {self.source.value}")
        return True

    def stop_tracking(self):
        self.tracking = False
        if self.connected:
            self.set_status(ServiceLevel.RUNNING, f"{self.source.value} connected")
        else:
            self.set_status(ServiceLevel.STOPPED, "disconnected")

    def on_start(self):
        parent = self.get_thread_parent() or self
        self._timer = QTimer(parent)
        self._timer.timeout.connect(self.safe(self.update))
        self._timer.start(max(1, int(1000.0 / self.frequency_hz)))

    def on_stop(self):
        if self._timer is not None:
            self._timer.stop()
            self._timer.deleteLater()
            self._timer = None
        self.disconnect()

    @staticmethod
    def parse_udp_packet(data: bytes, fallback_name: str):
        """Parse a UDP mocap payload into PositionData.

        Supported packet formats:
        - CSV/UTF-8: name,x,y,z,roll,pitch,yaw
        - Binary: 6 little-endian float32 values: x,y,z,roll,pitch,yaw
        """
        if not data:
            return None

        try:
            decoded = data.decode("utf-8").strip()
            parts = [p.strip() for p in decoded.split(",")]
            if len(parts) == 7:
                name = parts[0] or fallback_name
                x, y, z, xr, yr, zr = (float(v) for v in parts[1:])
                return PositionData(name, x, y, z, xr, yr, zr)
        except Exception:
            pass

        if len(data) >= 24:
            try:
                x, y, z, xr, yr, zr = struct.unpack("<6f", data[:24])
                return PositionData(fallback_name, x, y, z, xr, yr, zr)
            except Exception:
                return None
        return None

    def update(self):
        if not (self.connected and self.tracking):
            return
        if self.source != MotionCaptureSource.VICON or self._socket is None:
            return

        packet_count = 0
        while packet_count < 10:
            try:
                data, _ = self._socket.recvfrom(4096)
            except BlockingIOError:
                break
            except Exception as exc:
                self.set_status(ServiceLevel.ERROR, f"udp read error ({exc})")
                return

            pos = self.parse_udp_packet(data, self.tracked_object_name)
            if pos is not None:
                self._last_packet_time = time.time()
                self.position_updated.emit(pos)
            packet_count += 1

        if self._last_packet_time and (time.time() - self._last_packet_time) > 2.0:
            self.set_status(ServiceLevel.WARNING, "tracking, no recent packets")
        else:
            self.set_status(ServiceLevel.RUNNING, f"tracking {self.source.value}")
