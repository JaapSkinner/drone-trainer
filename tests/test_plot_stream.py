"""Live plots: the JSON PlotJuggler gets, and streaming it over UDP / WebSocket."""
import json
import math
import os
import socket
import sys
import time
import unittest
from types import SimpleNamespace

from qt_test_utils import get_app, process_events_for, wait_until

from models import frames
from models.grid import Grid
from models.plot_stream import PlotStreamConfig, build_sample, encode
from models.rect_prism import RectPrism
from models.structs import MavlinkTelemetryData
from services.motion_capture_service import SubjectInfo
from services.object_service import ObjectService
from services.plot_stream_service import PlotStreamService

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from fake_plotjuggler import flatten  # noqa: E402  (PlotJuggler's JSON naming rules)


def _free_port(kind=socket.SOCK_DGRAM):
    with socket.socket(socket.AF_INET, kind) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _drone(name, position, yaw_deg=0.0):
    box = RectPrism(name=name, dimensions=0.3)
    box.set_pose((*position, *frames.quat_from_axis_angle((0, 1, 0), math.radians(yaw_deg))))
    return box


class SampleTests(unittest.TestCase):
    def setUp(self):
        self.drone = _drone("Drone A", (1.0, 2.0, 3.0), yaw_deg=90.0)
        self.config = PlotStreamConfig(enabled=True)

    def series(self, **kwargs):
        sample = build_sample(1760000000.5, self.config, **kwargs)
        return sample, flatten(json.loads(encode(sample)))

    def test_object_pose_in_scene_and_px4_frames(self):
        sample, series = self.series(objects=[self.drone, Grid()])
        self.assertEqual(series["/timestamp"], 1760000000.5)
        self.assertEqual(series["/objects/Drone A/position/x"], 1.0)
        self.assertEqual(series["/objects/Drone A/position/y"], 2.0)
        # Scene (x, y up, z) → NED (x, z, -y)
        self.assertAlmostEqual(series["/objects/Drone A/ned/x"], 1.0)
        self.assertAlmostEqual(series["/objects/Drone A/ned/y"], 3.0)
        self.assertAlmostEqual(series["/objects/Drone A/ned/z"], -2.0)
        # Turning left about "up" is a negative yaw about NED "down".
        self.assertAlmostEqual(series["/objects/Drone A/attitude_deg/yaw"], -90.0, places=4)
        self.assertAlmostEqual(series["/objects/Drone A/attitude_deg/roll"], 0.0, places=4)
        self.assertEqual(series["/objects/Drone A/tracked"], 0.0)
        self.assertFalse(any("Grid" in name for name in series), "scene helpers aren't sent")

    def test_setpoint_and_error(self):
        state = SimpleNamespace(setpoint=(1.5, 2.0, 2.0, *frames.IDENTITY_QUAT), ghost=None, ghost_pending=False)
        _, series = self.series(objects=[self.drone], control_states={self.drone: state})
        self.assertEqual(series["/setpoints/Drone A/position/x"], 1.5)
        self.assertAlmostEqual(series["/setpoints/Drone A/error/x"], 0.5)
        self.assertAlmostEqual(series["/setpoints/Drone A/error/z"], -1.0)
        self.assertAlmostEqual(series["/setpoints/Drone A/error/distance"], math.hypot(0.5, 1.0))
        self.assertAlmostEqual(series["/setpoints/Drone A/yaw_deg"], 0.0)

    def test_mocap_and_mavlink(self):
        subject = SubjectInfo("quad/1", 99.5, 0.01, (0.1, 1.0, 0.2, *frames.IDENTITY_QUAT))
        telemetry = MavlinkTelemetryData(roll=math.radians(10), x=4.0, vz=-0.5, battery_voltage=12.4,
                                         battery_remaining=80, armed=True)
        _, series = self.series(subjects=[subject], telemetry={"quad1": telemetry})
        self.assertEqual(series["/mocap/quad_1/rate_hz"], 99.5)       # '/' in a name can't split the path
        self.assertEqual(series["/mocap/quad_1/visible"], 1.0)
        self.assertAlmostEqual(series["/mavlink/quad1/attitude_deg/roll"], 10.0)
        self.assertEqual(series["/mavlink/quad1/ned/x"], 4.0)
        self.assertEqual(series["/mavlink/quad1/velocity_ned/z"], -0.5)
        self.assertEqual(series["/mavlink/quad1/armed"], 1.0)

    def test_sources_can_be_left_out(self):
        self.config.objects = False
        self.config.mavlink = False
        sample, _ = self.series(objects=[self.drone], telemetry={"quad1": MavlinkTelemetryData()})
        self.assertEqual(set(sample), {"timestamp"})

    def test_not_a_number_is_dropped_not_sent(self):
        data = encode({"timestamp": 1.0, "a": {"ok": 1.0, "bad": float("nan"), "inf": float("inf")}})
        self.assertEqual(json.loads(data), {"timestamp": 1.0, "a": {"ok": 1.0}})

    def test_config_round_trip_and_limits(self):
        config = PlotStreamConfig.from_dict({"enabled": True, "transport": "carrier pigeon", "rate_hz": 0,
                                             "port": "9871", "unknown": 1})
        self.assertEqual(config.transport, "udp")
        self.assertEqual(config.rate_hz, 1.0)
        self.assertEqual(config.port, 9871)
        self.assertEqual(PlotStreamConfig.from_dict(config.to_dict()), config)
        self.assertEqual(PlotStreamConfig(transport="websocket", port=9871).address, "ws://127.0.0.1:9871")


class StreamingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = get_app()

    def setUp(self):
        self.objects = ObjectService()
        self.objects.add_object(_drone("Drone A", (1.0, 1.0, 0.0)))
        self.service = PlotStreamService(self.objects)
        self.addCleanup(self._stop)
        self.stats = []
        self.service.stats_changed.connect(self.stats.append)

    def _stop(self):
        self.service.stop()
        process_events_for(0.1)

    def test_udp_messages_reach_a_listener(self):
        port = _free_port()
        listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        listener.bind(("127.0.0.1", port))
        listener.setblocking(False)
        self.addCleanup(listener.close)
        received = []

        def poll():
            try:
                while True:
                    received.append(listener.recvfrom(65535)[0])
            except BlockingIOError:
                pass
            return len(received) >= 5

        self.service.set_config(PlotStreamConfig(enabled=True, port=port, rate_hz=100))
        self.service.start()
        self.assertTrue(wait_until(poll, timeout_s=3.0), "no UDP messages")
        message = json.loads(received[-1])
        self.assertLess(abs(message["timestamp"] - time.time()), 2.0)
        self.assertEqual(flatten(message)["/objects/Drone A/position/x"], 1.0)
        self.assertTrue(wait_until(lambda: any(s.state == "sending" and s.rate_hz > 20 for s in self.stats),
                                   timeout_s=3.0))

        # Turning it off stops the stream.
        self.service.set_config(PlotStreamConfig(enabled=False, port=port))
        process_events_for(0.2)
        poll()
        count = len(received)
        process_events_for(0.3)
        poll()
        self.assertEqual(len(received), count)

    def test_websocket_waits_for_plotjuggler_then_streams(self):
        from PyQt5.QtNetwork import QHostAddress
        from PyQt5.QtWebSockets import QWebSocketServer
        port = _free_port(socket.SOCK_STREAM)
        self.service.set_config(PlotStreamConfig(enabled=True, transport="websocket", port=port, rate_hz=50))
        self.service.start()
        self.assertTrue(wait_until(lambda: any(s.state == "connecting" for s in self.stats), timeout_s=3.0))

        # PlotJuggler's WebSocket Server starts later: we connect on a retry and send text messages.
        server = QWebSocketServer("test PlotJuggler", QWebSocketServer.NonSecureMode)
        self.addCleanup(server.close)
        clients, texts = [], []

        def on_connection():
            client = server.nextPendingConnection()
            client.textMessageReceived.connect(texts.append)
            clients.append(client)
        server.newConnection.connect(on_connection)
        self.assertTrue(server.listen(QHostAddress.LocalHost, port))
        self.assertTrue(wait_until(lambda: len(texts) >= 3, timeout_s=6.0), "no WebSocket messages")
        self.assertIn("/objects/Drone A/ned/z", flatten(json.loads(texts[-1])))
        self.assertTrue(any(s.state == "connected" for s in self.stats))


class SettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = get_app()

    def test_editing_emits_the_config(self):
        from ui.dock.panels.settings_panel import SettingsPanel
        panel = SettingsPanel()
        seen = []
        panel.plot_stream_changed.connect(seen.append)
        panel.plot_enable_check.setChecked(True)
        self.assertTrue(seen[-1].enabled)
        self.assertEqual((seen[-1].transport, seen[-1].port), ("udp", 9870))
        panel.plot_transport_buttons["websocket"].click()
        self.assertEqual((seen[-1].transport, seen[-1].port), ("websocket", 9871))   # follows PJ's default
        panel.plot_port_spin.setValue(12000)
        panel.plot_transport_buttons["udp"].click()
        self.assertEqual(seen[-1].port, 12000)                                      # a custom port is kept
        panel.plot_source_checks["mavlink"].setChecked(False)
        self.assertFalse(seen[-1].mavlink)
        self.assertIn("UDP Server", panel.plot_help.text())

    def test_status_line(self):
        from services.plot_stream_service import PlotStreamStats
        from ui.dock.panels.settings_panel import SettingsPanel
        panel = SettingsPanel()
        panel.set_plot_stream_config(PlotStreamConfig(enabled=True, transport="websocket", port=9871))
        panel.show_plot_stream_stats(PlotStreamStats("connecting"))
        self.assertIn("Waiting for PlotJuggler", panel.plot_status.text())
        panel.show_plot_stream_stats(PlotStreamStats("connected", rate_hz=50))
        self.assertIn("50 msg/s", panel.plot_status.text())


if __name__ == "__main__":
    unittest.main()
