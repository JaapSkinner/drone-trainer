import unittest
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtWidgets import QApplication, QSizePolicy

from ui.dock.panels.settings_panel import SettingsPanel


class SettingsPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def _clean_title(self, text: str) -> str:
        # Remove caret glyphs and surrounding whitespace used by header indicator
        return text.lstrip('▸▾ ').strip()

    def test_settings_panel_uses_collapsible_sections(self):
        panel = SettingsPanel()
        self.assertTrue(hasattr(panel, "settings_groups"))
        self.assertEqual(len(panel.settings_groups), 3)
        titles = [self._clean_title(g.toggle_button.text()) for g in panel.settings_groups]
        self.assertEqual(titles[0], "Viewport")
        self.assertEqual(titles[1], "MAVLink")
        self.assertEqual(titles[2], "Import / Export")

    def test_settings_panel_has_no_input_controls_section(self):
        panel = SettingsPanel()
        titles = [self._clean_title(g.toggle_button.text()) for g in panel.settings_groups]
        self.assertNotIn("Input Controls", titles)

    def test_headers_are_full_width_and_left_aligned(self):
        panel = SettingsPanel()
        for g in panel.settings_groups:
            policy = g.toggle_button.sizePolicy()
            self.assertEqual(policy.horizontalPolicy(), QSizePolicy.Expanding,
                             "Header toggle button should expand horizontally to full width")
            # Expect the inline stylesheet to include left-align directive (we set this in code)
            ss = g.toggle_button.styleSheet() or ""
            self.assertIn("text-align: left", ss.replace('\n', ' '))


if __name__ == "__main__":
    unittest.main()
