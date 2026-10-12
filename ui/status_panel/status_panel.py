"""
Status Panel for displaying service health information.

This panel shows the current status of:
- Motion capture (Vicon) connection
- MAVLink drone connections
- Input device status
"""
from PyQt5.QtWidgets import QFrame, QLabel, QLayout, QVBoxLayout
from PyQt5.QtCore import Qt, pyqtSlot
from services.service_base import ServiceLevel
from ui import theme

_TOKENS = {
    ServiceLevel.RUNNING: "success",
    ServiceLevel.WARNING: "warning",
    ServiceLevel.ERROR: "danger",
    ServiceLevel.STOPPED: "text_muted",
}


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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(5)
        # Grow/shrink with the status text; stays anchored to the top-right.
        layout.setSizeConstraint(QLayout.SetFixedSize)
        self.setMinimumWidth(250)

        self.motion_capture_label = QLabel()
        self.mavlink_label = QLabel()
        self.input_label = QLabel()
        self._states = {}   # label → (prefix, level, text)
        for widget, prefix, text in ((self.motion_capture_label, "Motion Capture", "Not connected"),
                                     (self.mavlink_label, "MAVLink", "Not Connected"),
                                     (self.input_label, "Input Device", "Unknown")):
            widget.setTextFormat(Qt.RichText)
            layout.addWidget(widget)
            self._set_row(widget, prefix, ServiceLevel.STOPPED, text)
        theme.signals.changed.connect(self._on_theme_changed)

    def _set_row(self, widget, prefix, level, text):
        self._states[widget] = (prefix, level, text)
        dot = theme.colour(_TOKENS.get(level, "text_muted"))
        widget.setText(f'<span style="color:{dot}; font-size:15px;">●</span>&nbsp; '
                       f'<span style="color:{theme.colour("text_secondary")};">{prefix}</span>&nbsp; '
                       f'<span style="color:{theme.colour("text")}; font-weight:600;">{text}</span>')
        widget.setToolTip(f"{prefix}: {text}")

    def _on_theme_changed(self, *_):
        for widget, (prefix, level, text) in self._states.items():
            self._set_row(widget, prefix, level, text)

    MARGIN = 20

    def anchor_top_right(self):
        """Place the panel in its parent's top-right corner."""
        parent = self.parentWidget()
        if parent is not None:
            self.adjustSize()
            self.move(parent.width() - self.width() - self.MARGIN, self.MARGIN)

    @pyqtSlot(int, str, str)
    def handle_status_change(self, level: int, label: str, target=""):
        """Handle status change from a service.
        
        Args:
            level: ServiceLevel enum value
            label: Status label text
            target: Target service identifier ('motion_capture', 'mavlink', 'input')
        """
        level_enum = ServiceLevel(level)
        text = label if label else level_enum.name.capitalize()

        label_map = {
            "motion_capture": (self.motion_capture_label, "Motion Capture"),
            "vicon": (self.motion_capture_label, "Motion Capture"),  # Legacy compatibility
            "mavlink": (self.mavlink_label, "MAVLink"),
            "input": (self.input_label, "Input Device"),
            "joystick": (self.input_label, "Input Device"),  # Legacy compatibility
        }

        if target in label_map:
            label_widget, prefix = label_map[target]
            
            # Hide mavlink label if no connections/objects (empty label means hide)
            if target == "mavlink" and (not label or level_enum == ServiceLevel.STOPPED):
                label_widget.setVisible(False)
            else:
                label_widget.setVisible(True)
                self._set_row(label_widget, prefix, level_enum, text)
            self.anchor_top_right()
