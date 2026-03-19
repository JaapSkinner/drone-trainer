import unittest
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtWidgets import QApplication

from ui.dock.panels.settings_panel import SettingsPanel


class SettingsPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_settings_panel_uses_collapsible_toolbox_sections(self):
        panel = SettingsPanel()
        self.assertTrue(hasattr(panel, "settings_toolbox"))
        self.assertEqual(panel.settings_toolbox.count(), 3)
        self.assertEqual(panel.settings_toolbox.itemText(0), "Viewport")
        self.assertEqual(panel.settings_toolbox.itemText(1), "MAVLink")
        self.assertEqual(panel.settings_toolbox.itemText(2), "Import / Export")

    def test_settings_panel_has_no_input_controls_section(self):
        panel = SettingsPanel()
        labels = [panel.settings_toolbox.itemText(i) for i in range(panel.settings_toolbox.count())]
        self.assertNotIn("Input Controls", labels)


if __name__ == "__main__":
    unittest.main()
