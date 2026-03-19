from PyQt5.QtWidgets import (QWidget, QLabel, QVBoxLayout, QSlider, 
                             QGroupBox, QFormLayout, QPushButton, QComboBox,
                             QDoubleSpinBox, QSpinBox, QCheckBox, QLineEdit,
                             QScrollArea, QHBoxLayout, QToolBox)
from PyQt5.QtCore import Qt, pyqtSignal
from models.debug_text import DebugText
from models.structs import MavlinkGlobalSettings
from services.input_service import InputType


class SettingsPanel(QWidget):
    """Settings panel for viewport, application, and MAVLink settings."""
    NavTag = "settings"
    
    # Signals to notify when input settings change
    input_type_changed = pyqtSignal(object)  # Emits InputType
    sensitivity_changed = pyqtSignal(float)  # Emits sensitivity value

    # Signals to notify when viewport settings change
    zoom_sensitivity_changed = pyqtSignal(float)
    reset_camera_requested = pyqtSignal()
    lock_object_changed = pyqtSignal(object)  # Emits SceneObject or None
    
    # Signal for MAVLink settings changes
    mavlink_settings_changed = pyqtSignal(object)  # Emits MavlinkGlobalSettings
    # Signals for import/export actions requested from the UI
    import_settings_requested = pyqtSignal()
    export_settings_requested = pyqtSignal()

    def __init__(self, parent=None, object_service=None, mavlink_service=None):
        super().__init__(parent)
        self.object_service = object_service
        self.mavlink_service = mavlink_service
        self._mavlink_settings = MavlinkGlobalSettings()
        self.init_ui()
    
    def init_ui(self):
        """Initialize the user interface."""
        main_layout = QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignTop)
        
        # Title
        title = QLabel("Settings")
        title.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 10px;")
        main_layout.addWidget(title)
        
        # Scroll area for all settings
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setAlignment(Qt.AlignTop)

        self.settings_toolbox = QToolBox()
        self.settings_toolbox.addItem(
            self._create_section_widget(
                self._create_input_group(),
                self._create_mapping_group()
            ),
            "Input Controls"
        )
        self.settings_toolbox.addItem(
            self._create_section_widget(
                self._create_viewport_group(),
                self._create_info_group()
            ),
            "Viewport"
        )
        self.settings_toolbox.addItem(
            self._create_section_widget(self._create_mavlink_settings_group()),
            "MAVLink"
        )
        self.settings_toolbox.addItem(
            self._create_section_widget(self._create_io_group()),
            "Import / Export"
        )
        layout.addWidget(self.settings_toolbox)
        layout.addStretch(1)
        
        scroll.setWidget(content)
        main_layout.addWidget(scroll)

    def _create_section_widget(self, *widgets):
        section = QWidget()
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(0, 0, 0, 0)
        section_layout.setSpacing(8)
        for widget in widgets:
            section_layout.addWidget(widget)
        section_layout.addStretch(1)
        return section

    def _create_input_group(self):
        """Create the input device settings group."""
        input_group = QGroupBox("Input Device Settings")
        input_layout = QFormLayout()

        self.input_type_combo = QComboBox()
        self.input_type_combo.addItem("Controller", InputType.CONTROLLER)
        self.input_type_combo.addItem("WASD Keys", InputType.WASD)
        self.input_type_combo.addItem("Arrow Keys", InputType.ARROW_KEYS)
        self.input_type_combo.currentIndexChanged.connect(self.on_input_type_changed)
        input_layout.addRow("Input Type:", self.input_type_combo)

        self.sensitivity_slider = QSlider(Qt.Horizontal)
        self.sensitivity_slider.setMinimum(10)   # 0.1 * 100
        self.sensitivity_slider.setMaximum(500)  # 5.0 * 100
        self.sensitivity_slider.setValue(100)    # 1.0 * 100
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
        return input_group

    def _create_mapping_group(self):
        """Create the input mapping info group."""
        mapping_group = QGroupBox("Input Mapping")
        mapping_layout = QVBoxLayout()

        self.mapping_info = QLabel()
        self.mapping_info.setWordWrap(True)
        self.mapping_info.setStyleSheet("font-size: 11px; color: #555;")
        mapping_layout.addWidget(self.mapping_info)

        mapping_group.setLayout(mapping_layout)
        self.update_mapping_info(InputType.CONTROLLER)
        return mapping_group
    
    def _create_viewport_group(self):
        """Create the viewport settings group."""
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
        return viewport_group
    
    def _create_io_group(self):
        """Create a small group containing Import / Export buttons."""
        group = QGroupBox("Import / Export")
        layout = QHBoxLayout()
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        self.import_btn = QPushButton("Import Settings")
        self.export_btn = QPushButton("Export Settings")
        self.import_btn.clicked.connect(self._on_import_clicked)
        self.export_btn.clicked.connect(self._on_export_clicked)

        layout.addStretch(1)
        layout.addWidget(self.import_btn)
        layout.addWidget(self.export_btn)
        group.setLayout(layout)
        return group

    def _create_mavlink_settings_group(self):
        """Create the MAVLink global settings group."""
        group = QGroupBox("MAVLink Global Settings")
        layout = QFormLayout()
        
        # Default connection string
        self.mavlink_conn_edit = QLineEdit(self._mavlink_settings.default_connection_string)
        self.mavlink_conn_edit.setPlaceholderText("udpin:0.0.0.0:14550")
        self.mavlink_conn_edit.textChanged.connect(
            lambda text: self._update_mavlink_setting('default_connection_string', text)
        )
        layout.addRow("Default Connection:", self.mavlink_conn_edit)
        
        # Source System ID
        self.source_system_spin = QSpinBox()
        self.source_system_spin.setRange(1, 255)
        self.source_system_spin.setValue(self._mavlink_settings.source_system_id)
        self.source_system_spin.valueChanged.connect(
            lambda val: self._update_mavlink_setting('source_system_id', val)
        )
        layout.addRow("Source System ID:", self.source_system_spin)
        
        # Source Component ID
        self.source_component_spin = QSpinBox()
        self.source_component_spin.setRange(0, 255)
        self.source_component_spin.setValue(self._mavlink_settings.source_component_id)
        self.source_component_spin.valueChanged.connect(
            lambda val: self._update_mavlink_setting('source_component_id', val)
        )
        layout.addRow("Source Component ID:", self.source_component_spin)
        
        # Default MoCap Rate
        self.mocap_rate_spin = QDoubleSpinBox()
        self.mocap_rate_spin.setRange(1, 200)
        self.mocap_rate_spin.setValue(self._mavlink_settings.default_mocap_rate_hz)
        self.mocap_rate_spin.setSuffix(" Hz")
        self.mocap_rate_spin.valueChanged.connect(
            lambda val: self._update_mavlink_setting('default_mocap_rate_hz', val)
        )
        layout.addRow("Default MoCap Rate:", self.mocap_rate_spin)
        
        # Default Setpoint Rate
        self.setpoint_rate_spin = QDoubleSpinBox()
        self.setpoint_rate_spin.setRange(1, 100)
        self.setpoint_rate_spin.setValue(self._mavlink_settings.default_setpoint_rate_hz)
        self.setpoint_rate_spin.setSuffix(" Hz")
        self.setpoint_rate_spin.valueChanged.connect(
            lambda val: self._update_mavlink_setting('default_setpoint_rate_hz', val)
        )
        layout.addRow("Default Setpoint Rate:", self.setpoint_rate_spin)
        
        # Telemetry Rate
        self.telemetry_rate_spin = QDoubleSpinBox()
        self.telemetry_rate_spin.setRange(1, 50)
        self.telemetry_rate_spin.setValue(self._mavlink_settings.telemetry_rate_hz)
        self.telemetry_rate_spin.setSuffix(" Hz")
        self.telemetry_rate_spin.valueChanged.connect(
            lambda val: self._update_mavlink_setting('telemetry_rate_hz', val)
        )
        layout.addRow("Telemetry Rate:", self.telemetry_rate_spin)
        
        # Heartbeat Interval
        self.heartbeat_spin = QDoubleSpinBox()
        self.heartbeat_spin.setRange(0.5, 5.0)
        self.heartbeat_spin.setValue(self._mavlink_settings.heartbeat_interval)
        self.heartbeat_spin.setSuffix(" s")
        self.heartbeat_spin.setSingleStep(0.5)
        self.heartbeat_spin.valueChanged.connect(
            lambda val: self._update_mavlink_setting('heartbeat_interval', val)
        )
        layout.addRow("Heartbeat Interval:", self.heartbeat_spin)
        
        # Connection Timeout
        self.timeout_spin = QDoubleSpinBox()
        self.timeout_spin.setRange(1, 30)
        self.timeout_spin.setValue(self._mavlink_settings.connection_timeout)
        self.timeout_spin.setSuffix(" s")
        self.timeout_spin.valueChanged.connect(
            lambda val: self._update_mavlink_setting('connection_timeout', val)
        )
        layout.addRow("Connection Timeout:", self.timeout_spin)
        
        # Setpoint Sanitization
        self.sanitize_cb = QCheckBox()
        self.sanitize_cb.setChecked(self._mavlink_settings.enable_setpoint_sanitization)
        self.sanitize_cb.stateChanged.connect(
            lambda state: self._update_mavlink_setting('enable_setpoint_sanitization', state == 2)
        )
        layout.addRow("Enable Setpoint Checks:", self.sanitize_cb)
        
        # Max Position Magnitude
        self.max_pos_spin = QDoubleSpinBox()
        self.max_pos_spin.setRange(1, 1000)
        self.max_pos_spin.setValue(self._mavlink_settings.max_position_magnitude)
        self.max_pos_spin.setSuffix(" m")
        self.max_pos_spin.valueChanged.connect(
            lambda val: self._update_mavlink_setting('max_position_magnitude', val)
        )
        layout.addRow("Max Position:", self.max_pos_spin)
        
        # Max Velocity Magnitude
        self.max_vel_spin = QDoubleSpinBox()
        self.max_vel_spin.setRange(0.1, 50)
        self.max_vel_spin.setValue(self._mavlink_settings.max_velocity_magnitude)
        self.max_vel_spin.setSuffix(" m/s")
        self.max_vel_spin.valueChanged.connect(
            lambda val: self._update_mavlink_setting('max_velocity_magnitude', val)
        )
        layout.addRow("Max Velocity:", self.max_vel_spin)
        
        # Max Yaw Rate
        self.max_yaw_spin = QDoubleSpinBox()
        self.max_yaw_spin.setRange(0.1, 10)
        self.max_yaw_spin.setValue(self._mavlink_settings.max_yaw_rate)
        self.max_yaw_spin.setSuffix(" rad/s")
        self.max_yaw_spin.valueChanged.connect(
            lambda val: self._update_mavlink_setting('max_yaw_rate', val)
        )
        layout.addRow("Max Yaw Rate:", self.max_yaw_spin)
        
        # Auto Reconnect
        self.auto_reconnect_cb = QCheckBox()
        self.auto_reconnect_cb.setChecked(self._mavlink_settings.auto_reconnect)
        self.auto_reconnect_cb.stateChanged.connect(
            lambda state: self._update_mavlink_setting('auto_reconnect', state == 2)
        )
        layout.addRow("Auto Reconnect:", self.auto_reconnect_cb)
        
        # Reconnect Interval
        self.reconnect_spin = QDoubleSpinBox()
        self.reconnect_spin.setRange(1, 60)
        self.reconnect_spin.setValue(self._mavlink_settings.reconnect_interval)
        self.reconnect_spin.setSuffix(" s")
        self.reconnect_spin.valueChanged.connect(
            lambda val: self._update_mavlink_setting('reconnect_interval', val)
        )
        layout.addRow("Reconnect Interval:", self.reconnect_spin)
        
        # Auto Connect Discovered
        self.auto_connect_cb = QCheckBox()
        self.auto_connect_cb.setChecked(self._mavlink_settings.auto_connect_discovered)
        self.auto_connect_cb.setToolTip("Automatically connect to MAVLink devices found during discovery")
        self.auto_connect_cb.stateChanged.connect(
            lambda state: self._update_mavlink_setting('auto_connect_discovered', state == 2)
        )
        layout.addRow("Auto Connect Discovered:", self.auto_connect_cb)
        
        group.setLayout(layout)
        return group
    
    def _create_info_group(self):
        """Create the viewport controls info group."""
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
        return info_group
    
    def _update_mavlink_setting(self, param, value):
        """Update a MAVLink global setting and emit signal."""
        setattr(self._mavlink_settings, param, value)
        self.mavlink_settings_changed.emit(self._mavlink_settings)
        
        # Also update the service if available
        if self.mavlink_service is not None:
            self.mavlink_service.update_global_settings(self._mavlink_settings)
    
    def set_mavlink_service(self, mavlink_service):
        """Set the mavlink service reference.
        
        Args:
            mavlink_service: MAVLink service instance
        """
        self.mavlink_service = mavlink_service
        
        # Load settings from service if available
        if mavlink_service is not None:
            self._mavlink_settings = mavlink_service.get_global_settings()
            self._refresh_mavlink_ui()
    
    def _refresh_mavlink_ui(self):
        """Refresh the MAVLink UI with current settings."""
        s = self._mavlink_settings
        
        # Block signals during refresh
        widgets = [
            self.mavlink_conn_edit, self.source_system_spin, self.source_component_spin,
            self.mocap_rate_spin, self.setpoint_rate_spin, self.telemetry_rate_spin,
            self.heartbeat_spin, self.timeout_spin, self.sanitize_cb, self.max_pos_spin,
            self.max_vel_spin, self.max_yaw_spin, self.auto_reconnect_cb, self.reconnect_spin,
            self.auto_connect_cb
        ]
        for w in widgets:
            w.blockSignals(True)
        
        self.mavlink_conn_edit.setText(s.default_connection_string)
        self.source_system_spin.setValue(s.source_system_id)
        self.source_component_spin.setValue(s.source_component_id)
        self.mocap_rate_spin.setValue(s.default_mocap_rate_hz)
        self.setpoint_rate_spin.setValue(s.default_setpoint_rate_hz)
        self.telemetry_rate_spin.setValue(s.telemetry_rate_hz)
        self.heartbeat_spin.setValue(s.heartbeat_interval)
        self.timeout_spin.setValue(s.connection_timeout)
        self.sanitize_cb.setChecked(s.enable_setpoint_sanitization)
        self.max_pos_spin.setValue(s.max_position_magnitude)
        self.max_vel_spin.setValue(s.max_velocity_magnitude)
        self.max_yaw_spin.setValue(s.max_yaw_rate)
        self.auto_reconnect_cb.setChecked(s.auto_reconnect)
        self.reconnect_spin.setValue(s.reconnect_interval)
        self.auto_connect_cb.setChecked(s.auto_connect_discovered)
        
        for w in widgets:
            w.blockSignals(False)
    
    def get_mavlink_settings(self) -> MavlinkGlobalSettings:
        """Get the current MAVLink global settings.
        
        Returns:
            Current MAVLink global settings
        """
        return self._mavlink_settings
    
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

    def on_input_type_changed(self, index):
        """Handle input type selection change."""
        input_type = self.input_type_combo.itemData(index)
        self.update_mapping_info(input_type)
        self.input_type_changed.emit(input_type)

    def on_sensitivity_changed(self, value):
        """Handle sensitivity slider change."""
        sensitivity = value / 100.0
        self.sensitivity_label.setText(f"{sensitivity:.1f}x")
        self.sensitivity_changed.emit(sensitivity)

    def update_mapping_info(self, input_type):
        """Update mapping information for selected input type."""
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

    def set_input_type(self, input_type):
        """Set the current input type selection without emitting signals."""
        for i in range(self.input_type_combo.count()):
            if self.input_type_combo.itemData(i) == input_type:
                self.input_type_combo.blockSignals(True)
                self.input_type_combo.setCurrentIndex(i)
                self.input_type_combo.blockSignals(False)
                self.update_mapping_info(input_type)
                break

    def set_input_sensitivity(self, sensitivity):
        """Set input sensitivity without emitting signals."""
        value = max(10, min(500, int(round(float(sensitivity) * 100))))
        self.sensitivity_slider.blockSignals(True)
        self.sensitivity_slider.setValue(value)
        self.sensitivity_slider.blockSignals(False)
        self.sensitivity_label.setText(f"{value / 100.0:.1f}x")

    def get_current_input_type(self):
        """Get the currently selected input type."""
        return self.input_type_combo.currentData()

    def get_current_sensitivity(self):
        """Get the current input sensitivity value."""
        return self.sensitivity_slider.value() / 100.0
    
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

    def _on_import_clicked(self):
        """Emit a request to import settings (MainWindow handles the dialog)."""
        self.import_settings_requested.emit()

    def _on_export_clicked(self):
        """Emit a request to export settings (MainWindow handles the dialog)."""
        self.export_settings_requested.emit()
