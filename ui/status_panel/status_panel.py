"""
Status Panel for displaying service health information.

This panel shows the current status of:
- Motion capture (Vicon) connection
- MAVLink drone connections
- Input device status
"""
from PyQt5.QtWidgets import QFrame, QLabel, QVBoxLayout
from PyQt5.QtCore import Qt
from ui.style import load_stylesheet
from services.service_base import ServiceLevel


class StatusPanel(QFrame):
    """Overlay panel displaying service health status.
    
    Shows color-coded status indicators for:
    - Motion capture (Vicon) connection
    - MAVLink connections and message rate
    - Input device (controller/keyboard)
    """
    
    def __init__(self, parent=None):
        """Initialize the status panel.
        
        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self.setObjectName("StatusPanel")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedSize(270, 110)  # Increased height for better layout
        self.setStyleSheet(load_stylesheet('ui/status_panel/status_panel.qss'))
        

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)


        self.vicon_label = QLabel("Motion Capture: Unknown")
        self.mavlink_label = QLabel("MAVLink: Not Connected")
        self.input_label = QLabel("Input Device: Unknown")

        layout.addWidget(self.vicon_label)
        layout.addWidget(self.mavlink_label)
        layout.addWidget(self.input_label)
        
    def handle_status_change(self, level: int, label: str, target=""):
        """Handle status change from a service.
        
        Args:
            level: ServiceLevel enum value
            label: Status label text
            target: Target service identifier ('vicon', 'mavlink', 'input')
        """
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
            "vicon": (self.vicon_label, "Motion Capture"),
            "mavlink": (self.mavlink_label, "MAVLink"),
            "input": (self.input_label, "Input Device"),
            "joystick": (self.input_label, "Input Device"),  # Legacy compatibility
        }

        if target in label_map:
            label_widget, prefix = label_map[target]
            label_widget.setText(f"{prefix}: {text}")
            label_widget.setStyleSheet(f"color: {color};")
