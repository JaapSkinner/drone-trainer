import struct
import unittest

from services.motion_capture_service import MotionCaptureService, MotionCaptureSource


class MotionCaptureServiceTests(unittest.TestCase):
    def test_parse_udp_packet_csv(self):
        data = b"drone1,1.0,2.0,3.0,0.1,0.2,0.3"
        pos = MotionCaptureService.parse_udp_packet(data, "fallback")
        self.assertIsNotNone(pos)
        self.assertEqual(pos.name, "drone1")
        self.assertAlmostEqual(pos.x, 1.0)
        self.assertAlmostEqual(pos.y, 2.0)
        self.assertAlmostEqual(pos.z, 3.0)
        self.assertAlmostEqual(pos.x_rot, 0.1)
        self.assertAlmostEqual(pos.y_rot, 0.2)
        self.assertAlmostEqual(pos.z_rot, 0.3)

    def test_parse_udp_packet_binary(self):
        payload = struct.pack("<6f", 4.0, 5.0, 6.0, 0.4, 0.5, 0.6)
        pos = MotionCaptureService.parse_udp_packet(payload, "fallback")
        self.assertIsNotNone(pos)
        self.assertEqual(pos.name, "fallback")
        self.assertAlmostEqual(pos.x, 4.0)
        self.assertAlmostEqual(pos.y, 5.0)
        self.assertAlmostEqual(pos.z, 6.0)
        self.assertAlmostEqual(pos.x_rot, 0.4)
        self.assertAlmostEqual(pos.y_rot, 0.5)
        self.assertAlmostEqual(pos.z_rot, 0.6)

    def test_configure_sets_source_and_network_fields(self):
        svc = MotionCaptureService()
        svc.configure(source="optitrack", address="127.0.0.1", port=1511, frequency_hz=120.0, tracked_object_name="cf1")
        cfg = svc.get_config()
        self.assertEqual(svc.source, MotionCaptureSource.OPTITRACK)
        self.assertEqual(cfg["source"], MotionCaptureSource.OPTITRACK.value)
        self.assertEqual(cfg["address"], "127.0.0.1")
        self.assertEqual(cfg["port"], 1511)
        self.assertAlmostEqual(cfg["frequency_hz"], 120.0)
        self.assertEqual(cfg["tracked_object_name"], "cf1")


if __name__ == "__main__":
    unittest.main()
