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
                    self.assertIsNotNone(window.dock.current_widget, key)

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


if __name__ == "__main__":
    unittest.main()
