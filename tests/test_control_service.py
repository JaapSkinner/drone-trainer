import math
import unittest

from qt_test_utils import get_app

from models import frames
from models.rect_prism import RectPrism
from services.control_service import ControlService
from services.object_service import ObjectService
from ui.gl_widget.setpoint_overlay import OVERLAP_ALPHA, SetpointOverlay

START = (0.0, 1.0, 0.0, *frames.IDENTITY_QUAT)


class ControlServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = get_app()

    def setUp(self):
        self.objects = ObjectService()
        self.box = self.objects.add_object(RectPrism(name="Box", dimensions=0.3))
        self.box.set_pose(START)
        self.control = ControlService(self.objects)
        self.control._timer.stop()   # tests drive tick() themselves
        self.control.sync_from_object(self.box)

    def test_normal_mode_edits_the_setpoint(self):
        self.control.move_target(self.box, (1.0, 0.0, 0.0))
        self.assertEqual(self.control.setpoint(self.box)[:3], (1.0, 1.0, 0.0))
        self.assertFalse(self.control.has_pending_ghost(self.box))

    def test_ghost_mode_edits_the_ghost_until_committed(self):
        self.control.set_ghost_mode(True)
        self.control.move_target(self.box, (0.0, 0.5, 0.0))
        self.assertEqual(self.control.setpoint(self.box)[:3], (0.0, 1.0, 0.0))
        self.assertEqual(self.control.ghost(self.box)[:3], (0.0, 1.5, 0.0))
        self.assertTrue(self.control.has_pending_ghost(self.box))
        self.assertEqual(self.control.commit_ghost(self.box)[:3], (0.0, 1.5, 0.0))
        self.assertFalse(self.control.has_pending_ghost(self.box))

    def test_leaving_ghost_mode_discards_the_pending_move(self):
        self.control.set_ghost_mode(True)
        self.control.move_target(self.box, (2.0, 0.0, 0.0))
        self.control.set_ghost_mode(False)
        self.assertEqual(self.control.ghost(self.box), self.control.setpoint(self.box))

    def test_set_setpoint_now_ignores_ghost_mode(self):
        self.control.set_ghost_mode(True)
        self.control.set_setpoint_now(self.box, (3.0, 1.0, 0.0, *frames.IDENTITY_QUAT))
        self.assertEqual(self.control.setpoint(self.box)[:3], (3.0, 1.0, 0.0))

    def test_rotation_moves_keep_unit_quaternions(self):
        for _ in range(50):
            self.control.move_target(self.box, rotation=frames.quat_from_axis_angle((0, 1, 0), 0.1))
        q = self.control.setpoint(self.box)[3:]
        self.assertAlmostEqual(sum(c * c for c in q), 1.0)
        self.assertAlmostEqual(frames.quat_to_euler_xyz(q)[1], 5.0 - 2 * math.pi, places=6)

    def test_simulated_object_flies_to_setpoint_at_limited_speed(self):
        self.control.move_target(self.box, (3.0, 0.0, 0.0))
        self.control.tick(1.0)
        self.assertAlmostEqual(self.box.pose[0], ControlService.SIM_SPEED_MPS)
        for _ in range(5):
            self.control.tick(1.0)
        self.assertAlmostEqual(self.box.pose[0], 3.0)

    def test_simulated_object_turns_towards_setpoint(self):
        target_q = frames.quat_from_axis_angle((0, 1, 0), math.radians(90))
        self.control.set_target(self.box, (*START[:3], *target_q))
        self.control.tick(0.25)   # 180°/s → 45°
        self.assertAlmostEqual(math.degrees(frames.quat_angle(self.box.pose[3:], START[3:])), 45.0, places=4)
        self.control.tick(1.0)
        self.assertTrue(frames.quats_equivalent(self.box.pose[3:], target_q))

    def test_mocap_tracked_objects_are_only_commanded(self):
        self.box.set_tracked(True, "cf1")
        self.control.move_target(self.box, (3.0, 0.0, 0.0))
        self.control.tick(1.0)
        self.assertEqual(self.box.pose, START)
        self.box.pose_locked = True     # locked pose: the sim may move it again
        self.control.tick(1.0)
        self.assertNotEqual(self.box.pose, START)

    def test_removed_objects_are_forgotten(self):
        self.objects.remove_object(obj=self.box)
        self.assertIsNone(self.control.state(self.box))


class SetpointOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = get_app()

    def setUp(self):
        self.objects = ObjectService()
        self.box = self.objects.add_object(RectPrism(name="Box", dimensions=0.3))
        self.box.set_pose(START)
        self.other = self.objects.add_object(RectPrism(name="Other", dimensions=0.3))
        self.control = ControlService(self.objects, simulate=False)
        self.control._timer.stop()
        self.overlay = SetpointOverlay(self.control, self.objects)

    def kinds(self):
        return sorted(type(d).__name__ + ("_ghost" if d.is_translucent() else "") for d in self.overlay.drawables())

    def test_controlled_object_on_its_setpoint_is_faded(self):
        self.objects.set_controlled_object(obj=self.box)
        self.control.sync_from_object(self.box)
        self.assertEqual(self.overlay.alpha_for(self.box), OVERLAP_ALPHA)
        self.assertEqual(self.overlay.alpha_for(self.other), 1.0)
        self.assertEqual(self.kinds(), ["Polyline", "Sphere"])  # ball + heading tick

    def test_line_to_setpoint_while_away(self):
        self.objects.set_controlled_object(obj=self.box)
        self.control.sync_from_object(self.box)
        self.control.move_target(self.box, (2.0, 0.0, 0.0))
        self.assertEqual(self.overlay.alpha_for(self.box), 1.0)
        self.assertEqual(self.kinds(), ["Polyline", "Polyline", "Sphere"])

    def test_ghost_ball_while_a_move_is_pending(self):
        self.objects.set_controlled_object(obj=self.box)
        self.control.sync_from_object(self.box)
        self.control.set_ghost_mode(True)
        self.control.move_target(self.box, (0.0, 0.0, 1.0))
        kinds = self.kinds()
        self.assertIn("Sphere_ghost", kinds)
        self.assertIn("Polyline_ghost", kinds)

    def test_uncontrolled_object_at_rest_shows_nothing(self):
        self.control.sync_from_object(self.other)
        self.assertEqual(self.overlay.drawables(), [])
        self.assertEqual(self.overlay.alpha_for(self.other), 1.0)


if __name__ == "__main__":
    unittest.main()
