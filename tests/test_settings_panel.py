import unittest

from qt_test_utils import get_app
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QSizePolicy

from ui import theme
from ui.dock.panels.settings_panel import SettingsPanel


class SettingsPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = get_app()

    def _clean_title(self, text: str) -> str:
        # Remove caret glyphs and surrounding whitespace used by header indicator
        return text.lstrip('▸▾ ').strip()

    def test_settings_panel_uses_collapsible_sections(self):
        panel = SettingsPanel()
        self.assertTrue(hasattr(panel, "settings_groups"))
        titles = [self._clean_title(g.toggle_button.text()) for g in panel.settings_groups]
        self.assertEqual(titles, ["Appearance", "Viewport", "MAVLink", "Live plots", "Import / Export"])

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
            # Icon then text, drawn from the left edge; styled by the app theme.
            self.assertEqual(g.toggle_button.toolButtonStyle(), Qt.ToolButtonTextBesideIcon)
            self.assertEqual(g.toggle_button.objectName(), "SectionHeader")
        self.assertIn("QToolButton#SectionHeader", theme.stylesheet())

    def test_sections_open_and_close(self):
        panel = SettingsPanel()
        box = panel.settings_groups[1]
        self.assertFalse(box.content_area.isVisibleTo(box))
        box.set_open(True)
        self.assertTrue(box.content_area.isVisibleTo(box))
        box.toggle_button.click()   # not shown, so no animation: closes at once
        self.assertFalse(box.content_area.isVisibleTo(box))

    def test_theme_buttons_request_a_theme(self):
        theme.apply("light")
        panel = SettingsPanel()
        self.assertTrue(panel.theme_buttons["light"].isChecked())
        requested = []
        panel.theme_changed.connect(requested.append)
        panel.theme_buttons["dark"].click()
        self.assertEqual(requested, ["dark"])
        # The panel only asks; MainWindow applies it. Light is still current, so asking again is a no-op.
        panel.theme_buttons["light"].click()
        self.assertEqual(requested, ["dark"])


if __name__ == "__main__":
    unittest.main()
