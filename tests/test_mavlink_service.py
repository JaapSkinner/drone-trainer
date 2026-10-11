import math
import time
import types
import unittest

from models import frames
from models.structs import MavlinkObjectConfig
from unittest import mock

from models.structs import MavlinkConnectionConfig
from services import mavlink_service
from services.mavlink_service import MavlinkService


class _FakeConnection:
    is_connected = True

    def __init__(self, name="Drone-1", system_id=1):
        self.mocap = []
        self.config = types.SimpleNamespace(name=name, system_id=system_id, linked_object_name="")

    def send_mocap_data(self, mocap):
        self.mocap.append(mocap)
        return True


class _Tracked:
    """A scene object receiving fresh motion capture."""

    def __init__(self, pose, name="obj"):
        self.pose = pose
        self.name = name
        self.mavlink_config = MavlinkObjectConfig()
        self.tracked = True
        self.pose_locked = False
        self.last_tracking_update = time.monotonic()


class MavlinkMocapTests(unittest.TestCase):
    def test_mocap_is_sent_in_ned_with_converted_attitude(self):
        service = MavlinkService()
        conn = _FakeConnection()
        service._connections[1] = conn

        # 2 m up, 1 m along +X, 3 m along +Z, nose yawed 90° about scene up.
        q_scene = frames.quat_from_axis_angle((0, 1, 0), math.pi / 2)
        service.register_mocap_source(1, _Tracked((1.0, 2.0, 3.0, *q_scene)))  # fresh tracking

        service._process_mocap()

        self.assertEqual(len(conn.mocap), 1)
        sent = conn.mocap[0]
        self.assertAlmostEqual(sent.x, 1.0)
        self.assertAlmostEqual(sent.y, 3.0)
        self.assertAlmostEqual(sent.z, -2.0)
        # Turning left (towards scene -Z, i.e. west) is a heading of -90° in NED.
        roll, pitch, yaw = frames.quat_to_euler_xyz(sent.q)
        self.assertAlmostEqual(roll, 0.0)
        self.assertAlmostEqual(pitch, 0.0)
        self.assertAlmostEqual(yaw, -math.pi / 2)


class MavlinkObjectLinkTests(unittest.TestCase):
    POSE = (0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0)

    def setUp(self):
        self.service = MavlinkService()
        self.drone1 = _FakeConnection("Drone-1", system_id=11)
        self.drone2 = _FakeConnection("Drone-2", system_id=12)
        self.service._connections = {11: self.drone1, 12: self.drone2}

    def test_linked_object_streams_to_its_named_connection(self):
        obj = _Tracked(self.POSE, "quad")
        self.service.link_object(obj, "Drone-2")
        self.service._process_mocap()
        self.assertEqual((len(self.drone1.mocap), len(self.drone2.mocap)), (0, 1))
        self.assertEqual(self.drone2.config.linked_object_name, "quad")

    def test_in_place_edits_take_effect(self):
        obj = _Tracked(self.POSE, "quad")
        self.service.link_object(obj, "Drone-1")
        obj.mavlink_config.enabled = False          # edited in place, as the UI does
        self.service.update_object_config(obj, obj.mavlink_config)
        self.service._process_mocap()
        self.assertEqual(self.drone1.mocap, [])

    def test_relinking_moves_the_stream_and_one_object_per_connection(self):
        a, b = _Tracked(self.POSE, "a"), _Tracked(self.POSE, "b")
        self.service.link_object(a, "Drone-1")
        self.service.link_object(a, "Drone-2")
        self.assertEqual(self.drone1.config.linked_object_name, "")
        self.service.link_object(b, "Drone-2")       # takes the connection from a
        self.assertEqual(a.mavlink_config.linked_connection_name, "")
        self.service._process_mocap()
        self.assertEqual((len(self.drone1.mocap), len(self.drone2.mocap)), (0, 1))

    def test_unregistering_stops_mocap(self):
        obj = _Tracked(self.POSE, "quad")
        self.service.link_object(obj, "Drone-1")
        self.service.unregister_mavlink_object(obj)
        self.service._process_mocap()
        self.assertEqual(self.drone1.mocap, [])

    def test_legacy_system_id_routing_still_works(self):
        obj = _Tracked(self.POSE, "quad")
        obj.mavlink_config = MavlinkObjectConfig(enabled=True, system_id=12)
        self.service.update_object_config(obj, obj.mavlink_config)
        self.service._process_mocap()
        self.assertEqual(len(self.drone2.mocap), 1)


class MocapSafetyTests(unittest.TestCase):
    """Only fresh motion capture may reach the vehicle as an external position."""
    POSE = (0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0)

    def setUp(self):
        self.service = MavlinkService()
        self.drone = _FakeConnection("Drone-1", system_id=11)
        self.service._connections = {11: self.drone}
        self.obj = _Tracked(self.POSE, "quad")
        self.service.link_object(self.obj, "Drone-1")

    def sent(self):
        self.drone.mocap.clear()
        self.service._process_mocap()
        return len(self.drone.mocap)

    def test_fresh_tracking_is_streamed(self):
        self.assertEqual(self.sent(), 1)
        self.assertEqual(self.service.mocap_stream_state(self.obj), "streaming")

    def test_untracked_object_is_not_streamed(self):
        self.obj.tracked = False
        self.assertEqual(self.sent(), 0)
        self.assertEqual(self.service.mocap_stream_state(self.obj), "not_tracked")

    def test_lost_tracking_pauses_the_stream(self):
        self.obj.last_tracking_update = time.monotonic() - 1.0
        self.assertEqual(self.sent(), 0)
        self.assertEqual(self.service.mocap_stream_state(self.obj), "tracking_lost")

    def test_locked_pose_is_not_streamed(self):
        self.obj.pose_locked = True
        self.assertEqual(self.sent(), 0)

    def test_simulation_override_streams_untracked_poses(self):
        self.obj.tracked = False
        self.obj.mavlink_config.send_mocap_untracked = True
        self.assertEqual(self.sent(), 1)


def _fake_connect(heartbeat_system_id=7, succeed=True):
    """Replacement for MavlinkConnection.connect that needs no vehicle."""
    def connect(self):
        if not succeed:
            return False
        self.status.system_id = heartbeat_system_id
        self.config.system_id = heartbeat_system_id
        self.status.connected = True
        self.status.last_heartbeat = time.time()
        self._state = mavlink_service.ConnectionState.CONNECTED
        return True
    return connect


class ConnectionWorkflowTests(unittest.TestCase):
    def setUp(self):
        self._patch = mock.patch.object(mavlink_service.MavlinkConnection, "connect", _fake_connect())
        self._patch.start()
        self.service = MavlinkService()

    def tearDown(self):
        self._patch.stop()

    def test_reconnecting_a_saved_connection_keeps_its_name(self):
        self.service.save_connection_config(MavlinkConnectionConfig("udpin:0.0.0.0:14550", name="Drone-1"))
        saved = self.service.get_all_connections()["Drone-1"]
        self.assertTrue(self.service.add_connection(saved))
        self.assertIsNotNone(self.service.get_connection_by_name("Drone-1"))
        self.assertEqual(sorted(self.service.get_all_connections()), ["Drone-1"])

    def test_renaming_a_connection_keeps_object_links(self):
        self.service.add_connection(MavlinkConnectionConfig("udpin:0.0.0.0:14550", name="Drone-1"))
        obj = _Tracked((0, 0, 0, 1, 0, 0, 0), "quad")
        self.service.link_object(obj, "Drone-1")
        self.assertTrue(self.service.rename_connection(7, "Lab quad"))
        self.assertEqual(obj.mavlink_config.linked_connection_name, "Lab quad")
        self.assertEqual(self.service.mocap_stream_state(obj), "streaming")


class AsyncConnectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from qt_test_utils import get_app
        cls.app = get_app()

    def connect_with(self, **fake):
        patch = mock.patch.object(mavlink_service.MavlinkConnection, "connect", _fake_connect(**fake))
        patch.start()
        self.addCleanup(patch.stop)

    def attempt(self, service, config):
        from qt_test_utils import wait_until
        results = []
        service.connection_attempt_finished.connect(lambda *args: results.append(args))
        name = service.add_connection_async(config)
        self.assertTrue(wait_until(lambda: results, timeout_s=3.0))
        return name, results[0]

    def test_background_connect_reports_success(self):
        self.connect_with(heartbeat_system_id=3)
        service = MavlinkService()
        name, (reported, ok, message) = self.attempt(service, MavlinkConnectionConfig("udpin:0.0.0.0:14550", name="Quad"))
        self.assertEqual((name, reported, ok, message), ("Quad", "Quad", True, ""))
        self.assertTrue(service.get_connection_by_name("Quad").is_connected)
        self.assertFalse(service.is_connecting("Quad"))

    def test_failed_connect_explains_and_frees_the_socket(self):
        self.connect_with(succeed=False)
        service = MavlinkService()
        with mock.patch.object(mavlink_service.MavlinkConnection, "disconnect") as disconnect:
            _name, (_n, ok, message) = self.attempt(service, MavlinkConnectionConfig("udpin:0.0.0.0:14551"))
        self.assertFalse(ok)
        self.assertIn("No heartbeat", message)
        disconnect.assert_called()

    def test_second_vehicle_with_the_same_system_id_is_refused(self):
        self.connect_with(heartbeat_system_id=1)
        service = MavlinkService()
        self.assertTrue(service.add_connection(MavlinkConnectionConfig("udpin:0.0.0.0:14550", name="A")))
        _name, (_n, ok, message) = self.attempt(service, MavlinkConnectionConfig("udpin:0.0.0.0:14560", name="B"))
        self.assertFalse(ok)
        self.assertIn("MAV_SYS_ID", message)
        self.assertEqual(service.get_connection_by_name("A").config.connection_string, "udpin:0.0.0.0:14550")

    def test_auto_reconnect_restores_saved_connections_but_respects_user_disconnect(self):
        from qt_test_utils import wait_until
        self.connect_with(heartbeat_system_id=4)
        service = MavlinkService()
        service.save_connection_config(MavlinkConnectionConfig("udpin:0.0.0.0:14550", name="Quad"))
        service._auto_reconnect()
        self.assertTrue(wait_until(lambda: service.get_connection_by_name("Quad") is not None, timeout_s=3.0))

        service.disconnect_by_user(4)
        service._auto_reconnect()
        self.assertFalse(service.is_connecting("Quad"))
        self.assertIsNone(service.get_connection_by_name("Quad"))
        self.assertFalse(service.get_all_connections()["Quad"].auto_connect)


if __name__ == "__main__":
    unittest.main()
