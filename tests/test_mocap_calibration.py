import math
import random
import unittest

import numpy as np

from models import frames
from models.mocap_calibration import (CalibrationError, MocapCalibration, solve_origin_direction,
                                      solve_reference_points)


def _close(a, b, tol=1e-6):
    return all(abs(x - y) < tol for x, y in zip(a, b))


# A "lab truth": the mocap world is rotated 30° about vertical and its origin sits
# in a corner, 2 m / 3 m away and 0.1 m below the lab floor origin.
TRUE = MocapCalibration(frames.quat_from_axis_angle((0, 1, 0), math.radians(30)), (2.0, 0.1, -3.0))
TO_MOCAP = TRUE.inverse()   # lab position → what the mocap system reports


class MocapCalibrationTests(unittest.TestCase):
    def test_apply_and_inverse(self):
        pose = (1.0, 2.0, 3.0, *frames.quat_from_axis_angle((1, 0, 0), 0.3))
        back = TRUE.inverse().apply(TRUE.apply(pose))
        self.assertTrue(_close(back[:3], pose[:3]))
        self.assertTrue(frames.quats_equivalent(back[3:], pose[3:]))

    def test_identity_leaves_poses_untouched(self):
        pose = (1.0, 2.0, 3.0, 1.0, 0.0, 0.0, 0.0)
        self.assertTrue(MocapCalibration().is_identity)
        self.assertEqual(MocapCalibration().apply(pose), pose)

    def test_orientation_is_rotated_too(self):
        cal = MocapCalibration(frames.quat_from_axis_angle((0, 1, 0), math.pi / 2), (0, 0, 0))
        pose = cal.apply((0, 0, 0, *frames.IDENTITY_QUAT))
        # A body facing +X now faces where +X maps under a 90° turn about +Y: -Z.
        self.assertTrue(_close(frames.rotate_vector(pose[3:], (1, 0, 0)), (0, 0, -1)))

    def test_manual_and_round_trip_through_dict(self):
        cal = MocapCalibration.from_manual((0.0, 15.0, 0.0), (0.5, 0.0, -0.25))
        self.assertTrue(_close(cal.euler_deg(), (0.0, 15.0, 0.0)))
        back = MocapCalibration.from_dict(cal.to_dict())
        self.assertTrue(frames.quats_equivalent(back.rotation, cal.rotation))
        self.assertEqual(back.translation, (0.5, 0.0, -0.25))
        self.assertEqual(back.method, "manual")
        self.assertTrue(MocapCalibration.from_dict(None).is_identity)


class OriginDirectionTests(unittest.TestCase):
    def test_recovers_origin_and_axis(self):
        origin_lab, along_x_lab = (0.0, 0.05, 0.0), (1.5, 0.05, 0.0)  # object 5 cm tall
        cal = solve_origin_direction(TO_MOCAP.apply_point(origin_lab), TO_MOCAP.apply_point(along_x_lab),
                                     origin_height_m=0.05)
        for lab_point in [(0, 0, 0), (1, 2, 3), (-2, 0.5, 4)]:
            self.assertTrue(_close(cal.apply_point(TO_MOCAP.apply_point(lab_point)), lab_point, 1e-9))

    def test_keeps_vertical_even_if_direction_point_is_higher(self):
        cal = solve_origin_direction((0, 0, 0), (1.0, 0.7, 1.0))
        self.assertTrue(_close(frames.rotate_vector(cal.rotation, (0, 1, 0)), (0, 1, 0)))
        self.assertTrue(_close(cal.apply_point((1.0, 0.0, 1.0)), (math.sqrt(2), 0.0, 0.0)))

    def test_rejects_too_small_a_move(self):
        with self.assertRaises(CalibrationError):
            solve_origin_direction((0, 0, 0), (0.05, 1.0, 0.05))


class ReferencePointTests(unittest.TestCase):
    TARGETS = [(0, 0, 0), (2, 0, 0), (2, 0, 2), (0, 0, 2), (1, 1.5, 1)]

    def _measured(self, noise=0.0, transform=TO_MOCAP):
        rng = random.Random(3)
        return [tuple(c + rng.gauss(0, noise) for c in transform.apply_point(t)) for t in self.TARGETS]

    def test_full_fit_recovers_the_transform(self):
        fit = solve_reference_points(self._measured(), self.TARGETS, keep_vertical=False)
        self.assertLess(fit.calibration.rms_error_m, 1e-9)
        self.assertTrue(frames.quats_equivalent(fit.calibration.rotation, TRUE.rotation, tol=1e-9))
        self.assertTrue(_close(fit.calibration.translation, TRUE.translation, 1e-9))

    def test_noisy_points_fit_within_noise(self):
        fit = solve_reference_points(self._measured(noise=0.002), self.TARGETS, keep_vertical=False)
        self.assertLess(fit.calibration.rms_error_m, 0.005)
        self.assertEqual(len(fit.residuals_m), len(self.TARGETS))
        yaw = fit.calibration.euler_deg()[1]
        self.assertAlmostEqual(yaw, 30.0, delta=0.5)

    def test_tilted_mocap_needs_full_fit(self):
        tilted = MocapCalibration(frames.euler_deg_to_quat(3.0, 30.0, 0.0), (2.0, 0.1, -3.0)).inverse()
        measured = self._measured(transform=tilted)
        yaw_only = solve_reference_points(measured, self.TARGETS, keep_vertical=True)
        full = solve_reference_points(measured, self.TARGETS, keep_vertical=False)
        self.assertGreater(yaw_only.calibration.rms_error_m, 0.01)  # can't explain the tilt
        self.assertLess(full.calibration.rms_error_m, 1e-9)

    def test_two_points_give_yaw_and_offset(self):
        fit = solve_reference_points(self._measured()[:2], self.TARGETS[:2], keep_vertical=False)
        self.assertLess(fit.calibration.rms_error_m, 1e-9)
        self.assertAlmostEqual(fit.calibration.euler_deg()[1], 30.0, places=6)

    def test_one_point_gives_offset_only(self):
        fit = solve_reference_points([(1.0, 2.0, 3.0)], [(0.0, 0.0, 0.0)])
        self.assertFalse(fit.calibration.is_identity)
        self.assertTrue(_close(fit.calibration.translation, (-1.0, -2.0, -3.0)))
        self.assertTrue(frames.quats_equivalent(fit.calibration.rotation, frames.IDENTITY_QUAT))

    def test_degenerate_inputs_are_rejected(self):
        with self.assertRaises(CalibrationError):
            solve_reference_points([], [])
        with self.assertRaises(CalibrationError):
            solve_reference_points([(0, 0, 0)], [(0, 0, 0), (1, 0, 0)])
        with self.assertRaises(CalibrationError):  # vertical line: no horizontal direction
            solve_reference_points([(0, 0, 0), (0, 1, 0)], [(0, 0, 0), (0, 1, 0)])
        line = [(0, 0, 0), (1, 0, 0), (2, 0, 0)]
        with self.assertRaises(CalibrationError):
            solve_reference_points(line, line, keep_vertical=False)

    def test_never_mirrors(self):
        fit = solve_reference_points(self._measured(noise=0.01), self.TARGETS, keep_vertical=False)
        self.assertAlmostEqual(np.linalg.det(frames.quat_to_matrix(fit.calibration.rotation)), 1.0)


if __name__ == "__main__":
    unittest.main()
