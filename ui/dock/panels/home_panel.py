"""Home: what the app is, the usual first steps, and credits."""
import webbrowser

from PyQt5.QtCore import QSize, Qt, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ui import theme

GITHUB_URL = "https://github.com/JaapSkinner/drone-trainer"
SPONSOR_URL = "https://dtrg.org"
SPONSOR_LOGO = "ui/assets/dtrg_full.png"

# (key, icon, title, description) — key "add_drone" opens the wizard, the rest are panel NavTags.
QUICK_ACTIONS = (
    ("add_drone", "plus", "Add a drone", "Model, motion capture and flight controller, step by step"),
    ("motion_capture", "radar", "Connect motion capture", "Vicon or OptiTrack, and calibrate the axes"),
    ("command", "move", "Fly", "Move a drone to a setpoint, jog it or use a controller"),
    ("trainer", "gamepad-2", "Train", "Hover, race gates and other games, with a leaderboard"),
)


class ActionTile(QPushButton):
    """A large clickable card: an icon, a title and a line of explanation."""

    def __init__(self, icon_name, title, description, primary=False, parent=None):
        super().__init__(parent)
        self.setProperty("variant", "tile-primary" if primary else "tile")
        self.setCursor(Qt.PointingHandCursor)
        self._icon_name, self._primary = icon_name, primary
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 12, 14, 12)
        row.setSpacing(12)
        self.icon_label = QLabel()
        self.icon_label.setObjectName("TileIcon" if not primary else "TileIconPrimary")
        self.icon_label.setFixedSize(36, 36)
        self.icon_label.setAlignment(Qt.AlignCenter)
        row.addWidget(self.icon_label, 0, Qt.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(1)
        text.addWidget(theme.label(title, "option-title"))
        text.addWidget(theme.label(description, "hint", wrap=True))
        row.addLayout(text, 1)
        self.chevron = QLabel()
        row.addWidget(self.chevron, 0, Qt.AlignVCenter)
        theme.signals.changed.connect(self._on_theme_changed)
        self._on_theme_changed()

    # A QPushButton sizes itself to its (empty) text; size the tile to its content instead.
    def sizeHint(self):
        return QSize(super().sizeHint().width(), self.layout().sizeHint().height())

    def minimumSizeHint(self):
        return QSize(super().minimumSizeHint().width(), self.layout().minimumSize().height())

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self.layout().totalHeightForWidth(width)

    @pyqtSlot(object)
    def _on_theme_changed(self, _palette=None):
        tone = "on_accent" if self._primary else "accent"
        self.icon_label.setPixmap(theme.icon(self._icon_name, tone, 18).pixmap(18, 18))
        self.chevron.setPixmap(theme.icon("chevron-right", "muted", 16).pixmap(16, 16))


class HomePanel(QWidget):
    NavTag = "home"
    add_drone_requested = pyqtSignal()
    navigate_requested = pyqtSignal(str)    # a panel NavTag

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignTop)

        # -- hero ---------------------------------------------------------------
        hero = QHBoxLayout()
        hero.setContentsMargins(2, 6, 2, 4)
        hero.setSpacing(14)
        self.mark = QLabel()
        self.mark.setObjectName("HomeMark")
        self.mark.setFixedSize(52, 52)
        self.mark.setAlignment(Qt.AlignCenter)
        hero.addWidget(self.mark, 0, Qt.AlignTop)
        hero_text = QVBoxLayout()
        hero_text.setSpacing(2)
        hero_text.addWidget(theme.label("Drone Trainer", "display"))
        hero_text.addWidget(theme.label("Mission control for indoor drone training: track, fly and practise.",
                                        "hint", wrap=True))
        hero.addLayout(hero_text, 1)
        layout.addLayout(hero)
        layout.addSpacing(6)

        # -- getting started ------------------------------------------------------
        layout.addWidget(theme.section("Get started"))
        self.tiles = {}
        for key, icon_name, title, description in QUICK_ACTIONS:
            tile = ActionTile(icon_name, title, description, primary=(key == "add_drone"))
            tile.setToolTip("Set up a drone step by step: model, tracking and flight controller"
                            if key == "add_drone" else f"Open {title}")
            tile.clicked.connect(lambda _checked=False, k=key: self._on_tile_clicked(k))
            layout.addWidget(tile)
            self.tiles[key] = tile

        # -- links ----------------------------------------------------------------
        links = QHBoxLayout()
        links.setContentsMargins(0, 4, 0, 0)
        self.github_button = theme.button("View on GitHub", "ghost", "link", "sm")
        self.github_button.clicked.connect(lambda: webbrowser.open_new_tab(GITHUB_URL))
        links.addWidget(self.github_button)
        links.addStretch()
        layout.addLayout(links)
        layout.addStretch(1)

        # -- sponsor credit -------------------------------------------------------
        divider = QFrame()
        divider.setProperty("role", "divider")
        layout.addWidget(divider)
        sponsor = QHBoxLayout()
        sponsor.setContentsMargins(2, 6, 2, 8)
        sponsor.setSpacing(10)
        sponsor_text = QVBoxLayout()
        sponsor_text.setSpacing(4)
        sponsor_text.addWidget(theme.section("Sponsored by"))
        logo = QLabel()
        pixmap = QPixmap(SPONSOR_LOGO)
        if not pixmap.isNull():
            scaled = pixmap.scaledToHeight(46 * 2, Qt.SmoothTransformation)   # 46 px tall, sharp on HiDPI
            scaled.setDevicePixelRatio(2)
            logo.setPixmap(scaled)
        else:
            logo.setText("Drone Technology Research Group")
        logo.setToolTip("Drone Technology Research Group")
        sponsor_text.addWidget(logo)
        sponsor.addLayout(sponsor_text, 1)
        self.sponsor_button = theme.button("dtrg.org", "ghost", None, "sm")
        self.sponsor_button.clicked.connect(lambda: webbrowser.open_new_tab(SPONSOR_URL))
        sponsor.addWidget(self.sponsor_button, 0, Qt.AlignBottom)
        layout.addLayout(sponsor)

        theme.signals.changed.connect(self._on_theme_changed)
        self._on_theme_changed()

    @pyqtSlot(object)
    def _on_theme_changed(self, _palette=None):
        self.mark.setPixmap(theme.icon("drone", "on_accent", 30).pixmap(30, 30))

    def _on_tile_clicked(self, key):
        if key == "add_drone":
            self.add_drone_requested.emit()
        else:
            self.navigate_requested.emit(key)
