"""The app theme: stylesheet, icons, light/dark switching and the small widgets built on it."""
import os
import re
import unittest

from qt_test_utils import QtMessageCapture, get_app, process_events_for
from PyQt5.QtGui import QFontDatabase
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFrame, QGroupBox, QLabel, QLineEdit,
                             QPushButton, QRadioButton, QTabWidget, QVBoxLayout, QWidget)

from ui import theme
from ui.dialogs.shell import DialogShell
from ui.splash import app_icon, splash_pixmap
from ui.widgets.compact_tabs import CompactTabWidget
from ui.widgets.empty_state import EmptyState
from ui.widgets.step_indicator import StepIndicator
from ui.widgets.toast import Toast, notifier, toast


def _sample_widgets():
    """One of each styled widget kind, with the roles and variants the panels use."""
    root = QWidget()
    layout = QVBoxLayout(root)
    for role in ("title", "subtitle", "display", "section", "hint", "value", "metric", "pill", "banner"):
        layout.addWidget(theme.label(role, role, "success"))
    for variant in ("", "primary", "danger", "success", "subtle", "ghost", "tile"):
        layout.addWidget(theme.button(variant or "default", variant or None, "plus"))
    layout.addWidget(theme.button("Large", "primary", size="lg"))
    card = QFrame()
    card.setProperty("role", "card")
    QVBoxLayout(card).addWidget(QGroupBox("Group in a card"))
    layout.addWidget(card)
    radio = QRadioButton("Card option")
    radio.setProperty("variant", "card")
    layout.addWidget(radio)
    eye = QCheckBox()
    eye.setProperty("variant", "eye")
    layout.addWidget(eye)
    for widget in (QLineEdit("text"), QComboBox(), QDoubleSpinBox(), QCheckBox("check"), QTabWidget()):
        layout.addWidget(widget)
    layout.addWidget(theme.StatusLine("Connected", "ok"))
    return root


class ThemeTests(unittest.TestCase):
    # Applying a theme re-polishes every widget in the process (thousands, after the other
    # test modules), so only test_switching_theme_* switches the whole app.

    @classmethod
    def setUpClass(cls):
        cls._app = get_app()
        theme.apply("light")

    def tearDown(self):
        theme.apply("light")     # free when it's already light

    def test_stylesheets_parse_and_have_no_unfilled_tokens(self):
        for name in theme.PALETTES:
            qss = theme.stylesheet(theme.PALETTES[name])
            self.assertNotRegex(qss, r"\{p\.\w+\}", f"{name}: a palette token wasn't substituted")
            for path in re.findall(r"url\(([^)]+)\)", qss):
                self.assertTrue(os.path.exists(path), f"{name}: missing stylesheet image {path}")
            with QtMessageCapture() as capture:
                root = _sample_widgets()
                root.setStyleSheet(qss)   # same rules, scoped to these widgets
                root.show()
                process_events_for(0.05)
                root.close()
            self.assertEqual(capture.matching("Could not parse", "Unknown property"), [], name)

    def test_switching_theme_changes_palette_icons_and_notifies(self):
        button = theme.button("Add", "subtle", "plus")
        light_icon = button.icon().cacheKey()
        seen = []
        theme.signals.changed.connect(seen.append)
        try:
            theme.apply("dark")
            self.assertEqual(theme.current_name(), "dark")
            self.assertEqual(theme.colour("bg"), theme.DARK.bg)
            self.assertEqual(self._app.palette().window().color().name().upper(), theme.DARK.bg.upper())
            self.assertIn(theme.DARK.surface.lower(), self._app.styleSheet().lower())
            self.assertNotEqual(button.icon().cacheKey(), light_icon, "icons are re-coloured on theme change")
            theme.apply("dark")      # already applied: nothing to redo
            theme.apply("light")
            self.assertEqual(theme.current_name(), "light")
        finally:
            theme.signals.changed.disconnect(seen.append)
        self.assertEqual([p.name for p in seen], ["dark", "light"])

    def test_unknown_theme_falls_back_to_light(self):
        theme.apply("default")    # the old AppSettings.ui_theme value
        self.assertEqual(theme.current_name(), "light")

    def test_bundled_fonts_are_used(self):
        families = QFontDatabase().families()
        self.assertIn(theme.UI_FONT, families)
        self.assertIn(theme.MONO_FONT, families)
        self.assertEqual(self._app.font().family(), theme.UI_FONT)

    def test_icons_render(self):
        for name in ("house", "plus", "radar", "drone", "check", "eye-off", "minus"):
            self.assertFalse(theme.icon(name).pixmap(18, 18).isNull(), name)
        self.assertNotEqual(theme.icon("plus", "accent").cacheKey(), theme.icon("plus", "danger").cacheKey())

    def test_status_line_shows_state(self):
        line = theme.StatusLine("Waiting", "warn")
        self.assertEqual(line.text(), "Waiting")
        line.set_state("bad", "Lost")
        self.assertEqual(line.text(), "Lost")
        self.assertEqual(line.text_label.property("tone"), "danger")
        self.assertFalse(line.icon_label.pixmap().isNull())

    def test_step_indicator_moves_to_a_step(self):
        steps = StepIndicator(["One", "Two", "Three"])
        steps.resize(400, 70)
        steps.set_current(2, animate=False)
        self.assertEqual(steps.current, 2)
        self.assertEqual(steps.position, 2.0)
        self.assertFalse(steps.grab().isNull())   # paints without errors

    def test_compact_tabs_size_to_the_current_page(self):
        tabs = CompactTabWidget()
        short, tall = QLabel("short"), QLabel("tall")
        tall.setMinimumHeight(400)
        tabs.addTab(short, "A")
        tabs.addTab(tall, "B")
        self.assertLess(tabs.sizeHint().height(), 200)
        tabs.setCurrentIndex(1)
        self.assertGreaterEqual(tabs.sizeHint().height(), 400)

    def test_toast_shows_then_hides(self):
        parent = QWidget()
        parent.resize(600, 400)
        widget = Toast(parent)
        notifier.requested.connect(widget.show_message)
        parent.show()
        try:
            toast("Scene saved")
            self.assertTrue(widget.isVisible())
            self.assertEqual(widget.text(), "Scene saved")
            self.assertLess(widget.y() + widget.height(), parent.height())
            widget.dismiss()
            process_events_for(0.5)
            self.assertFalse(widget.isVisible())
        finally:
            notifier.requested.disconnect(widget.show_message)
            parent.close()


    def test_dialog_shell_has_cancel_then_primary(self):
        dialog = DialogShell("Add object", "Explanation", accept_text="Add", accept_icon="plus")
        self.assertEqual(dialog.accept_button.text(), "Add")
        self.assertTrue(dialog.accept_button.isDefault())
        self.assertEqual(dialog.accept_button.property("variant"), "primary")
        footer = dialog.accept_button.parentWidget().layout()
        self.assertLess(footer.indexOf(dialog.cancel_button), footer.indexOf(dialog.accept_button))
        dialog.cancel_button.click()
        self.assertEqual(dialog.result(), QDialog.Rejected)
        dialog.accept_button.click()
        self.assertEqual(dialog.result(), QDialog.Accepted)

    def test_empty_state_updates_its_text(self):
        empty = EmptyState("radar", "Not connected", "Connect first.")
        empty.set_content("No subjects yet", "Nothing received.")
        self.assertEqual(empty.text(), "No subjects yet Nothing received.")
        self.assertFalse(empty.icon_label.pixmap().isNull())

    def test_app_icon_and_splash_are_drawn(self):
        icon = app_icon()
        self.assertGreaterEqual(len(icon.availableSizes()), 5)
        self.assertFalse(icon.pixmap(64, 64).isNull())
        self.assertEqual(splash_pixmap().width(), 520)


if __name__ == "__main__":
    unittest.main()
