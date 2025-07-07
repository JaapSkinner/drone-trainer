from PyQt5.QtWidgets import QWidget,QLabel, QFrame, QHBoxLayout,QVBoxLayout, QPushButton, QSizePolicy, QButtonGroup
from PyQt5.QtCore import pyqtSignal,Qt
from ui.style import load_stylesheet

class SideNavbar(QWidget):
    panel_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(200)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.setObjectName("SideNavbar")
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        
        # Title block
        title_frame = QFrame()
        title_layout = QHBoxLayout(title_frame)
        title_layout.setContentsMargins(8, 8, 8, 8)
        title_layout.setSpacing(8)
        title_frame.setObjectName("NavbarTitle")

        # Icon (placeholder circle)
        icon = QLabel()
        icon.setFixedSize(24, 24)
        icon.setStyleSheet("""
            background-color: #4caf50;
            border-radius: 12px;
        """)

        # Title text
        title_label = QLabel("DRONE TRAINER ")
        title_label.setObjectName("NavbarTitleText")

        title_layout.addWidget(icon)
        title_layout.addWidget(title_label)
        layout.addWidget(title_frame)
        

        self.buttons = {}
        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)  # Only one checked

        for name in ["Home", "Trainer", "Leaderboard","Config", "Vicon", "Live Data"]:
            key = name.lower().replace(" ", "_")
            btn = QPushButton(name)
            btn.setCheckable(True)
            layout.addWidget(btn)
            self.buttons[key] = btn
            self.button_group.addButton(btn)
            btn.clicked.connect(lambda _, k=key: self.panel_selected.emit(k))
            btn.setCursor(Qt.PointingHandCursor)

        layout.addStretch()

        # Settings button at bottom
        settings_btn = QPushButton("Settings")
        settings_btn.setCheckable(True)
        layout.addWidget(settings_btn)
        self.buttons["settings"] = settings_btn
        self.button_group.addButton(settings_btn)
        settings_btn.clicked.connect(lambda _, k="settings": self.panel_selected.emit(k))
        settings_btn.setCursor(Qt.PointingHandCursor)
        
        # Profile block
        profile_frame = QFrame()
        profile_frame.setObjectName("ProfileBlock")
        profile_frame.setCursor(Qt.PointingHandCursor)
        profile_layout = QHBoxLayout(profile_frame)
        profile_layout.setContentsMargins(8, 4, 8, 4)
        profile_layout.setSpacing(8)

        # Profile image
        avatar = QLabel()
        avatar.setFixedSize(32, 32)
        avatar.setStyleSheet("""
            background-color: #888;
            border-radius: 16px;
        """)
        
        # Profile name
        name_label = QLabel("Jaap")
        name_label.setObjectName("ProfileName")

        profile_layout.addWidget(avatar)
        profile_layout.addWidget(name_label)
        layout.addWidget(profile_frame)
        
        
        
        
        self.setStyleSheet(load_stylesheet('ui/navbar/navbar.qss'))
        self.set_active("home")

    def set_active(self, key):
        for k, btn in self.buttons.items():
            btn.setChecked(k == key)
