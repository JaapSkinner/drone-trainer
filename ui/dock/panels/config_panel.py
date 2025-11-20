from PyQt5.QtWidgets import (QWidget, QLabel, QVBoxLayout, QComboBox, 
                             QSlider, QGroupBox, QFormLayout)
from PyQt5.QtCore import Qt, pyqtSignal
from services.input_service import InputType


class ConfigPanel(QWidget):
    """Configuration panel for input device settings"""
    NavTag = "config"
    
    # Signals to notify when settings change
    input_type_changed = pyqtSignal(object)  # Emits InputType
    sensitivity_changed = pyqtSignal(float)  # Emits sensitivity value
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
    
    def init_ui(self):
        """Initialize the user interface"""
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignTop)
        
        # Title
        title = QLabel("Configuration Panel")
        title.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title)
        
        # Input Device Settings Group
        input_group = QGroupBox("Input Device Settings")
        input_layout = QFormLayout()
        
        # Input Type Selection
        self.input_type_combo = QComboBox()
        self.input_type_combo.addItem("Controller", InputType.CONTROLLER)
        self.input_type_combo.addItem("WASD Keys", InputType.WASD)
        self.input_type_combo.addItem("Arrow Keys", InputType.ARROW_KEYS)
        self.input_type_combo.currentIndexChanged.connect(self.on_input_type_changed)
        input_layout.addRow("Input Type:", self.input_type_combo)
        
        # Sensitivity Slider
        self.sensitivity_slider = QSlider(Qt.Horizontal)
        self.sensitivity_slider.setMinimum(10)  # 0.1 * 100
        self.sensitivity_slider.setMaximum(500)  # 5.0 * 100
        self.sensitivity_slider.setValue(100)  # 1.0 * 100 (default)
        self.sensitivity_slider.setTickPosition(QSlider.TicksBelow)
        self.sensitivity_slider.setTickInterval(50)
        self.sensitivity_slider.valueChanged.connect(self.on_sensitivity_changed)
        
        self.sensitivity_label = QLabel("1.0x")
        sensitivity_container = QWidget()
        sensitivity_layout = QVBoxLayout(sensitivity_container)
        sensitivity_layout.setContentsMargins(0, 0, 0, 0)
        sensitivity_layout.addWidget(self.sensitivity_slider)
        sensitivity_layout.addWidget(self.sensitivity_label)
        
        input_layout.addRow("Sensitivity:", sensitivity_container)
        
        input_group.setLayout(input_layout)
        layout.addWidget(input_group)
        
        # Input Mapping Info Group
        mapping_group = QGroupBox("Input Mapping")
        mapping_layout = QVBoxLayout()
        
        self.mapping_info = QLabel()
        self.mapping_info.setWordWrap(True)
        self.mapping_info.setStyleSheet("font-size: 11px; color: #555;")
        mapping_layout.addWidget(self.mapping_info)
        
        mapping_group.setLayout(mapping_layout)
        layout.addWidget(mapping_group)
        
        # Update mapping info for default selection
        self.update_mapping_info(InputType.CONTROLLER)
    
    def on_input_type_changed(self, index):
        """Handle input type selection change"""
        input_type = self.input_type_combo.itemData(index)
        self.update_mapping_info(input_type)
        self.input_type_changed.emit(input_type)
    
    def on_sensitivity_changed(self, value):
        """Handle sensitivity slider change"""
        sensitivity = value / 100.0
        self.sensitivity_label.setText(f"{sensitivity:.1f}x")
        self.sensitivity_changed.emit(sensitivity)
    
    def update_mapping_info(self, input_type):
        """Update the mapping information display based on input type"""
        if input_type == InputType.CONTROLLER:
            info = """<b>Controller Mapping:</b><br>
            • Left Stick: Move (X/Z)<br>
            • Right Stick: Rotate<br>
            • LB/RB: Move Up/Down<br>
            • LT/RT: Rotate Z-axis"""
        elif input_type == InputType.WASD:
            info = """<b>WASD Mapping:</b><br>
            • W/S: Forward/Backward<br>
            • A/D: Strafe Left/Right<br>
            • Q/E: Move Up/Down<br>
            • R/F: Rotate"""
        elif input_type == InputType.ARROW_KEYS:
            info = """<b>Arrow Keys Mapping:</b><br>
            • Up/Down: Forward/Backward<br>
            • Left/Right: Strafe Left/Right<br>
            • Page Up/Down: Move Up/Down<br>
            • Home/End: Rotate"""
        else:
            info = "Unknown input type"
        
        self.mapping_info.setText(info)
    
    def get_current_input_type(self):
        """Get the currently selected input type"""
        return self.input_type_combo.currentData()
    
    def get_current_sensitivity(self):
        """Get the current sensitivity value"""
        return self.sensitivity_slider.value() / 100.0