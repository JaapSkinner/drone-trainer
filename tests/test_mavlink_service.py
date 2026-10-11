import math
import types
import unittest

from models import frames
from models.structs import MavlinkObjectConfig
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
    def __init__(self, pose, name="obj"):
        self.pose = pose
        self.name = name
        self.mavlink_config = MavlinkObjectConfig()


class MavlinkMocapTests(unittest.TestCase):
    def test_mocap_is_sent_in_ned_with_converted_attitude(self):
        service = MavlinkService()
        conn = _FakeConnection()
        service._connections[1] = conn

        # 2 m up, 1 m along +X, 3 m along +Z, nose yawed 90° about scene up.
        q_scene = frames.quat_from_axis_angle((0, 1, 0), math.pi / 2)
        service.register_mocap_source(1, _Tracked((1.0, 2.0, 3.0, *q_scene)))

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


if __name__ == "__main__":
    unittest.main()
