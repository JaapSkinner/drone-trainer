"""Motion capture input (Vicon Tracker UDP or OptiTrack NatNet).

Runs on its own thread. Incoming samples are converted to scene poses
(models/frames.py), optionally filtered, and published in batches:

* ``poses_updated(dict)`` — ``{subject name: scene pose}`` with the newest
  sample of every subject seen since the last batch (up to ``poll_rate_hz``).
  MainWindow feeds this to ``ObjectService.apply_tracking_poses``.
* ``subjects_updated(list)`` — ``SubjectInfo`` snapshots for the UI (~2 Hz).

Control it from the GUI with ``configure()``, ``connect_source()`` and
``disconnect_source()``; they are queued onto the service thread.
"""
from __future__ import annotations

import copy
import logging
import socket
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from PyQt5.QtCore import QTimer, pyqtSignal

from models import frames
from models.structs import MotionCaptureConfig
from services.motion_capture import vicon_udp
from services.motion_capture.filters import PoseLowPass
from services.service_base import DebugLevel, ServiceBase, ServiceLevel

logger = logging.getLogger(__name__)


@dataclass
class SubjectInfo:
    name: str
    rate_hz: float
    age_s: float           # seconds since the last sample
    pose: tuple            # latest scene pose


class _SubjectStats:
    __slots__ = ("pose", "last_seen", "window_count", "rate_hz")

    def __init__(self):
        self.pose = None
        self.last_seen = 0.0
        self.window_count = 0
        self.rate_hz = 0.0


class MotionCaptureService(ServiceBase):
    poses_updated = pyqtSignal(object)
    subjects_updated = pyqtSignal(object)
    connection_changed = pyqtSignal(bool)

    STALE_AFTER_S = 1.0
    UI_REFRESH_S = 0.5
    MAX_DATAGRAMS_PER_POLL = 500

    def __init__(self, config: Optional[MotionCaptureConfig] = None, debug_level=None):
        super().__init__(debug_level=debug_level or DebugLevel.LOG)
        self._config = copy.deepcopy(config) if config else MotionCaptureConfig()
        self._lock = threading.Lock()
        self._pending: Dict[str, tuple] = {}
        self._subjects: Dict[str, _SubjectStats] = {}
        self._filters: Dict[str, PoseLowPass] = {}
        self._socket: Optional[socket.socket] = None
        self._optitrack = None
        self._connected = False
        self._connected_at = 0.0
        self._last_sample = 0.0
        self._window_start = 0.0
        self._parse_errors = 0
        self._timer: Optional[QTimer] = None
        self._last_ui_refresh = 0.0
        self._status_key = None
        self.set_status(ServiceLevel.STOPPED, "Not connected")

    # ------------------------------------------------------------------
    # Public API (any thread)
    # ------------------------------------------------------------------

    def get_config(self) -> MotionCaptureConfig:
        return copy.deepcopy(self._config)

    def configure(self, config: MotionCaptureConfig):
        """Apply new settings; reconnects if currently connected."""
        self.call_in_service_thread(self._apply_config, copy.deepcopy(config))

    def connect_source(self):
        self.call_in_service_thread(self._connect)

    def disconnect_source(self):
        self.call_in_service_thread(self._disconnect)

    def is_connected(self) -> bool:
        return self._connected

    def subjects_snapshot(self) -> List[SubjectInfo]:
        now = time.monotonic()
        with self._lock:
            return sorted((SubjectInfo(name, s.rate_hz, now - s.last_seen, s.pose)
                           for name, s in self._subjects.items() if s.pose is not None),
                          key=lambda info: info.name.lower())

    # ------------------------------------------------------------------
    # Service lifecycle (service thread)
    # ------------------------------------------------------------------

    def on_start(self):
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.safe(self.update))
        self._timer.start(self._poll_interval_ms())
        self._set_status(ServiceLevel.STOPPED, "Not connected")
        if self._config.auto_connect:
            self._connect()

    def on_stop(self):
        self._disconnect()
        if self._timer is not None:
            self._timer.stop()
            self._timer.deleteLater()
            self._timer = None

    def stop(self):
        # Release sockets even if the service thread never ran.
        if not (self._thread is not None and self._thread.isRunning()):
            self._close_sources()
        super().stop()

    def update(self):
        """Poll timer: drain the source, publish poses, refresh the UI/status."""
        if self._socket is not None:
            self._drain_vicon_socket()

        with self._lock:
            batch, self._pending = self._pending, {}
        if batch:
            self.poses_updated.emit(batch)

        now = time.monotonic()
        if now - self._last_ui_refresh >= self.UI_REFRESH_S:
            self._refresh_rates(now)
            self._last_ui_refresh = now
            self._update_status(now)
            self.subjects_updated.emit(self.subjects_snapshot())

    # ------------------------------------------------------------------
    # Internals (service thread unless noted)
    # ------------------------------------------------------------------

    def _poll_interval_ms(self) -> int:
        return max(1, int(1000.0 / max(1.0, float(self._config.poll_rate_hz))))

    def _apply_config(self, config: MotionCaptureConfig):
        was_connected = self._connected
        self._config = config
        self._filters.clear()
        if self._timer is not None:
            self._timer.setInterval(self._poll_interval_ms())
        if was_connected:
            self._connect()

    def _source_label(self) -> str:
        return "Vicon" if self._config.source == "vicon" else "OptiTrack"

    def _connect(self):
        self._close_sources()
        cfg = self._config
        error = None
        if cfg.source == "optitrack":
            from services.motion_capture.optitrack import OptiTrackSource
            source = OptiTrackSource(self._record_sample, cfg.optitrack_server_ip,
                                     cfg.optitrack_client_ip, cfg.optitrack_multicast,
                                     cfg.optitrack_up_axis)
            error = source.start()
            if error is None:
                self._optitrack = source
        else:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
                sock.bind((cfg.vicon_address, int(cfg.vicon_port)))
                sock.setblocking(False)
                self._socket = sock
            except OSError as exc:
                sock.close()
                error = f"could not listen on {cfg.vicon_address}:{cfg.vicon_port} ({exc})"

        if error:
            logger.warning("Motion capture connect failed: %s", error)
            self._connected = False
            self._set_status(ServiceLevel.ERROR, f"{self._source_label()}: {error}")
            self.connection_changed.emit(False)
            return

        self._connected = True
        self._connected_at = self._window_start = time.monotonic()
        self._last_sample = 0.0
        logger.info("Motion capture connected (%s)", self._describe_endpoint())
        self._update_status(time.monotonic())
        self.connection_changed.emit(True)

    def _disconnect(self):
        was_connected = self._connected
        self._close_sources()
        self._connected = False
        with self._lock:
            self._subjects.clear()
            self._pending.clear()
        self._filters.clear()
        self._set_status(ServiceLevel.STOPPED, "Not connected")
        if was_connected:
            logger.info("Motion capture disconnected")
            self.connection_changed.emit(False)
            self.subjects_updated.emit([])

    def _close_sources(self):
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None
        if self._optitrack is not None:
            self._optitrack.stop()
            self._optitrack = None

    def _describe_endpoint(self) -> str:
        cfg = self._config
        if cfg.source == "optitrack":
            mode = "multicast" if cfg.optitrack_multicast else "unicast"
            return f"OptiTrack {cfg.optitrack_server_ip} → {cfg.optitrack_client_ip}, {mode}"
        return f"Vicon UDP {cfg.vicon_address}:{cfg.vicon_port}"

    def _drain_vicon_socket(self):
        now = time.monotonic()
        for _ in range(self.MAX_DATAGRAMS_PER_POLL):
            try:
                data, _ = self._socket.recvfrom(65535)
            except (BlockingIOError, InterruptedError):
                return
            except OSError as exc:
                self._set_status(ServiceLevel.ERROR, f"Vicon: receive error ({exc})")
                return
            try:
                frame = vicon_udp.parse_packet(data)
            except vicon_udp.ViconPacketError as exc:
                self._parse_errors += 1
                if self._parse_errors in (1, 10, 100) or self._parse_errors % 1000 == 0:
                    logger.warning("Ignoring malformed Vicon packet (%d so far): %s", self._parse_errors, exc)
                continue
            for obj in frame.objects:
                if obj.name and not obj.occluded:
                    self._record_sample(obj.name,
                                        frames.vicon_to_scene_pose(obj.translation_mm, obj.rotation_rad),
                                        now)

    def _record_sample(self, name: str, pose: tuple, t: float):
        """Store a scene-frame sample. Called on the service thread or the NatNet thread."""
        if self._config.filter_enabled:
            filt = self._filters.get(name)
            if filt is None:
                filt = self._filters[name] = PoseLowPass(self._config.filter_cutoff_hz)
            pose = filt.update(pose, t)
        with self._lock:
            stats = self._subjects.get(name)
            if stats is None:
                stats = self._subjects[name] = _SubjectStats()
            stats.pose = pose
            stats.last_seen = t
            stats.window_count += 1
            self._pending[name] = pose
            self._last_sample = t

    def _refresh_rates(self, now: float):
        elapsed = now - self._window_start
        if elapsed <= 0:
            return
        with self._lock:
            for stats in self._subjects.values():
                stats.rate_hz = stats.window_count / elapsed
                stats.window_count = 0
        self._window_start = now

    def _update_status(self, now: float):
        if not self._connected:
            return
        label = self._source_label()
        if self._last_sample == 0.0:
            self._set_status(ServiceLevel.WARNING, f"{label}: waiting for data")
            return
        age = now - self._last_sample
        if age > self.STALE_AFTER_S:
            self._set_status(ServiceLevel.WARNING, f"{label}: no data for {age:.0f} s")
            return
        with self._lock:
            live = [s for s in self._subjects.values() if now - s.last_seen <= self.STALE_AFTER_S]
        rate = max((s.rate_hz for s in live), default=0.0)
        self._set_status(ServiceLevel.RUNNING, f"{label}: {len(live)} subject(s) @ {rate:.0f} Hz")

    def _set_status(self, level: ServiceLevel, label: str):
        if self._status_key != (level, label):
            self._status_key = (level, label)
            self.set_status(level, label)
