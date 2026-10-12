"""Stream live data to PlotJuggler (UDP Server or WebSocket Server plugin, JSON).

What is sent and how it is encoded lives in ``models/plot_stream.py``. This
service runs on its own thread: a timer at ``rate_hz`` takes a snapshot of the
scene (object poses, setpoints, motion capture subjects, MAVLink telemetry),
encodes it and sends it. Over WebSocket it connects to PlotJuggler's server
and keeps retrying while PlotJuggler isn't listening.

UI code talks to it with :meth:`set_config` and listens to ``stats_changed``.
"""
import logging
import socket
import time
from dataclasses import dataclass, replace

from PyQt5.QtCore import QTimer, QUrl, pyqtSignal
from PyQt5.QtNetwork import QAbstractSocket

from models import plot_stream
from models.plot_stream import PlotStreamConfig
from services.service_base import DebugLevel, ServiceBase, ServiceLevel

logger = logging.getLogger(__name__)

RECONNECT_MS = 2000
STATS_MS = 1000


@dataclass
class PlotStreamStats:
    state: str = "off"        # off | sending | connecting | connected | error
    rate_hz: float = 0.0      # messages per second actually sent
    bytes_per_s: float = 0.0
    message: str = ""         # last problem, for the UI


class PlotStreamService(ServiceBase):
    stats_changed = pyqtSignal(object)   # PlotStreamStats

    def __init__(self, object_service=None, control_service=None, motion_capture_service=None,
                 mavlink_service=None, debug_level=None):
        super().__init__(debug_level=debug_level or DebugLevel.LOG)
        self.object_service = object_service
        self.control_service = control_service
        self.motion_capture_service = motion_capture_service
        self.mavlink_service = mavlink_service
        self._config = PlotStreamConfig()
        self._stats = PlotStreamStats()
        self._timer = self._stats_timer = self._reconnect_timer = None
        self._udp = None
        self._ws = None
        self._sent = self._bytes = 0
        self._last_error = ""

    # -- public (any thread) ------------------------------------------------------

    def get_config(self) -> PlotStreamConfig:
        return replace(self._config)

    def get_stats(self) -> PlotStreamStats:
        return replace(self._stats)

    def set_config(self, config: PlotStreamConfig):
        """Apply a new configuration (takes effect on the service thread)."""
        self.call_in_service_thread(self._apply_config, replace(config))

    # -- lifecycle (service thread) ----------------------------------------------

    def on_start(self):
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.safe(self._tick))
        self._stats_timer = QTimer(self)
        self._stats_timer.timeout.connect(self.safe(self._publish_stats))
        self._stats_timer.start(STATS_MS)
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self.safe(self._open_websocket))
        self._apply_config(self._config)

    def on_stop(self):
        for timer in (self._timer, self._stats_timer, self._reconnect_timer):
            if timer is not None:
                timer.stop()
        self._close()

    def update(self):
        pass

    def _apply_config(self, config: PlotStreamConfig):
        changed_target = (config.transport, config.host, config.port) != (
            self._config.transport, self._config.host, self._config.port)
        self._config = config
        if self._timer is None:          # not started yet: on_start applies it
            return
        if not config.enabled:
            self._timer.stop()
            self._close()
            self._set_state("off")
            self.set_status(ServiceLevel.STOPPED, "Live plots: off")
            return
        if changed_target or (self._udp is None and self._ws is None):
            self._close()
            self._open()
        self._timer.start(max(1, int(round(1000.0 / config.rate_hz))))

    # -- connections (service thread) ---------------------------------------------

    def _open(self):
        self._last_error = ""
        if self._config.transport == "websocket":
            self._open_websocket()
        else:
            self._udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._udp.setblocking(False)
            self._set_state("sending")
            self.set_status(ServiceLevel.RUNNING, f"Live plots: {self._config.address}")

    def _open_websocket(self):
        if not self._config.enabled or self._config.transport != "websocket":
            return
        from PyQt5.QtWebSockets import QWebSocket
        if self._ws is None:
            self._ws = QWebSocket()
            self._ws.setParent(self)
            self._ws.connected.connect(self.safe(self._on_ws_connected))
            self._ws.disconnected.connect(self.safe(self._on_ws_disconnected))
            self._ws.error.connect(self.safe(self._on_ws_error))
        self._set_state("connecting")
        self.set_status(ServiceLevel.WARNING, f"Live plots: waiting for {self._config.address}")
        self._ws.open(QUrl(self._config.address))

    def _on_ws_connected(self):
        self._last_error = ""
        self._set_state("connected")
        self.set_status(ServiceLevel.RUNNING, f"Live plots: {self._config.address}")
        logger.info("Live plots: connected to PlotJuggler at %s", self._config.address)

    def _on_ws_disconnected(self):
        if self._config.enabled and self._config.transport == "websocket":
            self._set_state("connecting")
            if self._reconnect_timer is not None and not self._reconnect_timer.isActive():
                self._reconnect_timer.start(RECONNECT_MS)

    def _on_ws_error(self, _error):
        if self._ws is not None:
            self._last_error = self._ws.errorString()

    def _close(self):
        if self._reconnect_timer is not None:
            self._reconnect_timer.stop()
        if self._udp is not None:
            self._udp.close()
            self._udp = None
        if self._ws is not None:
            ws, self._ws = self._ws, None
            ws.disconnected.disconnect()
            ws.abort()
            ws.deleteLater()

    # -- sending (service thread) -----------------------------------------------------

    def snapshot(self) -> dict:
        """The message for this instant (also used by tests)."""
        config = self._config
        objects = list(self.object_service.get_objects()) if self.object_service is not None else []
        states = self.control_service.states() if (config.setpoints and self.control_service is not None) else None
        subjects = (self.motion_capture_service.subjects_snapshot()
                    if (config.motion_capture and self.motion_capture_service is not None) else ())
        telemetry = self._telemetry() if config.mavlink else None
        return plot_stream.build_sample(time.time(), config, objects, states, subjects, telemetry,
                                        now=time.monotonic())

    def _telemetry(self):
        service = self.mavlink_service
        if service is None:
            return None
        try:
            result = {}
            for system_id, data in service.get_all_telemetry().items():
                conn = service.get_connection(system_id)
                name = getattr(getattr(conn, "config", None), "name", "") or f"system {system_id}"
                result[name] = data
            return result
        except RuntimeError:   # its connection table changed while we read it: skip this tick
            return None

    def _tick(self):
        if not self._config.enabled:
            return
        data = plot_stream.encode(self.snapshot())
        if self._udp is not None:
            try:
                self._udp.sendto(data, (self._config.host, self._config.port))
            except OSError as exc:
                self._report_error(f"Can't send to {self._config.address}: {exc}")
                return
        elif self._ws is not None and self._ws.state() == QAbstractSocket.ConnectedState:
            self._ws.sendTextMessage(data.decode("utf-8"))
        else:
            return
        self._sent += 1
        self._bytes += len(data)

    def _report_error(self, message):
        if message != self._last_error:
            logger.warning("Live plots: %s", message)
        self._last_error = message
        self._set_state("error")

    # -- stats -----------------------------------------------------------------

    def _set_state(self, state):
        if state != self._stats.state:
            self._stats = replace(self._stats, state=state)
            self.stats_changed.emit(replace(self._stats))

    def _publish_stats(self):
        seconds = STATS_MS / 1000.0
        state = self._stats.state
        if state == "error" and self._udp is not None and self._sent:
            state = "sending"    # it recovered
        self._stats = PlotStreamStats(state, self._sent / seconds, self._bytes / seconds, self._last_error)
        self._sent = self._bytes = 0
        self.stats_changed.emit(replace(self._stats))
