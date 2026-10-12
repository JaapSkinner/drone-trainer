import math
import socket
import struct
import types
import unittest

from qt_test_utils import THREAD_VIOLATION_MARKERS, QtMessageCapture, get_app, wait_until

from models import frames
from models.rect_prism import RectPrism
from models.structs import MotionCaptureConfig
from services.motion_capture import vicon_udp
from services.motion_capture.filters import PoseLowPass
from services.motion_capture.optitrack import OptiTrackSource
from models.mocap_calibration import MocapCalibration
from services.motion_capture_service import MotionCaptureService
from services.object_service import ObjectService
from services.service_base import ServiceLevel


def _reference_decode(b):
    """The parsing loop from the lab's ViconInterface.main_loop (feature/13), verbatim
    apart from returning results instead of filtering and storing them."""
    out = []
    FrameNumber = int.from_bytes(b[0:4], byteorder='little')
    ItemsInBlock = b[4]
    byte_offset = 5
    for i in range(0, ItemsInBlock):
        ItemID = b[byte_offset]
        byte_offset += 1
        ItemDataSize = int.from_bytes(b[byte_offset:byte_offset + 2], byteorder='little')
        byte_offset += 2
        ItemData = b[byte_offset:byte_offset + ItemDataSize]
        byte_offset += ItemDataSize
        if (ItemID == 0):
            name = str(ItemData[0:24], 'utf-8').strip('\x00')
            data = struct.unpack('d d d d d d', ItemData[24:72])
            out.append((name, data))
    return FrameNumber, out


def _free_udp_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class ViconProtocolTests(unittest.TestCase):
    def test_built_packets_decode_with_the_lab_reference_parser(self):
        packet = vicon_udp.build_packet(1234, [
            ("cf1", (1000.0, -250.5, 980.0), (0.01, -0.02, 1.5)),
            ("wand", (0.0, 1.0, 2.0), (0.0, 0.0, 0.0)),
        ])
        frame_number, objects = _reference_decode(packet)
        self.assertEqual(frame_number, 1234)
        self.assertEqual(objects, [
            ("cf1", (1000.0, -250.5, 980.0, 0.01, -0.02, 1.5)),
            ("wand", (0.0, 1.0, 2.0, 0.0, 0.0, 0.0)),
        ])

    def test_parses_hand_built_packet_and_skips_unknown_items(self):
        packet = (struct.pack("<IB", 42, 2)
                  + struct.pack("<BH", 7, 4) + b"\x01\x02\x03\x04"           # unknown item
                  + struct.pack("<BH", 0, 72) + b"gate1".ljust(24, b"\x00")
                  + struct.pack("<6d", 1.0, 2.0, 3.0, 0.1, 0.2, 0.3))
        frame = vicon_udp.parse_packet(packet)
        self.assertEqual(frame.frame_number, 42)
        self.assertEqual(len(frame.objects), 1)
        obj = frame.objects[0]
        self.assertEqual(obj.name, "gate1")
        self.assertEqual(obj.translation_mm, (1.0, 2.0, 3.0))
        self.assertEqual(obj.rotation_rad, (0.1, 0.2, 0.3))
        self.assertFalse(obj.occluded)

    def test_truncated_packets_are_rejected(self):
        packet = vicon_udp.build_packet(1, [("cf1", (1, 2, 3), (0, 0, 0))])
        for cut in (3, 6, len(packet) - 1):
            with self.assertRaises(vicon_udp.ViconPacketError):
                vicon_udp.parse_packet(packet[:cut])

    def test_all_zero_samples_are_occluded(self):
        frame = vicon_udp.parse_packet(vicon_udp.build_packet(1, [("cf1", (0, 0, 0), (0, 0, 0))]))
        self.assertTrue(frame.objects[0].occluded)


class FilterTests(unittest.TestCase):
    def test_first_sample_passes_and_steps_converge(self):
        f = PoseLowPass(cutoff_hz=5.0)
        start = (0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0)
        self.assertEqual(f.update(start, 0.0), start)
        target_q = frames.quat_from_axis_angle((0, 1, 0), 1.0)
        target = (1.0, 0.0, 0.0, *target_q)
        out = start
        for i in range(1, 400):
            out = f.update(target, i * 0.005)
            if i == 1:
                self.assertLess(out[0], 0.5)  # smoothed, not a jump
        self.assertAlmostEqual(out[0], 1.0, places=3)
        self.assertTrue(frames.quats_equivalent(out[3:], target_q, tol=1e-4))


class _Desc:
    def __init__(self, id_num, name):
        self.id_num, self.sz_name = id_num, name


class _Body:
    def __init__(self, id_num, pos, rot, valid=True):
        self.id_num, self.pos, self.rot, self.tracking_valid = id_num, pos, rot, valid


class OptiTrackAdapterTests(unittest.TestCase):
    def test_rigid_bodies_are_named_from_model_definitions(self):
        samples = []
        source = OptiTrackSource(lambda name, pose, t: samples.append((name, pose)))
        source.handle_descriptions(types.SimpleNamespace(rigid_body_list=[_Desc(3, b"gate")]))

        half = math.sqrt(0.5)
        frame = {"mocap_data": types.SimpleNamespace(rigid_body_data=types.SimpleNamespace(rigid_body_list=[
            _Body(3, (1.0, 2.0, 3.0), (0.0, half, 0.0, half)),      # 90° about +Y, xyzw order
            _Body(4, (9.0, 9.0, 9.0), (0.0, 0.0, 0.0, 1.0)),       # not in definitions yet
            _Body(5, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0), valid=False),
        ]))}
        source.handle_frame(frame)

        self.assertEqual([name for name, _ in samples], ["gate", "rigid_body_4"])
        pose = samples[0][1]
        self.assertEqual(pose[:3], (1.0, 2.0, 3.0))
        self.assertTrue(frames.quats_equivalent(pose[3:], (half, 0.0, half, 0.0)))


class MotionCaptureServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = get_app()

    def test_vicon_udp_end_to_end_moves_tracked_objects(self):
        port = _free_udp_port()
        service = MotionCaptureService(MotionCaptureConfig(vicon_address="127.0.0.1", vicon_port=port))
        objects = ObjectService()
        drone = objects.add_object(RectPrism(name="Drone"))
        drone.set_tracked(True, "cf1")
        batches, connection_events = [], []
        service.poses_updated.connect(batches.append)
        service.poses_updated.connect(objects.apply_tracking_poses)
        service.connection_changed.connect(connection_events.append)

        sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        with QtMessageCapture() as capture:
            service.start()
            try:
                self.assertTrue(wait_until(lambda: service._timer is not None))
                service.connect_source()
                self.assertTrue(wait_until(service.is_connected))
                self.assertEqual(service.status, ServiceLevel.WARNING)  # waiting for data

                sample = ((1000.0, 2000.0, 3000.0), (0.0, 0.0, math.pi / 2))
                expected = frames.vicon_to_scene_pose(*sample)

                def send_and_check():
                    sender.sendto(vicon_udp.build_packet(1, [("cf1", *sample), ("wand", (5, 5, 5), (0, 0, 0))]),
                                  ("127.0.0.1", port))
                    return any("cf1" in b for b in batches)

                self.assertTrue(wait_until(send_and_check, timeout_s=3.0))
                received = next(b["cf1"] for b in batches if "cf1" in b)
                for got, want in zip(received, expected):
                    self.assertAlmostEqual(got, want)
                for got, want in zip(drone.pose, expected):
                    self.assertAlmostEqual(got, want)

                # Status reflects live data once the UI refresh has run.
                self.assertTrue(wait_until(lambda: send_and_check() and service.status == ServiceLevel.RUNNING,
                                           timeout_s=3.0))
                names = [s.name for s in service.subjects_snapshot()]
                self.assertEqual(names, ["cf1", "wand"])

                service.disconnect_source()
                self.assertTrue(wait_until(lambda: not service.is_connected()))
                self.assertEqual(service.status, ServiceLevel.STOPPED)
                # connection_changed is queued from the service thread, so it can land a moment later.
                wait_until(lambda: connection_events == [True, False])
                self.assertEqual(connection_events, [True, False])
            finally:
                service.stop()
                sender.close()
        self.assertEqual(capture.matching(*THREAD_VIOLATION_MARKERS), [])

        # The port was released.
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.bind(("127.0.0.1", port))
        probe.close()

    def test_bind_failure_reports_error(self):
        service = MotionCaptureService(MotionCaptureConfig(vicon_address="256.0.0.1", vicon_port=51001))
        service.start()
        try:
            self.assertTrue(wait_until(lambda: service._timer is not None))
            service.connect_source()
            self.assertTrue(wait_until(lambda: service.status == ServiceLevel.ERROR))
            self.assertFalse(service.is_connected())
            self.assertIn("could not listen", service.status_text)
        finally:
            service.stop()


class MotionCaptureCalibrationTests(unittest.TestCase):
    POSE = (1.0, 0.5, 2.0, *frames.IDENTITY_QUAT)

    def test_published_poses_are_calibrated_and_raw_pose_is_kept(self):
        cal = MocapCalibration(frames.quat_from_axis_angle((0, 1, 0), math.pi / 2), (0.0, 0.0, 1.0))
        service = MotionCaptureService(MotionCaptureConfig(calibration=cal.to_dict()))
        batches = []
        service.poses_updated.connect(batches.append)
        service._record_sample("wand", self.POSE, 1.0)
        service.update()

        expected = cal.apply(self.POSE)
        for got, want in zip(batches[0]["wand"], expected):
            self.assertAlmostEqual(got, want)
        info = service.subjects_snapshot()[0]
        self.assertEqual(info.raw_pose, self.POSE)
        for got, want in zip(info.pose, expected):
            self.assertAlmostEqual(got, want)

    def test_set_calibration_takes_effect_and_is_saved_in_config(self):
        service = MotionCaptureService()
        cal = MocapCalibration.from_manual((0, 0, 0), (0.0, -0.5, 0.0))
        service.set_calibration(cal)
        service._record_sample("wand", self.POSE, 1.0)
        self.assertAlmostEqual(service.subjects_snapshot()[0].pose[1], 0.0)
        self.assertEqual(MocapCalibration.from_dict(service.get_config().calibration).translation,
                         (0.0, -0.5, 0.0))

    def test_capture_averages_raw_positions(self):
        service = MotionCaptureService(MotionCaptureConfig(
            calibration=MocapCalibration.from_manual((0, 0, 0), (5, 5, 5)).to_dict()))
        results = []
        service.capture_finished.connect(results.append)
        service.capture_subject("wand", duration_s=0.0)
        for x in (0.99, 1.01, 1.00):
            service._record_sample("wand", (x, 0.5, 2.0, *frames.IDENTITY_QUAT), 1.0)
        service._record_sample("other", self.POSE, 1.0)
        service.update()

        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertTrue(result.ok)
        self.assertEqual(result.samples, 3)
        self.assertAlmostEqual(result.mean[0], 1.0)   # raw, not calibrated (+5)
        self.assertAlmostEqual(result.mean[1], 0.5)
        self.assertLess(result.std_m, 0.01)

    def test_capture_without_samples_reports_failure(self):
        service = MotionCaptureService()
        results = []
        service.capture_finished.connect(results.append)
        service.capture_subject("ghost", duration_s=0.0)
        service.update()
        self.assertFalse(results[0].ok)


if __name__ == "__main__":
    unittest.main()
