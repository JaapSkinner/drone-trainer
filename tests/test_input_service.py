import unittest

from services.input_service import InputService, InputType


class _FakeGlWidget:
    camera_angle_y = 0.0


class _FakeCommandPanel:
    def __init__(self, allowed=True):
        self.allowed = allowed
        self.received = []

    def is_joystick_control_allowed(self):
        return self.allowed

    def update_setpoint_from_joystick(self, pose_delta):
        self.received.append(pose_delta)


class _FakeObject:
    pass


class InputServiceTests(unittest.TestCase):
    def test_apply_deadzone(self):
        self.assertEqual(InputService._apply_deadzone(0.05), 0)
        self.assertEqual(InputService._apply_deadzone(-0.05), 0)
        self.assertEqual(InputService._apply_deadzone(0.2), 0.2)

    def test_wasd_control_path_updates_command_panel(self):
        service = InputService(gl_widget=_FakeGlWidget(), input_type=InputType.WASD, sensitivity=1.0)
        panel = _FakeCommandPanel(allowed=True)
        service.set_command_panel(panel)
        service.set_controlled_object(_FakeObject())

        from PyQt5.QtCore import Qt
        service.key_states[Qt.Key_W] = True
        service.key_states[Qt.Key_Q] = True
        service.key_states[Qt.Key_R] = True

        service.update()

        self.assertEqual(len(panel.received), 1)
        pose_delta = panel.received[0]
        self.assertAlmostEqual(pose_delta[0], 0.0)
        self.assertAlmostEqual(pose_delta[1], 0.1)
        self.assertAlmostEqual(pose_delta[2], -0.1)
        self.assertAlmostEqual(pose_delta[6], -0.03)

    def test_arrow_keys_control_path_blocked_when_not_allowed(self):
        service = InputService(gl_widget=_FakeGlWidget(), input_type=InputType.ARROW_KEYS, sensitivity=1.0)
        panel = _FakeCommandPanel(allowed=False)
        service.set_command_panel(panel)
        service.set_controlled_object(_FakeObject())

        from PyQt5.QtCore import Qt
        service.key_states[Qt.Key_Up] = True
        service.key_states[Qt.Key_PageUp] = True
        service.key_states[Qt.Key_Home] = True

        service.update()
        self.assertEqual(panel.received, [])


if __name__ == "__main__":
    unittest.main()
