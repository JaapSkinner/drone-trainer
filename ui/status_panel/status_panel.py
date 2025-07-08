from PyQt5.QtWidgets import QFrame, QLabel, QVBoxLayout
from PyQt5.QtCore import Qt
from ui.style import load_stylesheet
from services.service_base import ServiceLevel

class StatusPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("StatusPanel")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedSize(270, 90)
        self.setStyleSheet(load_stylesheet('ui/status_panel/status_panel.qss'))
        

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)


        self.vicon_label = QLabel("Motion Capture (vicon) : Unknown")
        self.mavlink_label = QLabel("Mavlink: Unknown")
        self.joystick_label = QLabel("Joystick: Unknown")

        layout.addWidget(self.vicon_label)
        layout.addWidget(self.mavlink_label)
        layout.addWidget(self.joystick_label)
        
    def handle_status_change(self, level: int, label: str, target=""):
        level_enum = ServiceLevel(level)
        text = label if label else level_enum.name.capitalize()

        color_map = {
            ServiceLevel.RUNNING: "green",
            ServiceLevel.WARNING: "orange",
            ServiceLevel.ERROR: "red",
            ServiceLevel.STOPPED: "gray",
        }

        color = color_map.get(level_enum, "gray")

        label_map = {
            "vicon": (self.vicon_label, "Motion Capture (vicon)"),
            "mavlink": (self.mavlink_label, "Mavlink"),
            "joystick": (self.joystick_label, "Joystick"),
        }

        if target in label_map:
            label_widget, prefix = label_map[target]
            label_widget.setText(f"{prefix}: {text}")
            label_widget.setStyleSheet(f"color: {color};")
