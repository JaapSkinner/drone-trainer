import time
import unittest
from unittest import mock

from qt_test_utils import get_app, wait_until

from models import frames
from models.cad_mesh import CadMesh
from models.rect_prism import RectPrism
from models.structs import MavlinkConnectionConfig
from services import mavlink_service
from services.mavlink_service import MavlinkService
from services.motion_capture_service import MotionCaptureService
from services.object_service import ObjectService
from test_mavlink_service import _fake_connect
from ui.dialogs.add_drone_wizard import NEW_CONNECTION, AddDroneWizard
from ui.widgets.drone_status import BAD, OFF, OK, WARN, DroneStatusWidget, drone_checks

POSE = (1.0, 1.2, -0.5, *frames.IDENTITY_QUAT)


def _stream(mocap, *names):
    mocap._connected = True
    for name in names:
        mocap._record_sample(name, POSE, time.monotonic())


class WizardTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = get_app()

    def setUp(self):
        patch = mock.patch.object(mavlink_service.MavlinkConnection, "connect", _fake_connect(heartbeat_system_id=5))
        patch.start()
        self.addCleanup(patch.stop)
        self.objects = ObjectService()
        self.mocap = MotionCaptureService()
        self.mavlink = MavlinkService()

    def wizard(self, edit_object=None):
        w = AddDroneWizard(self.objects, self.mocap, self.mavlink, edit_object=edit_object)
        self.addCleanup(w.deleteLater)
        self.results = []
        w.drone_ready.connect(lambda obj, opts: self.results.append((obj, opts)))
        return w

    def walk_to_review(self, w):
        for _ in range(3):
            w.next()
        self.assertEqual(w.current_step(), 3, w.error_label.text())


class AddDroneWizardTests(WizardTestCase):
    def test_simulated_drone_with_defaults(self):
        w = self.wizard()
        self.assertEqual(w.name_edit.text(), "Drone")
        self.assertTrue(w.simulated_radio.isChecked())
        self.walk_to_review(w)
        self.assertEqual(w.next_button.text(), "Finish")
        w.next()
        obj, options = self.results[0]
        self.assertIsInstance(obj, CadMesh)
        self.assertAlmostEqual(obj.scale[0], 0.004)
        self.assertTrue(obj.controllable)
        self.assertFalse(obj.tracked)
        self.assertFalse(obj.mavlink_config.enabled)
        self.assertTrue(options["control"])
        self.assertIs(self.objects.get_object("Drone"), obj)

    def test_tracked_drone_picks_matching_subject_and_takes_it_over(self):
        old = self.objects.add_object(RectPrism(name="Old marker"))
        old.set_tracked(True, "cf1")
        _stream(self.mocap, "cf1", "wand")
        w = self.wizard()
        w.name_edit.setText("CF1")
        w._on_subjects_updated(self.mocap.subjects_snapshot())
        w.next()
        w.subject_edit.clear()
        w._auto_pick_subject(["cf1", "wand"])   # matches the drone's name, ignoring case
        self.assertEqual(w.subject_edit.text(), "cf1")
        self.assertTrue(w.tracked_radio.isChecked())
        self.assertIn("taken over from 'Old marker'", w.subject_status.text())
        w.next()
        w.next()
        w.next()
        obj, _ = self.results[0]
        self.assertTrue(obj.tracked)
        self.assertEqual(obj.tracking_id, "cf1")
        self.assertEqual(obj.pose[:3], POSE[:3])      # placed where the subject is
        self.assertFalse(old.tracked)

    def test_tracking_needs_a_subject(self):
        w = self.wizard()
        w.next()
        w.tracked_radio.setChecked(True)
        w.subject_edit.clear()
        w.next()
        self.assertEqual(w.current_step(), 1)
        self.assertIn("subject", w.error_label.text())

    def test_new_vehicle_connection_connect_now_then_link(self):
        _stream(self.mocap, "Drone")
        w = self.wizard()
        w.next()
        w.tracked_radio.setChecked(True)
        w.subject_edit.setText("Drone")
        w.next()
        w.vehicle_radio.setChecked(True)
        w.connection_combo.setCurrentIndex(w.connection_combo.findData(NEW_CONNECTION))
        self.assertEqual(w.connection_name_edit.text(), "Drone")
        self.assertTrue(w.address_edit.text().endswith(":14550"))
        self.assertTrue(w.send_mocap_check.isChecked())
        w._connect_vehicle()
        self.assertTrue(wait_until(lambda: self.mavlink.get_connection_by_name("Drone") is not None, timeout_s=3))
        self.assertTrue(wait_until(lambda: "connected" in w.vehicle_status.text(), timeout_s=2))
        w.next()
        w.next()
        obj, _ = self.results[0]
        self.assertTrue(obj.mavlink_config.enabled)
        self.assertEqual(obj.mavlink_config.linked_connection_name, "Drone")
        self.assertTrue(obj.mavlink_config.send_mocap)
        self.objects.apply_tracking_poses({"Drone": POSE})   # what MainWindow does with mocap
        self.assertEqual(self.mavlink.mocap_stream_state(obj), "streaming")

    def test_unconnected_vehicle_is_saved_and_connects_in_the_background(self):
        w = self.wizard()
        w.next()
        w.next()
        w.vehicle_radio.setChecked(True)
        w.connection_combo.setCurrentIndex(w.connection_combo.findData(NEW_CONNECTION))
        self.assertFalse(w.send_mocap_check.isEnabled())   # not tracked, nothing to send
        w.next()
        w.next()
        obj, _ = self.results[0]
        self.assertEqual(obj.mavlink_config.linked_connection_name, "Drone")
        self.assertIn("Drone", self.mavlink.get_all_connections())
        self.assertTrue(wait_until(lambda: self.mavlink.get_connection_by_name("Drone") is not None, timeout_s=3))

    def test_existing_connection_name_is_rejected(self):
        self.mavlink.save_connection_config(MavlinkConnectionConfig("udpin:0.0.0.0:14550", name="Drone"))
        w = self.wizard()
        w.next()
        w.next()
        w.vehicle_radio.setChecked(True)
        w.connection_combo.setCurrentIndex(w.connection_combo.findData(NEW_CONNECTION))
        w.connection_name_edit.setText("Drone")
        w.next()
        self.assertEqual(w.current_step(), 2)
        self.assertIn("already exists", w.error_label.text())

    def test_suggested_port_avoids_existing_connections(self):
        for port in (14550, 14551):
            self.mavlink.save_connection_config(MavlinkConnectionConfig(f"udpin:0.0.0.0:{port}", name=f"D{port}"))
        self.assertEqual(self.wizard().suggest_port(), 14552)

    def test_edit_mode_prefills_and_can_remove_the_vehicle(self):
        drone = self.objects.add_object(RectPrism(name="Quad"))
        drone.set_tracked(True, "q1")
        self.mavlink.save_connection_config(MavlinkConnectionConfig("udpin:0.0.0.0:14550", name="Quad link"))
        self.mavlink.link_object(drone, "Quad link")
        w = self.wizard(edit_object=drone)
        self.assertEqual(w.name_edit.text(), "Quad")
        self.assertFalse(w.model_combo.isEnabled())
        self.assertTrue(w.tracked_radio.isChecked())
        self.assertEqual(w.subject_edit.text(), "q1")
        self.assertTrue(w.vehicle_radio.isChecked())
        self.assertEqual(w.connection_combo.currentData(), "Quad link")
        w.next()
        w.next()
        w.no_vehicle_radio.setChecked(True)
        w.next()
        w.next()
        self.assertIs(self.results[0][0], drone)
        self.assertFalse(drone.mavlink_config.enabled)
        self.assertEqual(len(self.objects.get_objects()), 1)   # nothing new was created


class DroneChecksTests(WizardTestCase):
    def states(self, obj):
        return {c.key: c.state for c in drone_checks(obj, self.mocap, self.mavlink)}

    def test_readiness_states(self):
        drone = self.objects.add_object(RectPrism(name="Quad"))
        self.assertEqual(self.states(drone), {"tracking": OFF, "vehicle": OFF})

        drone.set_tracked(True, "q1")
        self.assertEqual(self.states(drone)["tracking"], WARN)         # mocap not connected
        _stream(self.mocap, "q1")
        self.assertEqual(self.states(drone)["tracking"], OK)
        self.mocap._subjects["q1"].last_seen -= 5
        self.assertEqual(self.states(drone)["tracking"], BAD)          # lost

        drone.mavlink_config.enabled = True
        self.assertEqual(self.states(drone)["vehicle"], BAD)           # no connection chosen
        self.mavlink.add_connection(MavlinkConnectionConfig("udpin:0.0.0.0:14550", name="Link"))
        self.mavlink.link_object(drone, "Link")
        self.assertEqual(self.states(drone)["vehicle"], OK)
        drone.last_tracking_update = time.monotonic()
        self.assertEqual(self.states(drone)["mocap"], OK)

    def test_widget_shows_checks_and_setup_button(self):
        widget = DroneStatusWidget(self.mocap, self.mavlink)
        self.addCleanup(widget.deleteLater)
        self.assertEqual(widget.setup_button.text(), "Add a drone…")
        requested = []
        widget.setup_requested.connect(requested.append)
        drone = self.objects.add_object(RectPrism(name="Quad"))
        widget.set_object(drone)
        self.assertEqual(widget.setup_button.text(), "Drone setup…")
        widget.setup_button.click()
        self.assertIs(requested[0], drone)

    def test_case_mismatch_suggests_the_live_subject(self):
        from ui.widgets.drone_status import tracking_check
        _stream(self.mocap, "CF1")
        drone = self.objects.add_object(RectPrism(name="Quad"))
        drone.set_tracked(True, "cf1")
        self.assertIn("did you mean 'CF1'", tracking_check(drone, self.mocap).text)


if __name__ == "__main__":
    unittest.main()
