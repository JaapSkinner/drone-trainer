import math
import time
import unittest

from qt_test_utils import get_app

from models import frames
from models.mocap_calibration import MocapCalibration
from models.structs import MotionCaptureConfig
from services.motion_capture_service import MotionCaptureService
from services.object_service import ObjectService
from ui.dock.panels.mocap_calibration_dialog import MocapCalibrationDialog
from ui.dock.panels.motion_capture_panel import MotionCapturePanel

# The mocap world is yawed 30° and offset from the lab; this maps lab → reported (raw) positions.
TRUE = MocapCalibration(frames.quat_from_axis_angle((0, 1, 0), math.radians(30)), (2.0, 0.0, -3.0))
TO_MOCAP = TRUE.inverse()


def _close(a, b, tol=1e-6):
    return all(abs(x - y) < tol for x, y in zip(a, b))


class CalibrationDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = get_app()

    def setUp(self):
        self.service = MotionCaptureService()
        self.service._connected = True      # pretend a source is streaming
        self.dialog = MocapCalibrationDialog(self.service)
        self.place_wand((0.0, 0.0, 0.0))

    def tearDown(self):
        self.dialog.deleteLater()

    def place_wand(self, lab_position, jitter=0.0):
        """Feed samples as the mocap system would report the wand at a lab position."""
        raw = TO_MOCAP.apply_point(lab_position)
        for i in range(5):
            offset = jitter * (1 if i % 2 else -1)
            self.service._record_sample("wand", (raw[0] + offset, raw[1], raw[2], *frames.IDENTITY_QUAT),
                                        time.monotonic())
        self.dialog.on_subjects_updated(self.service.subjects_snapshot())

    def capture(self, purpose, lab_position, jitter=0.0):
        self.dialog.start_capture(purpose)
        self.place_wand(lab_position, jitter)
        self.service.update()   # capture window (1 s) not over yet
        self.service._finish_captures(float("inf"))

    def test_subject_list_and_live_readout(self):
        self.assertEqual(self.dialog.selected_subject(), "wand")
        self.assertIn("calibrated frame", self.dialog.live_label.text())
        self.assertTrue(self.dialog.origin_button.isEnabled())

    def test_origin_and_direction_aligns_the_frame(self):
        self.capture("origin", (0.0, 0.0, 0.0))
        self.assertIn("✓", self.dialog.origin_status.text())
        self.capture("direction", (1.5, 0.0, 0.0))
        cal = self.dialog.compute_origin_direction()
        self.assertIsNotNone(cal)
        for lab in [(0, 0, 0), (1, 0.5, 2), (-3, 1, 1)]:
            self.assertTrue(_close(self.service.get_calibration().apply_point(TO_MOCAP.apply_point(lab)), lab))
        # The manual tab shows the result for fine-tuning.
        self.assertAlmostEqual(self.dialog.rotation_spins[1].value(), 30.0, places=2)

    def test_origin_direction_needs_both_captures(self):
        self.capture("origin", (0.0, 0.0, 0.0))
        self.assertIsNone(self.dialog.compute_origin_direction())
        self.assertIn("Capture both", self.dialog.origin_error.text())

    def test_moving_during_capture_warns(self):
        self.capture("origin", (0.0, 0.0, 0.0), jitter=0.02)
        self.assertIn("moved", self.dialog.origin_status.text())

    def test_reference_points_fit(self):
        targets = [(0, 0, 0), (2, 0, 0), (2, 0, 2), (0, 0, 2)]
        for target in targets:
            self.capture("point", target)
            row = self.dialog.points_table.rowCount() - 1
            for col, value in enumerate(target):
                self.dialog.points_table.item(row, col + 1).setText(str(value))
        fit = self.dialog.solve_points()
        self.assertLess(fit.calibration.rms_error_m, 1e-6)
        self.assertIn("Fit error", self.dialog.points_status.text())
        self.assertTrue(_close(self.service.get_calibration().apply_point(TO_MOCAP.apply_point((1, 1, 1))),
                               (1, 1, 1)))

    def test_manual_edits_preview_immediately(self):
        self.dialog.offset_spins[1].setValue(-0.25)
        self.assertAlmostEqual(self.service.get_calibration().translation[1], -0.25)

    def test_cancel_restores_and_apply_keeps(self):
        original = self.service.get_calibration()
        self.dialog.offset_spins[0].setValue(1.0)
        self.dialog.reject()
        self.assertEqual(self.service.get_calibration().translation, original.translation)

        dialog = MocapCalibrationDialog(self.service)
        applied = []
        dialog.calibration_applied.connect(applied.append)
        dialog.offset_spins[0].setValue(1.0)
        dialog.accept()
        self.assertEqual(self.service.get_calibration().translation[0], 1.0)
        self.assertEqual(applied[0].translation[0], 1.0)

    def test_reset_to_none(self):
        self.dialog.set_preview(MocapCalibration.from_manual((0, 10, 0), (1, 0, 0)))
        self.dialog.reset_button.click()
        self.assertTrue(self.service.get_calibration().is_identity)


class PanelCalibrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = get_app()

    def test_applying_saves_calibration_through_the_panel(self):
        service = MotionCaptureService(MotionCaptureConfig())
        panel = MotionCapturePanel(motion_capture_service=service, object_service=ObjectService())
        saved = []
        panel.config_changed.connect(saved.append)
        self.assertEqual(panel.calibration_label.text(), "None")

        dialog = panel.open_calibration()
        dialog.rotation_spins[1].setValue(90.0)
        dialog.accept()

        cal = MocapCalibration.from_dict(saved[-1].calibration)
        self.assertAlmostEqual(cal.euler_deg()[1], 90.0, places=4)
        self.assertIn("Y +90.0°", panel.calibration_label.text())
        panel.deleteLater()


if __name__ == "__main__":
    unittest.main()
