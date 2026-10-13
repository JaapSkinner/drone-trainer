"""One link, several talkers: a vehicle, QGroundControl, a gimbal, a second vehicle.

Messages are real MAVLink packets (encoded and decoded with pymavlink), so the
source system/component in their headers is exactly what a link would see.
"""
import time
import unittest
from unittest import mock

from pymavlink.dialects.v20 import common as mavlink2

from models.structs import MavlinkConnectionConfig
from services import mavlink_service
from services.mavlink_service import MavlinkConnection

M = mavlink2


def packet(system, component, encode):
    """A decoded message as received from (system, component)."""
    sender = M.MAVLink(None, srcSystem=system, srcComponent=component)
    buf = encode(sender).pack(sender)
    receiver = M.MAVLink(None)
    msg = receiver.parse_buffer(buf)[0]
    return msg


def vehicle_heartbeat(system=1, armed=False):
    base_mode = M.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED | (M.MAV_MODE_FLAG_SAFETY_ARMED if armed else 0)
    return packet(system, 1, lambda m: m.heartbeat_encode(M.MAV_TYPE_QUADROTOR, M.MAV_AUTOPILOT_PX4,
                                                           base_mode, 0, M.MAV_STATE_ACTIVE))


def gcs_heartbeat(system=255, component=190):
    return packet(system, component, lambda m: m.heartbeat_encode(M.MAV_TYPE_GCS, M.MAV_AUTOPILOT_INVALID,
                                                                    0, 0, M.MAV_STATE_ACTIVE))


def gimbal_heartbeat(system=1):
    return packet(system, 154, lambda m: m.heartbeat_encode(M.MAV_TYPE_GIMBAL, M.MAV_AUTOPILOT_INVALID,
                                                              0, 0, M.MAV_STATE_ACTIVE))


def attitude(system=1, roll=0.0):
    return packet(system, 1, lambda m: m.attitude_encode(0, roll, 0.0, 0.0, 0.0, 0.0, 0.0))


class _Link:
    """Stands in for a pymavlink connection: hands out queued messages."""

    def __init__(self, messages=()):
        self.queue = list(messages)
        self.written = []
        self.mav = mock.MagicMock()

    def recv_match(self, blocking=False, timeout=None, type=None):
        while self.queue:
            msg = self.queue.pop(0)
            if type is None or msg.get_type() == type:
                return msg
        return None

    def write(self, data):
        self.written.append(bytes(data))

    def close(self):
        pass


def _connected(system_id=1):
    conn = MavlinkConnection(MavlinkConnectionConfig("udpin:0.0.0.0:14540"))
    conn.status.system_id = system_id
    conn.config.system_id = system_id
    conn.status.connected = True
    conn.status.last_heartbeat = time.time()
    conn._state = mavlink_service.ConnectionState.CONNECTED
    return conn


class VehicleOnlyTelemetryTests(unittest.TestCase):
    def test_qgc_heartbeats_do_not_keep_a_lost_vehicle_alive(self):
        conn = _connected()
        conn.status.last_heartbeat = time.time() - 10        # the vehicle went quiet…
        conn.process_message(gcs_heartbeat())                # …while QGC keeps talking
        self.assertFalse(conn.is_connected)

    def test_qgc_heartbeat_does_not_overwrite_the_armed_state(self):
        conn = _connected()
        conn.process_message(vehicle_heartbeat(armed=True))
        conn.process_message(gcs_heartbeat())
        self.assertTrue(conn.telemetry.armed)

    def test_other_components_do_not_count_as_the_vehicle(self):
        conn = _connected()
        conn.status.last_heartbeat = time.time() - 10
        conn.process_message(gimbal_heartbeat())
        self.assertFalse(conn.is_connected)

    def test_a_second_vehicle_on_the_link_is_not_mixed_in(self):
        conn = _connected(system_id=1)
        conn.process_message(attitude(system=1, roll=0.1))
        conn.process_message(attitude(system=2, roll=0.9))
        self.assertAlmostEqual(conn.telemetry.roll, 0.1, places=5)
        self.assertEqual(conn.other_systems(), {2})


class ConnectPicksTheVehicleTests(unittest.TestCase):
    def _connect(self, messages):
        link = _Link(messages)
        with mock.patch.object(mavlink_service.mavutil, "mavlink_connection", return_value=link), \
                mock.patch.object(MavlinkConnection, "_prime_connection"):
            conn = MavlinkConnection(MavlinkConnectionConfig("udpin:0.0.0.0:14540"))
            return conn, conn.connect()

    def test_ignores_gcs_and_component_heartbeats_until_the_autopilot_speaks(self):
        conn, ok = self._connect([gcs_heartbeat(), gimbal_heartbeat(system=3), vehicle_heartbeat(system=3)])
        self.assertTrue(ok)
        self.assertEqual(conn.status.system_id, 3)

    def test_only_a_gcs_means_no_vehicle(self):
        conn, ok = self._connect([gcs_heartbeat(), gcs_heartbeat()])
        self.assertFalse(ok)


class PacketLossTests(unittest.TestCase):
    def test_sequence_numbers_are_tracked_per_sender(self):
        conn = _connected()
        # Interleaved talkers each count their own sequence numbers; that's not packet loss.
        vehicle = M.MAVLink(None, srcSystem=1, srcComponent=1)
        qgc = M.MAVLink(None, srcSystem=255, srcComponent=190)
        receiver = M.MAVLink(None)
        stream = []
        for _ in range(5):
            for sender in (vehicle, qgc):
                buf = sender.heartbeat_encode(M.MAV_TYPE_QUADROTOR, M.MAV_AUTOPILOT_PX4, 0, 0, 0).pack(sender)
                sender.seq = (sender.seq + 1) % 256     # pack() alone doesn't advance it (send() does)
                stream += receiver.parse_buffer(buf)
        stream.append(stream[-1])                        # heard twice (two routes): not a loss either
        conn._connection = _Link(stream)
        conn.receive_messages(max_messages=100)
        self.assertEqual(conn.packets_dropped, 0)


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# Real links: UDP relaying to QGC, a serial port, our identity
# ---------------------------------------------------------------------------

import os  # noqa: E402
import socket  # noqa: E402
import sys  # noqa: E402

from models import mavlink_links  # noqa: E402
from models.structs import MavlinkGlobalSettings  # noqa: E402
from services.mavlink_service import MavlinkService  # noqa: E402


def _free_udp_port():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _read_packets(sock, parser, seconds=0.5):
    """Messages that arrive on a non-blocking UDP socket within ``seconds``."""
    messages, deadline = [], time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            data, _ = sock.recvfrom(65535)
        except BlockingIOError:
            time.sleep(0.005)
            continue
        messages += [m for m in parser.parse_buffer(data) or [] if m is not None]
    return messages


class _UdpVehicle:
    """A PX4-ish vehicle sending to the app's UDP port; reads what comes back."""

    def __init__(self, app_port, system=1):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.setblocking(False)
        self.app = ("127.0.0.1", app_port)
        self.mav = M.MAVLink(None, srcSystem=system, srcComponent=1)
        self.parser = M.MAVLink(None)

    def send(self, msg):
        self.sock.sendto(msg.pack(self.mav), self.app)
        self.mav.seq = (self.mav.seq + 1) % 256

    def heartbeat(self):
        self.send(self.mav.heartbeat_encode(M.MAV_TYPE_QUADROTOR, M.MAV_AUTOPILOT_PX4, 0, 0, M.MAV_STATE_ACTIVE))

    def received(self, seconds=0.5):
        return _read_packets(self.sock, self.parser, seconds)

    def close(self):
        self.sock.close()


def _connect_with_heartbeats(conn, vehicle, seconds=6.0):
    """conn.connect() blocks waiting for a heartbeat, so keep sending them from a thread."""
    import threading
    stop = threading.Event()

    def beat():
        while not stop.is_set():
            vehicle.heartbeat()
            time.sleep(0.1)
    thread = threading.Thread(target=beat, daemon=True)
    thread.start()
    try:
        return conn.connect()
    finally:
        stop.set()
        thread.join(1.0)


class RelayToQgcTests(unittest.TestCase):
    def test_vehicle_traffic_reaches_qgc_and_qgc_commands_reach_the_vehicle(self):
        app_port = _free_udp_port()
        qgc = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        qgc.bind(("127.0.0.1", 0))
        qgc.setblocking(False)
        self.addCleanup(qgc.close)
        qgc_addr = qgc.getsockname()
        vehicle = _UdpVehicle(app_port)
        self.addCleanup(vehicle.close)

        conn = MavlinkConnection(MavlinkConnectionConfig(f"udpin:127.0.0.1:{app_port}", name="quad1",
                                                         forward_to=f"127.0.0.1:{qgc_addr[1]}"))
        self.addCleanup(conn.disconnect)
        self.assertTrue(_connect_with_heartbeats(conn, vehicle))
        self.assertTrue(conn.forwarding)

        # Vehicle → app → QGC
        vehicle.send(vehicle.mav.attitude_encode(0, 0.25, 0.0, 0.0, 0.0, 0.0, 0.0))
        time.sleep(0.05)
        for _ in range(5):
            for msg in conn.receive_messages(max_messages=100):
                conn.process_message(msg)
        seen = _read_packets(qgc, M.MAVLink(None))
        self.assertIn("ATTITUDE", [m.get_type() for m in seen])
        self.assertAlmostEqual(conn.telemetry.roll, 0.25, places=5)

        # QGC → app → vehicle (QGC replies to the address the relayed packets came from)
        qgc_mav = M.MAVLink(None, srcSystem=255, srcComponent=190)
        command = qgc_mav.command_long_encode(1, 1, M.MAV_CMD_REQUEST_MESSAGE, 0, 33, 0, 0, 0, 0, 0, 0)
        relay_port = conn._forward_sock.getsockname()[1]
        qgc.sendto(command.pack(qgc_mav), ("127.0.0.1", relay_port))
        time.sleep(0.05)
        self.assertEqual(conn.pump_forward(), 1)
        got = [m for m in vehicle.received() if m.get_type() == "COMMAND_LONG"]
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0].get_srcSystem(), 255, "QGC's own identity is kept")

    def test_forward_target_is_optional(self):
        conn = MavlinkConnection(MavlinkConnectionConfig("udpin:127.0.0.1:1"))
        conn._open_forward()
        self.assertFalse(conn.forwarding)


@unittest.skipUnless(sys.platform.startswith("linux"), "uses a Linux pseudo-terminal as the serial port")
class SerialLinkTests(unittest.TestCase):
    def test_connects_over_a_serial_port_at_the_chosen_baud(self):
        import pty
        import threading
        master, slave = pty.openpty()
        self.addCleanup(os.close, master)
        self.addCleanup(os.close, slave)
        device = os.ttyname(slave)
        vehicle = M.MAVLink(None, srcSystem=7, srcComponent=1)
        stop = threading.Event()

        def beat():
            while not stop.is_set():
                buf = vehicle.heartbeat_encode(M.MAV_TYPE_QUADROTOR, M.MAV_AUTOPILOT_PX4, 0, 0, 0).pack(vehicle)
                vehicle.seq = (vehicle.seq + 1) % 256
                os.write(master, buf)
                time.sleep(0.1)
        thread = threading.Thread(target=beat, daemon=True)
        thread.start()
        self.addCleanup(stop.set)

        conn = MavlinkConnection(MavlinkConnectionConfig(f"{device},460800", name="usb"))
        self.addCleanup(conn.disconnect)
        self.assertTrue(conn.connect(), conn.last_error)
        self.assertEqual(conn.status.system_id, 7)
        self.assertEqual(int(conn._connection.baud), 460800)


class IdentityTests(unittest.TestCase):
    def test_connections_use_the_identity_from_settings(self):
        service = MavlinkService()
        service.update_global_settings(MavlinkGlobalSettings(source_system_id=200, source_component_id=191))
        config = MavlinkConnectionConfig("udpin:0.0.0.0:14540")
        service._apply_identity(config)
        self.assertEqual((config.source_system, config.source_component), (200, 191))

    def test_defaults_do_not_clash_with_qgroundcontrol(self):
        settings = MavlinkGlobalSettings()
        self.assertNotEqual(settings.source_system_id, 255)    # QGC's default system ID
        self.assertNotEqual(settings.source_component_id, 0)   # 0 means "all components"

    def test_heartbeats_go_out_with_our_identity(self):
        app_port = _free_udp_port()
        vehicle = _UdpVehicle(app_port)
        self.addCleanup(vehicle.close)
        conn = MavlinkConnection(MavlinkConnectionConfig(f"udpin:127.0.0.1:{app_port}", source_system=245,
                                                         source_component=190))
        self.addCleanup(conn.disconnect)
        self.assertTrue(_connect_with_heartbeats(conn, vehicle))
        conn.send_heartbeat()
        beats = [m for m in vehicle.received() if m.get_type() == "HEARTBEAT"]
        self.assertTrue(beats)
        self.assertEqual((beats[-1].get_srcSystem(), beats[-1].get_srcComponent()), (245, 190))
        self.assertEqual(beats[-1].type, M.MAV_TYPE_GCS)


class FailureMessageTests(unittest.TestCase):
    def test_busy_serial_port_says_who_to_close(self):
        text = MavlinkService.explain_connect_failure("COM3,57600", "could not open port 'COM3': "
                                                      "PermissionError(13, 'Access is denied.', None, 5)")
        self.assertIn("in use by another program", text)
        self.assertIn("Share with QGroundControl", text)

    def test_unplugged_and_wrong_baud(self):
        self.assertIn("plugged in", MavlinkService.explain_connect_failure(
            "/dev/ttyUSB0,57600", "[Errno 2] could not open port /dev/ttyUSB0: [Errno 2] No such file or directory"))
        self.assertIn("baud", MavlinkService.explain_connect_failure("COM4,57600", "no heartbeat"))

    def test_udp_mentions_sharing_the_port_with_qgc(self):
        self.assertIn("QGroundControl", MavlinkService.explain_connect_failure("udpin:0.0.0.0:14550"))


class LinkAddressTests(unittest.TestCase):
    def test_round_trips(self):
        for text in ("udpin:0.0.0.0:14540", "udpout:10.0.0.1:14550", "tcp:127.0.0.1:5760", "COM3,460800",
                     "/dev/ttyACM0,115200"):
            self.assertEqual(mavlink_links.parse_link(text).connection_string(), text)

    def test_serial_without_baud_gets_the_default(self):
        link = mavlink_links.parse_link("COM7")
        self.assertEqual((link.kind, link.device, link.baud), ("serial", "COM7", mavlink_links.DEFAULT_BAUD))

    def test_baud_suggestions(self):
        self.assertEqual(mavlink_links.suggest_baud("FT231X USB UART", "FTDI", 0x0403), 57600)
        self.assertEqual(mavlink_links.suggest_baud("PX4 FMU v5.x", "3D Robotics"), 115200)
        self.assertEqual(mavlink_links.suggest_baud("ExpressLRS TX", ""), 460800)

    def test_endpoints(self):
        self.assertEqual(mavlink_links.parse_endpoint("127.0.0.1:14550"), ("127.0.0.1", 14550))
        self.assertEqual(mavlink_links.parse_endpoint("192.168.1.5"), ("192.168.1.5", 14550))
        self.assertIsNone(mavlink_links.parse_endpoint("host:notaport"))
        self.assertIsNone(mavlink_links.parse_endpoint(""))


class LinkEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from qt_test_utils import get_app
        cls.app = get_app()

    def _editor(self, ports=()):
        from ui.widgets import link_editor
        with mock.patch.object(link_editor.mavlink_links, "list_serial_ports", return_value=list(ports)):
            return link_editor.LinkEditor()

    def test_network_and_serial_round_trip(self):
        editor = self._editor()
        for text in ("udpin:0.0.0.0:14540", "udpout:10.0.0.1:14550", "COM5,460800"):
            editor.setText(text)
            self.assertEqual(editor.text(), text)

    def test_picking_a_port_suggests_its_baud_and_turns_on_sharing(self):
        ports = [mavlink_links.SerialPortInfo("COM3", "FT231X USB UART", 57600),
                 mavlink_links.SerialPortInfo("COM9", "ExpressLRS TX", 460800)]
        editor = self._editor(ports)
        editor.kind_combo.setCurrentIndex(editor.kind_combo.findData("serial"))
        self.assertTrue(editor.share_check.isChecked(), "a serial port can't be opened by QGC too")
        editor.device_combo.setCurrentIndex(1)
        self.assertEqual(editor.text(), "COM9,460800")
        self.assertEqual(editor.forward_to(), mavlink_links.QGC_DEFAULT_FORWARD)

    def test_relaying_into_our_own_port_is_refused(self):
        editor = self._editor()
        editor.setText("udpin:0.0.0.0:14550")
        editor.set_forward_to("127.0.0.1:14550")
        self.assertIn("different port", editor.problem())
        editor.setText("udpin:0.0.0.0:14540")
        self.assertEqual(editor.problem(), "")

    def test_warns_that_qgc_listens_on_14550(self):
        editor = self._editor()
        editor.setText("udpin:0.0.0.0:14550")
        self.assertIn("QGroundControl also listens", editor.hint.text())

    def test_serial_needs_a_port(self):
        editor = self._editor()
        editor.setText("COM1,57600")
        editor.device_combo.setEditText("")
        self.assertIn("serial port", editor.problem())


class ServiceRelayTests(unittest.TestCase):
    """Relaying through the running service (its own thread and timers)."""

    @classmethod
    def setUpClass(cls):
        from qt_test_utils import get_app
        cls.app = get_app()

    def test_running_service_relays_to_qgc(self):
        from qt_test_utils import process_events_for, wait_until
        app_port = _free_udp_port()
        qgc = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        qgc.bind(("127.0.0.1", 0))
        qgc.setblocking(False)
        self.addCleanup(qgc.close)
        vehicle = _UdpVehicle(app_port)
        self.addCleanup(vehicle.close)

        service = MavlinkService()
        service.start()
        self.addCleanup(lambda: (service.stop(), process_events_for(0.1)))
        import threading
        stop = threading.Event()

        def beat():
            while not stop.is_set():
                vehicle.heartbeat()
                vehicle.send(vehicle.mav.attitude_encode(0, 0.3, 0.0, 0.0, 0.0, 0.0, 0.0))
                time.sleep(0.05)
        threading.Thread(target=beat, daemon=True).start()
        self.addCleanup(stop.set)

        results = []
        service.connection_attempt_finished.connect(lambda name, ok, message: results.append(ok))
        service.add_connection_async(MavlinkConnectionConfig(
            f"udpin:127.0.0.1:{app_port}", name="quad1", forward_to=f"127.0.0.1:{qgc.getsockname()[1]}"))
        self.assertTrue(wait_until(lambda: results, timeout_s=8.0))
        self.assertEqual(results, [True])
        parser, seen = M.MAVLink(None), []
        self.assertTrue(wait_until(lambda: seen.extend(_read_packets(qgc, parser, 0.05)) or
                                   "ATTITUDE" in [m.get_type() for m in seen], timeout_s=3.0))
        conn = service.get_connection_by_name("quad1")
        self.assertAlmostEqual(conn.telemetry.roll, 0.3, places=5)
