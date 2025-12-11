from PyQt5.QtWidgets import (QWidget, QLabel, QVBoxLayout, QSlider, 
                             QGroupBox, QFormLayout, QPushButton, QComboBox)
from PyQt5.QtCore import Qt, pyqtSignal
from models.debug_text import DebugText


class SettingsPanel(QWidget):
    """Settings panel for viewport and application settings."""
    NavTag = "settings"
    
    # Signals to notify when viewport settings change
    zoom_sensitivity_changed = pyqtSignal(float)
    reset_camera_requested = pyqtSignal()
    lock_object_changed = pyqtSignal(object)  # Emits SceneObject or None
    
    def __init__(self, parent=None, object_service=None):
        super().__init__(parent)
        self.object_service = object_service
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
        
        # Lock View dropdown
        self.lock_object_combo = QComboBox()
        self.lock_object_combo.addItem("None (Origin)", None)
        self.lock_object_combo.currentIndexChanged.connect(self.on_lock_object_changed)
        viewport_layout.addRow("Lock View To:", self.lock_object_combo)
        
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
        <b>Lock View:</b><br>
        • Select an object to orbit around it<br>
        • Camera follows object as it moves<br>
        <br>
        <b>Zoom Limits:</b><br>
        • Minimum distance: 2 units<br>
        • Maximum distance: 50 units""")
        info_text.setWordWrap(True)
        info_text.setStyleSheet("font-size: 11px; color: #555;")
        info_layout.addWidget(info_text)
        
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)
    
    def set_object_service(self, object_service):
        """Set the object service and populate the lock object dropdown."""
        self.object_service = object_service
        self.refresh_object_list()
    
    def refresh_object_list(self):
        """Refresh the lock object dropdown with current objects."""
        if self.object_service is None:
            return
        
        # Store current selection
        current_obj = self.lock_object_combo.currentData()
        
        # Clear and repopulate
        self.lock_object_combo.blockSignals(True)
        self.lock_object_combo.clear()
        self.lock_object_combo.addItem("None (Origin)", None)
        
        for obj in self.object_service.get_objects():
            # Only include controllable objects, exclude debug/utility objects
            is_controllable = getattr(obj, 'controllable', False)
            is_debug_text = isinstance(obj, DebugText)
            if is_controllable and not is_debug_text:
                self.lock_object_combo.addItem(obj.name, obj)
        
        # Restore selection if still valid
        if current_obj is not None:
            for i in range(self.lock_object_combo.count()):
                if self.lock_object_combo.itemData(i) == current_obj:
                    self.lock_object_combo.setCurrentIndex(i)
                    break
        
        self.lock_object_combo.blockSignals(False)
    
    def on_lock_object_changed(self, index):
        """Handle lock object selection change."""
        obj = self.lock_object_combo.currentData()
        self.lock_object_changed.emit(obj)
    
    def on_zoom_sensitivity_changed(self, value):
        """Handle zoom sensitivity slider change."""
        sensitivity = value / 100.0
        self.zoom_sensitivity_label.setText(f"{sensitivity:.1f}x")
        self.zoom_sensitivity_changed.emit(sensitivity)
    
    def on_reset_camera_clicked(self):
        """Handle reset camera button click."""
        # Reset UI controls to default values
        self.lock_object_combo.setCurrentIndex(0)
        self.zoom_sensitivity_slider.setValue(100)  # Reset to 1.0x
        self.reset_camera_requested.emit()
    
    def reset_ui_to_defaults(self):
        """Reset all UI controls to default values.
        
        Called when camera is reset externally to keep UI in sync.
        """
        self.lock_object_combo.blockSignals(True)
        self.zoom_sensitivity_slider.blockSignals(True)
        
        self.lock_object_combo.setCurrentIndex(0)
        self.zoom_sensitivity_slider.setValue(100)
        self.zoom_sensitivity_label.setText("1.0x")
        
        self.lock_object_combo.blockSignals(False)
        self.zoom_sensitivity_slider.blockSignals(False)
    
    def get_zoom_sensitivity(self):
        """Get the current zoom sensitivity value."""
        return self.zoom_sensitivity_slider.value() / 100.0