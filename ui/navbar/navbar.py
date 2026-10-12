"""Left navigation sidebar: app mark, sections, settings and the pilot profile."""
from PyQt5.QtCore import QRect, QSize, Qt, pyqtSignal
from PyQt5.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout,
                             QWidget)

from ui import animation, theme

# (navigation key, label, Lucide icon) — keys must match a panel NavTag.
NAV_ITEMS = [
    ("home", "Home", "house"),
    ("command", "Command", "move"),
    ("trainer", "Trainer", "gamepad-2"),
    ("leaderboard", "Leaderboard", "trophy"),
    ("objects", "Objects", "boxes"),
    ("motion_capture", "Motion Capture", "radar"),
    ("mavlink", "MAVLink", "radio-tower"),
]


def _initials(name: str) -> str:
    parts = [p for p in name.split() if p]
    return "".join(p[0] for p in parts[:2]).upper() or "?"


class SideNavbar(QWidget):
    panel_selected = pyqtSignal(str)
    profile_clicked = pyqtSignal()

    WIDTH = 216

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(self.WIDTH)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.setObjectName("SideNavbar")
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 16, 12, 12)
        layout.setSpacing(4)

        # App mark: a drone glyph on an accent tile + the name.
        title = QHBoxLayout()
        title.setContentsMargins(6, 0, 0, 14)
        title.setSpacing(10)
        self.mark = QLabel()
        self.mark.setObjectName("AppMark")
        self.mark.setFixedSize(30, 30)
        self.mark.setAlignment(Qt.AlignCenter)
        title.addWidget(self.mark)
        name = QLabel("DRONE TRAINER")
        name.setObjectName("NavbarTitleText")
        title.addWidget(name)
        title.addStretch()
        layout.addLayout(title)

        # Sliding highlight behind the selected item (drawn under the buttons).
        self.indicator = QFrame(self)
        self.indicator.setObjectName("NavIndicator")
        self.indicator.hide()

        self.buttons = {}
        self._icons = {}
        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)
        for key, text, icon_name in NAV_ITEMS:
            self._add_button(layout, key, text, icon_name)
        layout.addStretch()
        self._add_button(layout, "settings", "Settings", "settings")
        layout.addSpacing(8)

        # Pilot profile
        profile = QFrame()
        profile.setObjectName("ProfileBlock")
        profile.setCursor(Qt.PointingHandCursor)
        profile.setToolTip("Set the pilot name used for training results")
        profile.mouseReleaseEvent = lambda event: self.profile_clicked.emit()
        row = QHBoxLayout(profile)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(10)
        self.avatar = QLabel()
        self.avatar.setObjectName("Avatar")
        self.avatar.setFixedSize(32, 32)
        self.avatar.setAlignment(Qt.AlignCenter)
        row.addWidget(self.avatar)
        text_col = QVBoxLayout()
        text_col.setSpacing(0)
        self.profile_name_label = QLabel()
        self.profile_name_label.setObjectName("ProfileName")
        text_col.addWidget(self.profile_name_label)
        self.profile_caption = theme.label("Pilot", "hint")
        text_col.addWidget(self.profile_caption)
        row.addLayout(text_col, 1)
        layout.addWidget(profile)

        self.set_pilot_name("")
        self._active = None
        theme.signals.changed.connect(self._on_theme_changed)
        self._on_theme_changed()
        self.set_active("home")

    def _add_button(self, layout, key, text, icon_name):
        button = QPushButton("  " + text)
        button.setCheckable(True)
        button.setCursor(Qt.PointingHandCursor)
        button.setIconSize(QSize(18, 18))
        button.clicked.connect(lambda _checked, k=key: self.panel_selected.emit(k))
        button.toggled.connect(lambda _checked, k=key: self._refresh_icon(k))
        layout.addWidget(button)
        self.buttons[key] = button
        self._icons[key] = icon_name
        self.button_group.addButton(button)
        self._refresh_icon(key)

    def _refresh_icon(self, key):
        button = self.buttons[key]
        button.setIcon(theme.icon(self._icons[key], "accent" if button.isChecked() else None, 18))

    def _on_theme_changed(self, *_):
        for key in self.buttons:
            self._refresh_icon(key)
        self.mark.setPixmap(theme.icon("drone", "on_accent", 20).pixmap(20, 20))

    # -- selection --------------------------------------------------------------

    def set_active(self, key):
        for k, btn in self.buttons.items():
            btn.setChecked(k == key)
        self._active = key
        self._place_indicator(animate=self.isVisible())

    def _place_indicator(self, animate=False):
        button = self.buttons.get(self._active)
        if button is None or button.width() == 0:
            self.indicator.hide()
            return
        target = QRect(button.geometry())
        self.indicator.show()
        self.indicator.lower()
        if animate and self.indicator.geometry().height() > 0:
            animation.move_to(self.indicator, target, duration=200)
        else:
            self.indicator.setGeometry(target)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_indicator()

    def showEvent(self, event):
        super().showEvent(event)
        self._place_indicator()

    # -- profile -------------------------------------------------------------------

    def set_pilot_name(self, name: str):
        self.profile_name_label.setText(name or "Set pilot name")
        self.avatar.setText(_initials(name) if name else "")
        if not name:
            self.avatar.setPixmap(theme.icon("user", "on_accent", 16).pixmap(16, 16))
