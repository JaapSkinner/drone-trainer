"""Boot smoke test: build the real MainWindow headlessly and shut it down.

Catches wiring mistakes (attributes that don't exist, panels that can't be
built, cross-thread Qt misuse) that unit tests of individual pieces miss.
"""
import json
import os
import tempfile
import unittest
from unittest import mock

from qt_test_utils import (THREAD_VIOLATION_MARKERS, QtMessageCapture,
                           get_app, process_events_for)

from services.paths import DATA_DIR_ENV_VAR


class AppBootTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = get_app()

    def setUp(self):
        self._data_dir = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(os.environ, {DATA_DIR_ENV_VAR: self._data_dir.name})
        self._env.start()

    def tearDown(self):
        self._env.stop()
        self._data_dir.cleanup()

    def _boot(self):
        from ui.main_window import MainWindow
        window = MainWindow()
        window.show()
        process_events_for(0.3)
        return window

    def test_boot_visit_every_panel_save_settings_and_close(self):
        with QtMessageCapture() as capture:
            window = self._boot()
            try:
                for key, button in window.navbar.buttons.items():
                    button.click()
                    process_events_for(0.05)
                    self.assertEqual(getattr(window.dock.current_widget, "NavTag", None), key,
                                     f"navbar entry {key!r} did not open its panel")

                # Paths that previously produced cross-thread timer warnings.
                window.settings_panel._update_mavlink_setting("telemetry_rate_hz", 10.0)
                window.on_sensitivity_changed(1.5)
                window._on_save_zoom_sensitivity(1.3)
                process_events_for(0.2)
            finally:
                window.close()
                process_events_for(0.2)

        self.assertEqual(capture.matching(*THREAD_VIOLATION_MARKERS), [])

        settings_path = os.path.join(self._data_dir.name, "settings.json")
        with open(settings_path, encoding="utf-8") as fh:
            saved = json.load(fh)
        self.assertAlmostEqual(saved["input_sensitivity"], 1.5)
        self.assertAlmostEqual(saved["zoom_sensitivity"], 1.3)
        self.assertAlmostEqual(saved["telemetry_rate_hz"], 10.0)

    def test_restores_legacy_active_panel_and_syncs_navbar(self):
        with open(os.path.join(self._data_dir.name, "settings.json"), "w", encoding="utf-8") as fh:
            json.dump({"active_panel": "live_data"}, fh)
        window = self._boot()
        try:
            self.assertEqual(window.dock.current_widget.NavTag, "objects")
            self.assertTrue(window.navbar.buttons["objects"].isChecked())
        finally:
            window.close()
            process_events_for(0.1)

    def test_scene_is_restored_and_saved_between_sessions(self):
        from models import scene_io
        from models.sphere import Sphere
        scene_path = os.path.join(self._data_dir.name, "scene.json")
        scene_io.save_scene([Sphere(name="Waypoint", radius=0.3)], scene_path)

        window = self._boot()
        try:
            self.assertEqual([o.name for o in window.object_service.get_objects()], ["Waypoint"])
            window.object_service.add_object(Sphere(name="Added"))
        finally:
            window.close()
            process_events_for(0.1)

        self.assertEqual([o.name for o in scene_io.load_scene(scene_path)], ["Waypoint", "Added"])

    def test_broken_scene_file_falls_back_to_default_scene(self):
        with open(os.path.join(self._data_dir.name, "scene.json"), "w", encoding="utf-8") as fh:
            fh.write("{ not json")
        window = self._boot()
        try:
            self.assertIsNotNone(window.object_service.get_object("Grid"))
        finally:
            window.close()
            process_events_for(0.1)

    def test_second_close_does_not_save_again(self):
        window = self._boot()
        window.close()
        process_events_for(0.1)
        scene_path = os.path.join(self._data_dir.name, "scene.json")
        os.remove(scene_path)
        window.close()  # e.g. QApplication.aboutToQuit after the user closed the window
        self.assertFalse(os.path.exists(scene_path))


if __name__ == "__main__":
    unittest.main()
