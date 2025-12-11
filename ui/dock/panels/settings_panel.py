from PyQt5.QtWidgets import (QWidget, QLabel, QVBoxLayout, QSlider, 
                             QGroupBox, QFormLayout, QPushButton)
from PyQt5.QtCore import Qt, pyqtSignal


class SettingsPanel(QWidget):
    """Settings panel for viewport and application settings."""
    NavTag = "settings"
    
    # Signals to notify when viewport settings change
    zoom_sensitivity_changed = pyqtSignal(float)
    reset_camera_requested = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
    
    def init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignTop)
        
        # Title
        title = QLabel("Settings")
        title.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title)
        
        # Viewport Settings Group
        viewport_group = QGroupBox("Viewport Controls")
        viewport_layout = QFormLayout()
        
        # Zoom Sensitivity Slider
        self.zoom_sensitivity_slider = QSlider(Qt.Horizontal)
        self.zoom_sensitivity_slider.setMinimum(10)   # 0.1 * 100
        self.zoom_sensitivity_slider.setMaximum(300)  # 3.0 * 100
        self.zoom_sensitivity_slider.setValue(100)    # 1.0 * 100 (default)
        self.zoom_sensitivity_slider.setTickPosition(QSlider.TicksBelow)
        self.zoom_sensitivity_slider.setTickInterval(50)
        self.zoom_sensitivity_slider.valueChanged.connect(self.on_zoom_sensitivity_changed)
        
        self.zoom_sensitivity_label = QLabel("1.0x")
        zoom_container = QWidget()
        zoom_layout = QVBoxLayout(zoom_container)
        zoom_layout.setContentsMargins(0, 0, 0, 0)
        zoom_layout.addWidget(self.zoom_sensitivity_slider)
        zoom_layout.addWidget(self.zoom_sensitivity_label)
        
        viewport_layout.addRow("Zoom Sensitivity:", zoom_container)
        
        # Reset Camera Button
        self.reset_camera_btn = QPushButton("Reset Camera")
        self.reset_camera_btn.clicked.connect(self.on_reset_camera_clicked)
        viewport_layout.addRow("", self.reset_camera_btn)
        
        viewport_group.setLayout(viewport_layout)
        layout.addWidget(viewport_group)
        
        # Viewport Controls Info Group
        info_group = QGroupBox("Viewport Controls Info")
        info_layout = QVBoxLayout()
        
        info_text = QLabel("""<b>Mouse Controls:</b><br>
        • Left Click + Drag: Orbit camera<br>
        • Scroll Wheel: Zoom in/out<br>
        <br>
        <b>Zoom Limits:</b><br>
        • Minimum distance: 2 units<br>
        • Maximum distance: 50 units""")
        info_text.setWordWrap(True)
        info_text.setStyleSheet("font-size: 11px; color: #555;")
        info_layout.addWidget(info_text)
        
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)
    
    def on_zoom_sensitivity_changed(self, value):
        """Handle zoom sensitivity slider change."""
        sensitivity = value / 100.0
        self.zoom_sensitivity_label.setText(f"{sensitivity:.1f}x")
        self.zoom_sensitivity_changed.emit(sensitivity)
    
    def on_reset_camera_clicked(self):
        """Handle reset camera button click."""
        self.reset_camera_requested.emit()
    
    def get_zoom_sensitivity(self):
        """Get the current zoom sensitivity value."""
        return self.zoom_sensitivity_slider.value() / 100.0