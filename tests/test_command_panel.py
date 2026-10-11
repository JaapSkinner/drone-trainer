import math
import unittest

from qt_test_utils import get_app

from PyQt5.QtCore import Qt

from models import frames
from models.rect_prism import RectPrism
from services.control_service import ControlService
from services.object_service import ObjectService
from ui.dock.panels.command_panel import CommandPanel

START = (0.0, 1.0, 0.0, *frames.IDENTITY_QUAT)


class CommandPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = get_app()

    def setUp(self):
        self.objects = ObjectService()
        self.drone = self.objects.add_object(RectPrism(name="Drone", dimensions=0.3))
        self.drone.set_pose(START)
        self.control = ControlService(self.objects)
        self.control._timer.stop()
        self.panel = CommandPanel(object_service=self.objects, control_service=self.control)
        index = next(i for i in range(self.panel.object_combo.count())
                     if self.panel.object_combo.itemData(i) is self.drone)
        self.panel.object_combo.setCurrentIndex(index)

    def tearDown(self):
        self.panel.deleteLater()

    def test_selecting_an_object_starts_from_its_pose(self):
        self.assertIs(self.objects.get_controlled_object(), self.drone)
        self.assertEqual(tuple(self.panel.setpoint), START)

    def test_jog_moves_setpoint_and_the_simulated_object_follows(self):
        self.panel._jog_axis("X", +1)
        self.assertAlmostEqual(self.panel.setpoint[0], 0.1)
        self.assertEqual(self.drone.pose[0], 0.0)      # not teleported
        self.control.tick(1.0)
        self.assertAlmostEqual(self.drone.pose[0], 0.1)
        self.assertEqual(self.panel.jog_x_value.text(), "0.1000")

    def test_rotation_jog_is_a_real_rotation(self):
        self.panel._jog_axis("Yaw", +1)
        q = self.panel.setpoint[3:]
        self.assertAlmostEqual(sum(c * c for c in q), 1.0)
        self.assertAlmostEqual(math.degrees(frames.quat_to_euler_xyz(q)[1]), 5.0)
        self.assertEqual(self.panel.jog_yaw_value.text(), "5.0°")

    def test_ghost_mode_previews_then_sends(self):
        sent = []
        self.panel.send_position_requested.connect(sent.append)
        self.panel.ghost_checkbox.setCheckState(Qt.Checked)
        self.assertFalse(self.panel.send_position_btn.isEnabled())
        self.panel._jog_axis("Z", -1)
        self.assertEqual(tuple(self.panel.setpoint), START)
        self.assertAlmostEqual(self.panel.next_setpoint[2], -0.1)
        self.assertTrue(self.panel.send_position_btn.isEnabled())

        self.panel.send_position_btn.click()
        self.assertAlmostEqual(self.panel.setpoint[2], -0.1)
        self.assertAlmostEqual(sent[0][2], -0.1)
        self.assertFalse(self.panel.send_position_btn.isEnabled())

    def test_home_button_overrides_ghost_mode(self):
        self.panel.home_position = (2.0, -1.0)
        self.panel.hover_height_spin.setValue(1.5)
        self.panel.ghost_checkbox.setCheckState(Qt.Checked)
        self.panel.home_btn.click()
        self.assertEqual(tuple(self.panel.setpoint[:3]), (2.0, 1.5, -1.0))

    def test_joystick_deltas_move_the_setpoint(self):
        self.panel.update_setpoint_from_joystick([0.1, 0.0, -0.1, 0.0, 0.0, 0.03, 0.0])
        sp = self.panel.setpoint
        self.assertAlmostEqual(sp[0], 0.1)
        self.assertAlmostEqual(sp[2], -0.1)
        self.assertAlmostEqual(sum(c * c for c in sp[3:]), 1.0)
        self.assertGreater(abs(frames.quat_to_euler_xyz(sp[3:])[1]), 0.0)

    def test_go_to_target_point(self):
        self.panel.target_x_spin.setValue(1.0)
        self.panel.target_y_spin.setValue(2.0)
        self.panel.offset_z_spin.setValue(0.5)
        self.panel.go_to_target_btn.click()
        self.assertEqual(tuple(self.panel.setpoint[:3]), (1.0, 2.0, 0.5))


if __name__ == "__main__":
    unittest.main()
