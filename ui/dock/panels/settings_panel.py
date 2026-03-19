from PyQt5.QtWidgets import (QWidget, QLabel, QVBoxLayout, QSlider, 
                             QGroupBox, QFormLayout, QPushButton, QComboBox,
                             QDoubleSpinBox, QSpinBox, QCheckBox, QLineEdit,
                             QScrollArea, QHBoxLayout, QToolButton, QFrame, QSizePolicy)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QStyle, QApplication
from models.debug_text import DebugText
from models.structs import MavlinkGlobalSettings


class CollapsibleBox(QWidget):
    """A simple collapsible container with a header (box-like) and arrow.

    Header acts as a toggle. Content is provided via setContentWidget.
    """
    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self._title = title
        self.toggle_button = QToolButton()
        # Use text-only button and include a simple caret glyph as the indicator
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(False)
        self.toggle_button.setAutoRaise(True)
        self.toggle_button.setObjectName("SectionHeader")

        # Make the header/button full-width and left-aligned
        self.toggle_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        # Ensure the text aligns to the left and give a bit of left padding so the caret isn't jammed
        # Keep this minimal because the global QSS also styles SectionHeader
        self.toggle_button.setStyleSheet("text-align: left; padding-left: 6px;")

        # initial closed caret + title (with a small gap)
        self._closed_caret = "▸"
        self._open_caret = "▾"
        self._update_button_text(False)

        # Content area
        self.content_area = QWidget()
        self.content_area.setVisible(False)
        self._content_layout = QVBoxLayout(self.content_area)
        self._content_layout.setContentsMargins(8, 4, 8, 8)
        self._content_layout.setSpacing(6)

        # Layout for the whole widget
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.toggle_button)
        main_layout.addWidget(self.content_area)

        # Connect toggle
        self.toggle_button.clicked.connect(self._on_toggled)

        # Make header look like a box: wrap in a frame for styling if needed
        self.header_frame = QFrame()
        # ensure the header frame expands horizontally as well
        self.header_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        header_layout = QHBoxLayout(self.header_frame)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addWidget(self.toggle_button)
        # replace toggle button in main layout with header frame for styling hook
        main_layout.removeWidget(self.toggle_button)
        main_layout.insertWidget(0, self.header_frame)

    def _update_button_text(self, opened: bool):
        caret = self._open_caret if opened else self._closed_caret
        # two-space separation for clear visual gap
        self.toggle_button.setText(f"{caret}  {self._title}")

    def _on_toggled(self, checked: bool):
        self.content_area.setVisible(checked)
        self._update_button_text(checked)

    def setContentWidget(self, widget: QWidget):
        # Clear existing
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        self._content_layout.addWidget(widget)

    def setTitle(self, title: str):
        self._title = title
        self._update_button_text(self.toggle_button.isChecked())


class SettingsPanel(QWidget):
    """Settings panel for viewport, application, and MAVLink settings."""
    NavTag = "settings"

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

        # Create three collapsible boxes instead of a QToolBox
        self.settings_groups = []

        viewport_box = CollapsibleBox("Viewport")
        viewport_box.setContentWidget(self._create_section_widget(
            self._create_viewport_group(), self._create_info_group()
        ))
        layout.addWidget(viewport_box)
        self.settings_groups.append(viewport_box)

        mavlink_box = CollapsibleBox("MAVLink")
        mavlink_box.setContentWidget(self._create_section_widget(self._create_mavlink_settings_group()))
        layout.addWidget(mavlink_box)
        self.settings_groups.append(mavlink_box)

        io_box = CollapsibleBox("Import / Export")
        io_box.setContentWidget(self._create_section_widget(self._create_io_group()))
        layout.addWidget(io_box)
        self.settings_groups.append(io_box)

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
