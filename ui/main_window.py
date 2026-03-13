from PyQt5.QtCore import QTimer, Qt, pyqtSlot
from PyQt5.QtWidgets import QMainWindow, QSplitter,QHBoxLayout, QWidget, QApplication
from PyQt5.QtGui import QFontDatabase, QFont

from services.input_service import InputService, InputType
from services.object_service import ObjectService
from services.status_service import StatusService
from services.mavlink_service import MavlinkService
from services.storage_service import StorageService

from ui.gl_widget.gl_widget import GLWidget
from ui.dock.dock_manager import DockManager
from models.structs import PositionData, MavlinkGlobalSettings, MavlinkConnectionConfig
from models.storage_models import AppSettings, ConnectionEntry
from ui.navbar.navbar import SideNavbar
from ui.style import load_stylesheet
from ui.status_panel.status_panel import StatusPanel


class MainWindow(QMainWindow):
    """Main application window for the Drone Trainer.
    
    Integrates all services and UI components including:
    - Object service for scene management
    - Input service for controller/keyboard input
    - MAVLink service for drone communication
    - Status service for health monitoring
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        # Load and set global font
        font_id = QFontDatabase.addApplicationFont('ui/assets/fonts/NotoSan.ttf')
        if font_id != -1:
            family = QFontDatabase.applicationFontFamilies(font_id)[0]
            QFontDatabase.addApplicationFont('ui/assets/fonts/NotoSan.ttf')
            self.setFont(QFont(family, 11))
            QApplication.setFont(QFont(family, 11))

        # --- Persistent storage (loaded synchronously before other services) ---
        self.storage_service = StorageService()
        self.storage_service.on_start()  # load data from disk immediately

        # self.vicon = vicon

        self.object_service = ObjectService(None, debug_level=None)  # Use default debug level

        self.glWidget = None
        self.initUI()

        # --- Apply persisted settings to UI and services ---
        saved = self.storage_service.get_settings()

        # Resolve input type from stored string
        input_type_map = {t.value.lower(): t for t in InputType}
        restored_input_type = input_type_map.get(
            saved.input_type.lower(), InputType.CONTROLLER
        )

        # Initialize input service with persisted settings
        self.input_service = InputService(
            self.glWidget,
            input_type=restored_input_type,
            sensitivity=saved.input_sensitivity
        )
        self.object_service.load_input_service(self.input_service)
        
        # Connect GL widget to input service for keyboard events
        self.glWidget.set_input_service(self.input_service)
        
        # Connect input service to command panel for setpoint-based control
        self.input_service.set_command_panel(self.command_panel)

        # Initialize MAVLink service for drone communication
        # TODO: Validate DTRG-Mavlink dialect presence at runtime, wire any remaining custom DTRG
        #       message handling, and surface a UI warning when DTRG_DIALECT_BUILT is False.
        self.mavlink_service = MavlinkService()

        # Apply persisted MAVLink global settings
        mavlink_settings = self._build_mavlink_settings(saved)
        self.mavlink_service.update_global_settings(mavlink_settings)

        # Restore saved connections into the mavlink service
        for entry in self.storage_service.list_connections():
            config = MavlinkConnectionConfig(
                connection_string=entry.connection_string,
                system_id=entry.system_id,
                component_id=entry.component_id,
                source_system=entry.source_system,
                source_component=entry.source_component,
                heartbeat_interval=entry.heartbeat_interval,
                mocap_rate_hz=entry.mocap_rate_hz,
                name=entry.name,
                linked_object_name=entry.linked_object_name,
            )
            self.mavlink_service.save_connection_config(config)
        
        # Connect mavlink service to dock panel
        self.dock.set_mavlink_service(self.mavlink_service)

        # Apply persisted viewport zoom sensitivity
        if hasattr(self, 'glWidget') and self.glWidget:
            self.glWidget.set_zoom_sensitivity(saved.zoom_sensitivity)
        # Sync the settings panel slider
        self.settings_panel.zoom_sensitivity_slider.blockSignals(True)
        self.settings_panel.zoom_sensitivity_slider.setValue(int(saved.zoom_sensitivity * 100))
        self.settings_panel.zoom_sensitivity_label.setText(f"{saved.zoom_sensitivity:.1f}x")
        self.settings_panel.zoom_sensitivity_slider.blockSignals(False)

        self.status_service = StatusService(
            self.status_panel,
            self.input_service,
            self.mavlink_service
        )
        self.status_service.start()
        
        
        self.input_service.input_updated.connect(self.on_input_update)
        self.input_service.start()
        
        # Start mavlink service
        self.mavlink_service.start()
        
        # self.vicon.position_updated.connect(self.update_vicon_position)
        
        # --- Wire auto-save hooks ---
        self.settings_panel.zoom_sensitivity_changed.connect(self._on_save_zoom_sensitivity)
        self.settings_panel.mavlink_settings_changed.connect(self._on_save_mavlink_settings)
        self.mavlink_service.connection_changed.connect(self._on_connection_changed)

        # Pass storage service to mavlink panel so connection edits/deletes
        # are automatically persisted.
        self.dock.mavlink_panel.set_storage_service(self.storage_service)

        self.setStyleSheet(load_stylesheet('ui/main_window.qss'))


    def initUI(self):
        self.setWindowTitle('Collaborative Control Interface')
        self.setGeometry(50, 50, 1200, 800)

        # Top-level horizontal layout
        central_widget = QWidget(self)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        self.setCentralWidget(central_widget)

        # NavBar on far left
        self.navbar = SideNavbar()
        main_layout.addWidget(self.navbar)

        # Dock and GLWidget on the right
        self.glWidget = GLWidget(object_service=self.object_service)
        self.dock = DockManager(self.glWidget, self, self.object_service)
        self.config_panel = self.dock.panels[3]   # Config panel
        self.object_panel = self.dock.panels[5]   # Object/Live Data panel
        self.settings_panel = self.dock.panels[6]  # Settings panel
        self.command_panel = self.dock.panels[7]   # Command panel

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.dock)
        splitter.addWidget(self.glWidget)
        splitter.setStretchFactor(1, 1)  # let GLWidget expand
        main_layout.addWidget(splitter)
        splitter.setCollapsible(0, False)  # Prevent dock collapsing
        splitter.setCollapsible(1, False)  # Prevent GL collapsing
        self.glWidget.setMinimumWidth(200)
        self.dock.setMinimumWidth(380)  # Increased to prevent horizontal scroll and button clipping
        
        self.navbar.panel_selected.connect(self.dock.set_active_panel)
        
        # Connect config panel signals to input service
        self.config_panel.input_type_changed.connect(self.on_input_type_changed)
        self.config_panel.sensitivity_changed.connect(self.on_sensitivity_changed)
        
        # Connect command panel signals to input service (joystick settings moved here)
        self.command_panel.input_type_changed.connect(self.on_input_type_changed)
        self.command_panel.sensitivity_changed.connect(self.on_sensitivity_changed)
        
        # Connect settings panel signals to viewport
        self.settings_panel.zoom_sensitivity_changed.connect(self.on_zoom_sensitivity_changed)
        self.settings_panel.reset_camera_requested.connect(self.on_reset_camera_requested)
        self.settings_panel.lock_object_changed.connect(self.on_lock_object_changed)
        
        # Connect GLWidget signals to settings panel for UI sync
        self.glWidget.camera_reset.connect(self.settings_panel.reset_ui_to_defaults)
        
        # Populate settings panel with objects after they're created
        self.settings_panel.refresh_object_list()
        
        # Populate command panel with objects after they're created
        self.command_panel.refresh_object_list()
        
        # Connect command panel joystick control signal
        self.command_panel.joystick_control_enabled.connect(self.on_joystick_control_enabled)
        
        # === Overlay container ===
        self.overlay = QWidget(central_widget)
        self.overlay.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.overlay.setStyleSheet("background: transparent;")
        self.overlay.setGeometry(self.rect())
        self.overlay.raise_()

        # === Status panel inside overlay ===
        self.status_panel = StatusPanel(self.overlay)
        self.status_panel.move(self.width() - self.status_panel.width() - 20, 20)
        self.status_panel.show()



    @pyqtSlot(PositionData)
    def update_vicon_position(self, pos_data: PositionData):
        for obj in self.glWidget.objects:
            if obj.tracked and obj.name == pos_data.name:
                obj.x_pos = pos_data.x
                obj.y_pos = pos_data.y
                obj.z_pos = pos_data.z
                obj.x_rot = pos_data.x_rot
                obj.y_rot = pos_data.y_rot
                obj.z_rot = pos_data.z_rot
        self.object_panel.refresh()

    @pyqtSlot(object)
    def on_input_update(self, obj):
        """Handle input device updates (replaces on_joystick_update)"""
        self.object_panel.refresh()
        # Update command panel position display live
        if hasattr(self, 'command_panel'):
            self.command_panel.refresh()
        self.glWidget.update()
    
    @pyqtSlot(object)
    def on_input_type_changed(self, input_type):
        """Handle input type change from config panel or command panel"""
        if hasattr(self, 'input_service'):
            self.input_service.set_input_type(input_type)
        # Persist input type
        if hasattr(self, 'storage_service'):
            settings = self.storage_service.get_settings()
            settings.input_type = input_type.value if hasattr(input_type, 'value') else str(input_type)
            self.storage_service.update_settings(settings)
    
    @pyqtSlot(float)
    def on_sensitivity_changed(self, sensitivity):
        """Handle sensitivity change from config panel or command panel"""
        if hasattr(self, 'input_service'):
            self.input_service.set_sensitivity(sensitivity)
        # Persist input sensitivity
        if hasattr(self, 'storage_service'):
            settings = self.storage_service.get_settings()
            settings.input_sensitivity = sensitivity
            self.storage_service.update_settings(settings)

    @pyqtSlot(float)
    def on_zoom_sensitivity_changed(self, sensitivity):
        """Handle zoom sensitivity change from settings panel"""
        if hasattr(self, 'glWidget') and self.glWidget:
            self.glWidget.set_zoom_sensitivity(sensitivity)
    
    @pyqtSlot()
    def on_reset_camera_requested(self):
        """Handle reset camera request from settings panel"""
        if hasattr(self, 'glWidget') and self.glWidget:
            self.glWidget.reset_camera()
    
    @pyqtSlot(object)
    def on_lock_object_changed(self, obj):
        """Handle lock object change from settings panel"""
        if hasattr(self, 'glWidget') and self.glWidget:
            self.glWidget.set_locked_object(obj)
    
    @pyqtSlot(bool)
    def on_joystick_control_enabled(self, enabled):
        """Handle joystick control enable/disable from command panel.
        
        Joystick is now always live when in Joystick mode. Ghost mode affects
        whether it updates next_setpoint (preview) or setpoint directly.
        """
        if hasattr(self, 'input_service') and self.input_service:
            if enabled:
                # Enable joystick control - set controlled object
                if hasattr(self, 'object_service') and self.object_service:
                    obj = self.object_service.get_controlled_object()
                    if obj is not None:
                        self.input_service.set_controlled_object(obj)
                # Return focus to viewport so controller/keyboard input works immediately
                if hasattr(self, 'glWidget') and self.glWidget:
                    self.glWidget.setFocus()
            else:
                # Disable joystick control - set controlled object to None
                self.input_service.set_controlled_object(None)
        
    # ------------------------------------------------------------------
    # Storage auto-save hooks
    # ------------------------------------------------------------------

    @staticmethod
    def _build_mavlink_settings(saved: AppSettings) -> MavlinkGlobalSettings:
        """Create a MavlinkGlobalSettings from persisted AppSettings."""
        return MavlinkGlobalSettings(
            default_connection_string=saved.default_connection_string,
            default_mocap_rate_hz=saved.default_mocap_rate_hz,
            default_setpoint_rate_hz=saved.default_setpoint_rate_hz,
            telemetry_rate_hz=saved.telemetry_rate_hz,
            heartbeat_interval=saved.heartbeat_interval,
            connection_timeout=saved.connection_timeout,
            enable_setpoint_sanitization=saved.enable_setpoint_sanitization,
            max_position_magnitude=saved.max_position_magnitude,
            max_velocity_magnitude=saved.max_velocity_magnitude,
            max_yaw_rate=saved.max_yaw_rate,
            source_system_id=saved.source_system_id,
            source_component_id=saved.source_component_id,
            auto_reconnect=saved.auto_reconnect,
            reconnect_interval=saved.reconnect_interval,
            auto_connect_discovered=saved.auto_connect_discovered,
        )

    def _on_save_zoom_sensitivity(self, value: float):
        """Persist zoom sensitivity when the slider changes."""
        settings = self.storage_service.get_settings()
        settings.zoom_sensitivity = value
        self.storage_service.update_settings(settings)

    def _on_save_mavlink_settings(self, mavlink_settings):
        """Persist MAVLink global settings when any field changes."""
        settings = self.storage_service.get_settings()
        settings.default_connection_string = mavlink_settings.default_connection_string
        settings.default_mocap_rate_hz = mavlink_settings.default_mocap_rate_hz
        settings.default_setpoint_rate_hz = mavlink_settings.default_setpoint_rate_hz
        settings.telemetry_rate_hz = mavlink_settings.telemetry_rate_hz
        settings.heartbeat_interval = mavlink_settings.heartbeat_interval
        settings.connection_timeout = mavlink_settings.connection_timeout
        settings.enable_setpoint_sanitization = mavlink_settings.enable_setpoint_sanitization
        settings.max_position_magnitude = mavlink_settings.max_position_magnitude
        settings.max_velocity_magnitude = mavlink_settings.max_velocity_magnitude
        settings.max_yaw_rate = mavlink_settings.max_yaw_rate
        settings.source_system_id = mavlink_settings.source_system_id
        settings.source_component_id = mavlink_settings.source_component_id
        settings.auto_reconnect = mavlink_settings.auto_reconnect
        settings.reconnect_interval = mavlink_settings.reconnect_interval
        settings.auto_connect_discovered = mavlink_settings.auto_connect_discovered
        self.storage_service.update_settings(settings)

    def _on_connection_changed(self, system_id: int, connected: bool):
        """Persist connection configs whenever a connection is added or removed.
        
        This is triggered by the mavlink_service.connection_changed signal.
        After a connect, the active connection config is upserted.
        After a disconnect, the mavlink_service already saves the config in
        _saved_connections; we mirror that to persistent storage.
        """
        self._sync_connections_to_storage()

    def _sync_connections_to_storage(self):
        """Write the current set of known connections to persistent storage."""
        all_conns = self.mavlink_service.get_all_connections()
        # Build the set of connection names we want to keep
        current_names = set()
        for name, config in all_conns.items():
            entry = ConnectionEntry(
                name=name,
                connection_string=config.connection_string,
                system_id=config.system_id,
                component_id=config.component_id,
                source_system=config.source_system,
                source_component=config.source_component,
                heartbeat_interval=config.heartbeat_interval,
                mocap_rate_hz=config.mocap_rate_hz,
                linked_object_name=config.linked_object_name,
            )
            self.storage_service.upsert_connection(entry)
            current_names.add(name)

        # Remove any entries no longer known to the mavlink service
        for stored in self.storage_service.list_connections():
            if stored.name not in current_names:
                self.storage_service.delete_connection(stored.name)

    def changeEvent(self, event):
        """Handle window state changes, including focus loss."""
        from PyQt5.QtCore import QEvent as _QEvent
        super().changeEvent(event)
        if event.type() == _QEvent.ActivationChange and not self.isActiveWindow():
            # Window lost focus — clear keyboard states to avoid stuck keys
            if hasattr(self, 'input_service') and self.input_service:
                self.input_service.clear_key_states()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.overlay.setGeometry(self.rect())
        self.status_panel.move(self.width() - self.status_panel.width() - 20, 20)

    def closeEvent(self, event):
        """Properly stop all services before closing the application."""
        # Persist latest connection state before shutting down
        if hasattr(self, 'storage_service') and hasattr(self, 'mavlink_service'):
            self._sync_connections_to_storage()

        # Stop services to ensure timers are stopped in their own threads
        if hasattr(self, 'status_service'):
            self.status_service.stop()
        if hasattr(self, 'input_service'):
            self.input_service.stop()
        if hasattr(self, 'mavlink_service'):
            self.mavlink_service.stop()
        
        # Stop the GL widget timer
        if hasattr(self, 'glWidget') and self.glWidget and hasattr(self.glWidget, 'timer'):
            self.glWidget.timer.stop()
        
        # Accept the close event
        super().closeEvent(event)
        event.accept()