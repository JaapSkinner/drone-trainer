import math
import unittest

from models import frames
from services.mavlink_service import MavlinkService


class _FakeConnection:
    is_connected = True

    def __init__(self):
        self.mocap = []

    def send_mocap_data(self, mocap):
        self.mocap.append(mocap)
        return True


class _Tracked:
    def __init__(self, pose):
        self.pose = pose


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


if __name__ == "__main__":
    unittest.main()
