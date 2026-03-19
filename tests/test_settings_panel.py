import unittest
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtWidgets import QApplication

from services.input_service import InputType
from ui.dock.panels.settings_panel import SettingsPanel


class SettingsPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_settings_panel_uses_collapsible_toolbox_sections(self):
        panel = SettingsPanel()
        self.assertTrue(hasattr(panel, "settings_toolbox"))
        self.assertEqual(panel.settings_toolbox.count(), 4)
        self.assertEqual(panel.settings_toolbox.itemText(0), "Input Controls")
        self.assertEqual(panel.settings_toolbox.itemText(1), "Viewport")
        self.assertEqual(panel.settings_toolbox.itemText(2), "MAVLink")
        self.assertEqual(panel.settings_toolbox.itemText(3), "Import / Export")

    def test_input_type_controls_live_in_settings_panel(self):
        panel = SettingsPanel()
        panel.set_input_type(InputType.WASD)
        panel.set_input_sensitivity(2.5)
        self.assertEqual(panel.get_current_input_type(), InputType.WASD)
        self.assertAlmostEqual(panel.get_current_sensitivity(), 2.5, places=2)
        self.assertIn("WASD Mapping", panel.mapping_info.text())


if __name__ == "__main__":
    unittest.main()
