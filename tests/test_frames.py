import math
import random
import unittest

import numpy as np

from models import frames


def _close(a, b, tol=1e-9):
    return all(abs(x - y) < tol for x, y in zip(a, b))


class QuaternionTests(unittest.TestCase):
    def test_euler_round_trip(self):
        rng = random.Random(1)
        for _ in range(200):
            angles = (rng.uniform(-math.pi, math.pi),
                      rng.uniform(-1.4, 1.4),
                      rng.uniform(-math.pi, math.pi))
            back = frames.quat_to_euler_xyz(frames.euler_xyz_to_quat(*angles))
            self.assertTrue(_close(angles, back, 1e-9), (angles, back))

    def test_matrix_round_trip(self):
        rng = random.Random(2)
        for _ in range(200):
            q = frames.quat_normalize([rng.uniform(-1, 1) for _ in range(4)])
            q2 = frames.matrix_to_quat(frames.quat_to_matrix(q))
            self.assertTrue(frames.quats_equivalent(q, q2))

    def test_yaw_about_z_turns_x_towards_y(self):
        q = frames.euler_xyz_to_quat(0.0, 0.0, math.pi / 2)
        self.assertTrue(_close(frames.rotate_vector(q, (1, 0, 0)), (0, 1, 0)))

    def test_euler_order_is_roll_then_pitch_then_yaw_about_fixed_axes(self):
        roll, pitch, yaw = 0.3, -0.2, 1.1
        expected = (frames.quat_to_matrix(frames.quat_from_axis_angle((0, 0, 1), yaw))
                    @ frames.quat_to_matrix(frames.quat_from_axis_angle((0, 1, 0), pitch))
                    @ frames.quat_to_matrix(frames.quat_from_axis_angle((1, 0, 0), roll)))
        actual = frames.quat_to_matrix(frames.euler_xyz_to_quat(roll, pitch, yaw))
        self.assertTrue(np.allclose(actual, expected))


class FrameTransformTests(unittest.TestCase):
    def test_rejects_mirroring(self):
        with self.assertRaises(ValueError):
            frames.FrameTransform(np.diag([1.0, 1.0, -1.0]))

    def test_inverse_round_trip(self):
        pose = (1.0, 2.0, 3.0, *frames.euler_xyz_to_quat(0.1, 0.2, 0.3))
        back = frames.NED_TO_SCENE.pose(frames.SCENE_TO_NED.pose(pose))
        self.assertTrue(_close(back[:3], pose[:3]))
        self.assertTrue(frames.quats_equivalent(back[3:], pose[3:]))


class ViconToSceneTests(unittest.TestCase):
    def test_position_mm_to_scene_metres_y_up(self):
        pose = frames.vicon_to_scene_pose((1000.0, 2000.0, 3000.0), (0.0, 0.0, 0.0))
        self.assertTrue(_close(pose[:3], (1.0, 3.0, -2.0)))
        self.assertTrue(frames.quats_equivalent(pose[3:], frames.IDENTITY_QUAT))

    def test_vicon_up_stays_up_for_any_yaw(self):
        for yaw in (0.0, 0.7, -2.0, math.pi):
            pose = frames.vicon_to_scene_pose((0, 0, 0), (0.0, 0.0, yaw))
            self.assertTrue(_close(frames.rotate_vector(pose[3:], (0, 1, 0)), (0, 1, 0)))

    def test_vicon_yaw_left_points_nose_at_scene_minus_z(self):
        # Vicon +Y is scene -Z; yawing +90° turns the nose from Vicon +X to +Y.
        pose = frames.vicon_to_scene_pose((0, 0, 0), (0.0, 0.0, math.pi / 2))
        self.assertTrue(_close(frames.rotate_vector(pose[3:], (1, 0, 0)), (0, 0, -1)))


class SceneToNedTests(unittest.TestCase):
    def test_height_becomes_negative_down(self):
        position, q = frames.scene_pose_to_ned((1.0, 2.0, 3.0, *frames.IDENTITY_QUAT))
        self.assertTrue(_close(position, (1.0, 3.0, -2.0)))
        self.assertTrue(frames.quats_equivalent(q, frames.IDENTITY_QUAT))

    def test_vicon_to_ned_is_flu_to_frd(self):
        # Vicon (X fwd, Y left, Z up) → NED (X north, Y east, Z down).
        scene = frames.vicon_to_scene_pose((1000.0, 2000.0, 3000.0), (0.0, 0.0, 0.0))
        position, _ = frames.scene_pose_to_ned(scene)
        self.assertTrue(_close(position, (1.0, -2.0, -3.0)))

    def test_attitude_signs_follow_frd_conventions(self):
        # Vicon yaw +90° (counter-clockwise seen from above) is a heading of -90° in NED.
        _, q = frames.scene_pose_to_ned(frames.vicon_to_scene_pose((0, 0, 0), (0, 0, math.pi / 2)))
        self.assertTrue(_close(frames.quat_to_euler_xyz(q), (0.0, 0.0, -math.pi / 2)))

        # Vicon roll +10° about the forward axis lifts the left wing: positive FRD roll.
        _, q = frames.scene_pose_to_ned(frames.vicon_to_scene_pose((0, 0, 0), (math.radians(10), 0, 0)))
        self.assertTrue(_close(frames.quat_to_euler_xyz(q), (math.radians(10), 0.0, 0.0)))

        # Vicon pitch +10° about the left axis drops the nose: negative FRD pitch.
        _, q = frames.scene_pose_to_ned(frames.vicon_to_scene_pose((0, 0, 0), (0, math.radians(10), 0)))
        self.assertTrue(_close(frames.quat_to_euler_xyz(q), (0.0, -math.radians(10), 0.0)))


class OptiTrackTests(unittest.TestCase):
    def test_y_up_is_identity_and_quaternion_order_is_xyzw(self):
        q_xyzw = (0.0, math.sin(0.25), 0.0, math.cos(0.25))  # 0.5 rad about +Y
        pose = frames.optitrack_to_scene_pose((1.0, 2.0, 3.0), q_xyzw)
        self.assertTrue(_close(pose[:3], (1.0, 2.0, 3.0)))
        self.assertTrue(frames.quats_equivalent(pose[3:], (math.cos(0.25), 0.0, math.sin(0.25), 0.0)))

    def test_z_up_matches_vicon_axes(self):
        pose = frames.optitrack_to_scene_pose((1.0, 2.0, 3.0), (0, 0, 0, 1), up_axis="z")
        self.assertTrue(_close(pose[:3], (1.0, 3.0, -2.0)))


class GlMatrixTests(unittest.TestCase):
    def test_translation_is_in_the_last_row_for_column_major_upload(self):
        m = frames.gl_model_matrix((1.0, 2.0, 3.0, *frames.IDENTITY_QUAT))
        self.assertTrue(np.allclose(m[3, :3], (1.0, 2.0, 3.0)))


if __name__ == "__main__":
    unittest.main()
