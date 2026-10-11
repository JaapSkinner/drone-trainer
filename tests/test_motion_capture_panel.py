import unittest

from qt_test_utils import get_app

from models.rect_prism import RectPrism
from models.sphere import Sphere
from models.structs import MotionCaptureConfig
from services.motion_capture_service import MotionCaptureService, SubjectInfo
from services.object_service import ObjectService
from ui.dock.panels.motion_capture_panel import MotionCapturePanel

POSE = (1.0, 1.5, -2.0, 1.0, 0.0, 0.0, 0.0)


class MotionCapturePanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = get_app()

    def setUp(self):
        self.config = MotionCaptureConfig(source="optitrack", vicon_port=52000,
                                          optitrack_server_ip="10.0.0.5", optitrack_client_ip="10.0.0.9",
                                          optitrack_multicast=False, optitrack_up_axis="z",
                                          filter_enabled=True, filter_cutoff_hz=7.5, auto_connect=True)
        self.service = MotionCaptureService(self.config)
        self.objects = ObjectService()
        self.panel = MotionCapturePanel(motion_capture_service=self.service, object_service=self.objects)

    def tearDown(self):
        self.panel.deleteLater()
        self.service.stop()

    def test_widgets_round_trip_the_config(self):
        self.assertEqual(self.panel.current_config(), self.config)

    def test_connect_click_emits_config_for_saving(self):
        emitted = []
        self.panel.config_changed.connect(emitted.append)
        self.panel.vicon_port_spin.setValue(51999)
        self.panel.connect_button.click()
        self.assertEqual(emitted[-1].vicon_port, 51999)

    def test_connection_state_locks_settings(self):
        self.panel.on_connection_changed(True)
        self.assertEqual(self.panel.connect_button.text(), "Disconnect")
        self.assertFalse(self.panel.source_combo.isEnabled())
        self.panel.on_connection_changed(False)
        self.assertTrue(self.panel.source_combo.isEnabled())

    def test_subject_table_updates_in_place(self):
        subjects = [SubjectInfo("cf1", 100.0, 0.01, POSE), SubjectInfo("wand", 99.0, 5.0, POSE)]
        self.panel.on_subjects_updated(subjects)
        table = self.panel.subjects_table
        self.assertEqual(table.rowCount(), 2)
        self.assertEqual(table.item(0, 0).text(), "cf1")
        self.assertEqual(table.item(0, 1).text(), "100 Hz")
        self.assertEqual(table.item(1, 1).text(), "lost")
        self.assertEqual(table.item(0, 2).text(), "+1.00, +1.50, -2.00")

        table.selectRow(1)
        self.panel.on_subjects_updated([SubjectInfo("cf1", 98.0, 0.0, POSE), SubjectInfo("wand", 99.0, 0.0, POSE)])
        self.assertEqual(self.panel.selected_subject(), "wand")
        self.assertEqual(table.item(0, 1).text(), "98 Hz")

    def test_assigning_moves_tracking_to_one_object(self):
        a = self.objects.add_object(RectPrism(name="A"))
        b = self.objects.add_object(RectPrism(name="B"))
        self.panel.on_subjects_updated([SubjectInfo("cf1", 100.0, 0.0, POSE)])

        self.panel.assign_subject("cf1", a)
        self.assertTrue(a.tracked and a.tracking_id == "cf1")
        self.assertEqual(self.panel.subjects_table.item(0, 3).text(), "A")

        self.panel.assign_subject("cf1", b)
        self.assertFalse(a.tracked)
        self.assertTrue(b.tracked)
        self.assertEqual(self.panel.subjects_table.item(0, 3).text(), "B")

    def test_create_object_for_subject(self):
        marker = self.panel.create_object_for_subject("wand")
        self.assertIsInstance(marker, Sphere)
        self.assertIs(self.objects.get_object("wand"), marker)
        self.assertTrue(marker.tracked)
        self.assertEqual(marker.tracking_id, "wand")


if __name__ == "__main__":
    unittest.main()
