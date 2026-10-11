"""Regression tests for cross-thread use of threaded services (issue #40)."""
import unittest

from qt_test_utils import (THREAD_VIOLATION_MARKERS, QtMessageCapture,
                           get_app, wait_until)

from PyQt5.QtCore import QObject, QThread, Qt, pyqtSlot

from models.structs import MavlinkGlobalSettings
from services.input_service import InputService, InputType
from services.mavlink_service import MavlinkService
from services.status_service import StatusService


class _ThreadRecordingPanel(QObject):
    """Stands in for a GUI widget and records which thread it was called on."""

    def __init__(self):
        super().__init__()
        self.calls = []

    @pyqtSlot(int, str, str)
    def handle_status_change(self, level, label, target=""):
        self.calls.append((QThread.currentThread(), target))

    @pyqtSlot(object)
    def update_setpoint_from_joystick(self, pose_delta):
        self.calls.append((QThread.currentThread(), list(pose_delta)))

    def is_joystick_control_allowed(self):
        return True


class _FakeGlWidget:
    camera_angle_y = 0.0


class ServiceThreadingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = get_app()

    def test_mavlink_settings_update_from_gui_thread_applies_rates_without_warnings(self):
        service = MavlinkService()
        with QtMessageCapture() as capture:
            service.start()
            try:
                self.assertTrue(wait_until(lambda: service._mocap_timer is not None),
                                "MAVLink service did not start")

                service.update_global_settings(MavlinkGlobalSettings(
                    telemetry_rate_hz=10.0,
                    default_setpoint_rate_hz=25.0,
                    default_mocap_rate_hz=50.0,
                ))

                self.assertTrue(wait_until(lambda: service._mocap_timer.interval() == 20))
                self.assertEqual(service._setpoint_timer.interval(), 40)
                self.assertEqual(service._telemetry_timer.interval(), 100)
            finally:
                service.stop()
        self.assertEqual(capture.matching(*THREAD_VIOLATION_MARKERS), [])

    def test_settings_applied_before_start_are_used_by_timers(self):
        service = MavlinkService()
        service.update_global_settings(MavlinkGlobalSettings(default_mocap_rate_hz=200.0))
        service.start()
        try:
            self.assertTrue(wait_until(lambda: service._mocap_timer is not None))
            self.assertEqual(service._mocap_timer.interval(), 5)
        finally:
            service.stop()

    def test_status_service_updates_panel_on_gui_thread(self):
        panel = _ThreadRecordingPanel()
        input_service = InputService(gl_widget=_FakeGlWidget(), input_type=InputType.WASD)
        service = StatusService(panel, input_service, None)
        service.start()
        try:
            self.assertTrue(wait_until(lambda: len(panel.calls) > 0, timeout_s=3.0))
        finally:
            service.stop()
        gui_thread = self.app.thread()
        for thread, _ in panel.calls:
            self.assertIs(thread, gui_thread)

    def test_input_service_routes_deltas_to_panel_on_gui_thread(self):
        panel = _ThreadRecordingPanel()
        service = InputService(gl_widget=_FakeGlWidget(), input_type=InputType.WASD)
        service.set_command_panel(panel)
        service.set_controlled_object(object())
        service.key_states[Qt.Key_W] = True
        with QtMessageCapture() as capture:
            service.start()
            try:
                self.assertTrue(wait_until(lambda: len(panel.calls) > 0))
            finally:
                service.stop()
        gui_thread = self.app.thread()
        for thread, _ in panel.calls:
            self.assertIs(thread, gui_thread)
        self.assertEqual(capture.matching(*THREAD_VIOLATION_MARKERS), [])

    def test_input_type_switch_from_gui_thread_runs_on_service_thread(self):
        service = InputService(gl_widget=_FakeGlWidget(), input_type=InputType.WASD)
        seen = []
        original = service._apply_input_type

        def recording_apply(input_type):
            seen.append(QThread.currentThread())
            original(input_type)

        service._apply_input_type = recording_apply
        service.start()
        try:
            self.assertTrue(wait_until(lambda: service.timer is not None))
            service.set_input_type(InputType.ARROW_KEYS)
            self.assertTrue(wait_until(lambda: service.input_type == InputType.ARROW_KEYS))
        finally:
            service.stop()
        self.assertEqual(len(seen), 1)
        self.assertIsNot(seen[0], self.app.thread())


if __name__ == "__main__":
    unittest.main()
