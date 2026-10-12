import logging
import os
from collections import deque
from PyQt5.QtCore import Qt, pyqtSlot, pyqtSignal
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QDialog,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
import json

from services.input_service import InputService, InputType
from services.object_service import ObjectService
from services.status_service import StatusService
from services.mavlink_service import MavlinkService
from services.storage_service import StorageService
from services.motion_capture_service import MotionCaptureService
from services.control_service import ControlService
from services.trainer_service import TrainerService

from ui.gl_widget.gl_widget import GLWidget
from ui.gl_widget.setpoint_overlay import SetpointOverlay
from ui.dock.dock_manager import DockManager
from models.structs import MotionCaptureConfig, MavlinkGlobalSettings, MavlinkConnectionConfig, MavlinkObjectConfig
from models.storage_models import AppSettings, ConnectionEntry
from models.default_scene import build_default_scene
from ui.navbar.navbar import SideNavbar
from ui import theme
from ui.splash import app_icon
from ui.widgets.toast import Toast, notifier as toast_notifier, toast
from ui.status_panel.status_panel import StatusPanel
from services.app_logging import get_log_file_path
from services.paths import session_scene_path
from models import scene_io

logger = logging.getLogger(__name__)
_OBJECT_STATUS_DEBUG_PREFIX = "Debug text "

class QtLogHandler(logging.Handler):
    def __init__(self, window):
        super().__init__()
        self._window = window
        self.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%H:%M:%S",
            )
        )

    def emit(self, record):
        try:
            message = self.format(record)
            self._window.log_message_received.emit(message)
        except Exception:
            pass


class MainWindow(QMainWindow):
    """Main application window for the Drone Trainer.
    
    Integrates all services and UI components including:
    - Object service for scene management
    - Input service for controller/keyboard input
    - MAVLink service for drone communication
    - Status service for health monitoring
    """
    
    log_message_received = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._root_log_handler = None
        self._service_status_seen = {}
        # --- Persistent storage (loaded synchronously before other services) ---
        # Load settings from disk first (synchronously) so the UI can use them
        # for initial configuration. Create the ObjectService before the
        # StorageService to avoid any cross-affinity side-effects when the
        # storage service constructs its internal QThread.
        saved = StorageService.load_settings_from_disk()
        initial_connections = StorageService.load_connections_from_disk()

        # Look and feel (fonts, colours, icons) before any widget is built.
        theme.apply(saved.ui_theme if saved.ui_theme in theme.PALETTES else "light")
        self.setWindowIcon(app_icon())

        # Create object service early (before StorageService) to preserve
        # the previous construction order and avoid moveToThread races.
        self.object_service = ObjectService(None, debug_level=None)  # Use default debug level
        # Resolved once, like the storage directory, so the scene is always saved
        # next to this window's settings.
        self._session_scene_path = session_scene_path()
        self.object_service.add_objects(self._load_startup_scene(self._session_scene_path))

        # Motion capture feeds tracked object poses into the object service.
        self.motion_capture_service = MotionCaptureService(
            MotionCaptureConfig.from_dict(saved.motion_capture))
        self.motion_capture_service.poses_updated.connect(self.object_service.apply_tracking_poses)

        # Setpoints for controlled objects (red ball / ghost in the viewport).
        self.control_service = ControlService(self.object_service, parent=self)
        # Training games (Trainer panel) and their results (Leaderboard panel).
        self.trainer_service = TrainerService(self.object_service, parent=self)

        # Now instantiate the storage service (its QThread will be created
        # inside ServiceBase.__init__). We'll start it later after UI wiring.
        self.storage_service = StorageService()

        self.glWidget = None
        self.initUI()

        # --- Apply persisted settings to UI and services ---
        # saved = self.storage_service.get_settings()

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

        # Restore saved connections into the mavlink service (loaded from disk)
        for entry in initial_connections:
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
                auto_connect=entry.auto_connect,
            )
            self.mavlink_service.save_connection_config(config)
        
        # Connect mavlink service to dock panel
        self.dock.set_mavlink_service(self.mavlink_service)

        # Apply persisted viewport zoom sensitivity
        if hasattr(self, 'glWidget') and self.glWidget:
            self.glWidget.set_zoom_sensitivity(saved.zoom_sensitivity)
            # Restore camera position/angles if present
            try:
                if getattr(saved, 'camera_distance', None) is not None:
                    self.glWidget.camera_distance = float(saved.camera_distance)
                    self.glWidget.camera_angle_x = float(saved.camera_angle_x)
                    self.glWidget.camera_angle_y = float(saved.camera_angle_y)
            except Exception:
                pass
            # Restore splitter sizes if available
            try:
                if getattr(saved, 'splitter_sizes', None):
                    # Ensure splitter exists and sizes look plausible
                    sizes = list(saved.splitter_sizes)
                    if hasattr(self, 'splitter') and sizes:
                        self.splitter.setSizes(sizes)
            except Exception:
                pass
            # Restore window maximized state
            try:
                if getattr(saved, 'window_maximized', False):
                    self.showMaximized()
            except Exception:
                pass
        # Sync the settings panel slider
        self.settings_panel.zoom_sensitivity_slider.blockSignals(True)
        self.settings_panel.zoom_sensitivity_slider.setValue(int(saved.zoom_sensitivity * 100))
        self.settings_panel.zoom_sensitivity_label.setText(f"{saved.zoom_sensitivity:.1f}x")
        self.settings_panel.zoom_sensitivity_slider.blockSignals(False)

        self.status_service = StatusService(
            self.status_panel,
            self.input_service,
            self.mavlink_service,
            motion_capture_service=self.motion_capture_service,
        )
        self.status_service.start()
        self._wire_service_logging()

        # Start input and MAVLink services after UI + service wiring.
        self.input_service.input_updated.connect(self.on_input_update)
        self.input_service.start()
        self.mavlink_service.start()
        self.motion_capture_service.start()
        
        # Apply persisted per-object MAVLink configs
        try:
            for obj_name, cfg in (saved.object_mavlink_configs or {}).items():
                # Find scene object by name
                for obj in self.object_service.get_objects():
                    if getattr(obj, 'name', None) == obj_name:
                        # Build a minimal MavlinkObjectConfig from stored dict
                        moc = MavlinkObjectConfig(
                            enabled=bool(cfg.get('enabled', False)),
                            connection_string=saved.default_connection_string,
                            system_id=int(cfg.get('system_id', 1)),
                            component_id=1,
                            source_system=saved.source_system_id,
                            source_component=saved.source_component_id,
                            send_mocap=bool(cfg.get('send_mocap', True)),
                            receive_setpoints=False,
                            mocap_rate_hz=0.0,
                            use_global_connection=True,
                            linked_connection_name=cfg.get('linked_connection_name', '')
                        )
                        try:
                            obj.set_mavlink_config(moc)
                        except Exception:
                            pass
                        break
        except Exception:
            pass

        # Activate MAVLink routing for objects that have it enabled, and drop
        # objects from MAVLink when they leave the scene.
        for obj in self.object_service.get_objects():
            if obj.mavlink_config.enabled:
                self.mavlink_service.update_object_config(obj, obj.mavlink_config)
        self.object_service.object_removed.connect(self.mavlink_service.unregister_mavlink_object)

        # Restore active panel
        if getattr(saved, 'active_panel', None):
            self._show_panel(saved.active_panel)

        # Restore locked object if present
        try:
            if getattr(saved, 'last_locked_object', None):
                target_name = saved.last_locked_object
                for obj in self.object_service.get_objects():
                    if getattr(obj, 'name', None) == target_name:
                        self.glWidget.set_locked_object(obj)
                        break
        except Exception:
            pass

        # --- Trainer: pilot name and remembered game settings ---
        self.trainer_panel = self.dock.trainer_panel
        self.trainer_panel.set_pilot_name(saved.pilot_name)
        self.trainer_panel.load_preferences(saved.trainer)
        self.navbar.set_pilot_name(saved.pilot_name)
        self.trainer_panel.pilot_name_changed.connect(self.set_pilot_name)
        self.trainer_panel.preferences_changed.connect(self._on_trainer_preferences_changed)
        self.navbar.profile_clicked.connect(self._on_profile_clicked)

        # --- Wire auto-save hooks ---
        self.settings_panel.zoom_sensitivity_changed.connect(self._on_save_zoom_sensitivity)
        self.settings_panel.mavlink_settings_changed.connect(self._on_save_mavlink_settings)
        self.settings_panel.theme_changed.connect(self._on_theme_changed)
        self.mavlink_service.connection_changed.connect(self._on_connection_changed)

        # Pass storage service to mavlink panel so connection edits/deletes
        # are automatically persisted.
        self.dock.mavlink_panel.set_storage_service(self.storage_service)

        # Start the storage service thread now that UI wiring is done. The
        # service will load again in its own thread and handle future saves.
        try:
            self.storage_service.start()
        except Exception:
            pass

        self.log_message_received.connect(self._append_log_console_message)
        self._setup_app_console()

    def _setup_app_console(self):
        """Create a toggleable console dock with floating overlay toggle button."""
        self.app_console_dock = QDockWidget("Application Console", self)
        self.app_console_dock.setObjectName("applicationConsoleDock")
        self.app_console_dock.setAllowedAreas(Qt.BottomDockWidgetArea | Qt.TopDockWidgetArea)

        self.app_console_output = QPlainTextEdit(self.app_console_dock)
        self.app_console_output.setReadOnly(True)
        self.app_console_output.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.app_console_output.setMaximumBlockCount(4000)
        self.app_console_output.setProperty("role", "console")
        self.app_console_dock.setWidget(self.app_console_output)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.app_console_dock)
        self.app_console_dock.hide()

        # Keep the top menubar hidden for this feature; use a floating overlay button.
        self.menuBar().setVisible(False)
        self.toggle_console_action = QAction("Application Console", self)
        self.toggle_console_action.setShortcut("F12")
        self.toggle_console_action.triggered.connect(self._toggle_app_console)
        self.addAction(self.toggle_console_action)

        self.console_toggle_button = QPushButton(" Console", self.centralWidget())
        self.console_toggle_button.setObjectName("ConsoleToggle")
        self.console_toggle_button.setToolTip("Open/close the application console (F12)")
        self.console_toggle_button.setCursor(Qt.PointingHandCursor)
        theme.set_icon(self.console_toggle_button, "terminal", size=14)
        self.console_toggle_button.clicked.connect(self._toggle_app_console)
        self.console_toggle_button.adjustSize()
        self.console_toggle_button.raise_()
        self._position_overlay_widgets()

        self._root_log_handler = QtLogHandler(self)
        logging.getLogger().addHandler(self._root_log_handler)
        logger.info("Application console initialized (F12 or Console button).")

        # Seed the console with recent file logs so users see output immediately.
        try:
            log_path = get_log_file_path()
            if os.path.exists(log_path):
                with open(log_path, "r", encoding="utf-8") as fh:
                    recent = deque(fh, maxlen=200)
                if recent:
                    self.app_console_output.appendPlainText("--- recent log history ---")
                    self.app_console_output.appendPlainText("".join(recent).rstrip("\n"))
        except Exception:
            logger.exception(
                "Failed to preload recent log history into app console. "
                "Live logging still works; full logs are available at %s",
                get_log_file_path(),
            )

    @pyqtSlot(str)
    def _append_log_console_message(self, message: str):
        if not hasattr(self, "app_console_output") or self.app_console_output is None:
            return
        self.app_console_output.appendPlainText(message)

    def _toggle_app_console(self):
        self.app_console_dock.setVisible(not self.app_console_dock.isVisible())

    def _position_overlay_widgets(self):
        self.status_panel.anchor_top_right()
        try:
            if hasattr(self, "console_toggle_button") and self.console_toggle_button:
                margin = 20
                # Use the parent widget's size to compute coordinates in the correct space
                parent = self.console_toggle_button.parentWidget() or self.centralWidget() or self
                x = parent.width() - self.console_toggle_button.width() - margin
                y = parent.height() - self.console_toggle_button.height() - margin
                # Ensure the button stays within the parent bounds
                x = max(margin, x)
                y = max(margin, y)
                self.console_toggle_button.move(x, y)
        except Exception:
            pass

    def _wire_service_logging(self):
        service_pairs = [
            ("ObjectService", self.object_service),
            ("InputService", self.input_service),
            ("MavlinkService", self.mavlink_service),
            ("MotionCaptureService", self.motion_capture_service),
            ("StorageService", self.storage_service),
            ("StatusService", self.status_service),
        ]
        for service_name, service in service_pairs:
            try:
                service.status_changed.connect(
                    lambda level, label, svc=service_name: self._on_service_status_changed(svc, level, label)
                )
            except Exception:
                logger.exception("Failed to bind status logging for %s", service_name)

    @pyqtSlot(str, int, str)
    def _on_service_status_changed(self, service_name: str, level: int, label: str):
        if service_name == "ObjectService" and label.startswith(_OBJECT_STATUS_DEBUG_PREFIX):
            return
        status_tuple = (level, label)
        if self._service_status_seen.get(service_name) == status_tuple:
            return
        self._service_status_seen[service_name] = status_tuple
        logger.info("%s status changed: level=%s label=%s", service_name, level, label)


    def initUI(self):
        self.setWindowTitle('Drone Trainer')
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
        self.dock = DockManager(self.glWidget, self, self.object_service,
                                motion_capture_service=self.motion_capture_service,
                                control_service=self.control_service,
                                trainer_service=self.trainer_service)
        self.glWidget.overlays = [SetpointOverlay(self.control_service, self.object_service),
                                  self.trainer_service]
        self.trainer_service.hud_changed.connect(self.glWidget.set_game_hud)
        self.dock.motion_capture_panel.config_changed.connect(self.save_motion_capture_config)
        self.objects_panel = self.dock.objects_panel
        self.objects_panel.focus_requested.connect(self.focus_object)
        # Every way into the step-by-step drone setup.
        self.objects_panel.add_drone_requested.connect(lambda: self.open_drone_setup())
        self.dock.home_panel.add_drone_requested.connect(lambda: self.open_drone_setup())
        self.dock.home_panel.navigate_requested.connect(self._show_panel)
        self.dock.command_panel.drone_setup_requested.connect(self.open_drone_setup)
        self.settings_panel = self.dock.settings_panel  # Settings panel
        self.command_panel = self.dock.get_panel("command")

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.dock)
        splitter.addWidget(self.glWidget)
        splitter.setStretchFactor(1, 1)  # let GLWidget expand
        main_layout.addWidget(splitter)
        # Keep a reference to the main splitter so we can persist/restore sizes
        self.splitter = splitter
        splitter.setCollapsible(0, False)  # Prevent dock collapsing
        splitter.setCollapsible(1, False)  # Prevent GL collapsing
        self.glWidget.setMinimumWidth(200)
        self.dock.setMinimumWidth(380)  # Increased to prevent horizontal scroll and button clipping
        
        self.navbar.panel_selected.connect(self.dock.set_active_panel)
        # Persist active panel selection when the navbar changes
        self.navbar.panel_selected.connect(self._on_active_panel_changed)

        # Connect command panel signals to input service (joystick settings moved here)
        self.command_panel.input_type_changed.connect(self.on_input_type_changed)
        self.command_panel.sensitivity_changed.connect(self.on_sensitivity_changed)
        
        # Connect settings panel signals to viewport
        self.settings_panel.zoom_sensitivity_changed.connect(self.on_zoom_sensitivity_changed)
        self.settings_panel.reset_camera_requested.connect(self.on_reset_camera_requested)
        self.settings_panel.lock_object_changed.connect(self.on_lock_object_changed)
        
        # Wire import/export buttons from settings panel into the main handlers
        self.settings_panel.import_settings_requested.connect(self._on_import_settings_triggered)
        self.settings_panel.export_settings_requested.connect(self._on_export_settings_triggered)

        # Give the settings panel access to the object service so it can populate lock list
        try:
            self.settings_panel.set_object_service(self.object_service)
        except Exception:
            pass

        # Connect GLWidget signals to settings panel for UI sync
        self.glWidget.camera_reset.connect(self.settings_panel.reset_ui_to_defaults)
        
        # Keep object lists in the panels in step with the scene.
        self.settings_panel.refresh_object_list()
        self.command_panel.refresh_object_list()
        self.object_service.objects_changed.connect(self.settings_panel.refresh_object_list)
        self.object_service.objects_changed.connect(self.command_panel.refresh_object_list)
        self.object_service.object_removed.connect(self._on_object_removed)
        
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
        self.status_panel.show()
        self.status_panel.anchor_top_right()

        # Short confirmations ("Scene saved") over the bottom of the 3-D view
        self.toast = Toast(self.glWidget)
        toast_notifier.requested.connect(self.toast.show_message)



    @staticmethod
    def _load_startup_scene(path):
        """Objects from the last session, or the default scene on first launch."""
        if os.path.exists(path):
            try:
                objects = scene_io.load_scene(path)
                if objects:
                    logger.info("Restored %d object(s) from %s", len(objects), path)
                    return objects
            except (OSError, ValueError) as exc:
                logger.warning("Could not restore the last scene (%s); using the default scene.", exc)
        return build_default_scene()

    def _save_session_scene(self):
        try:
            scene_io.save_scene(self.object_service.get_objects(), self._session_scene_path)
        except OSError:
            logger.exception("Could not save the scene for next session")

    def open_drone_setup(self, obj=None):
        """Open the Add-a-drone wizard (or re-run it for ``obj``). Returns the dialog."""
        from ui.dialogs.add_drone_wizard import AddDroneWizard
        wizard = AddDroneWizard(self.object_service, self.motion_capture_service, self.mavlink_service,
                                edit_object=obj, parent=self)
        wizard.drone_ready.connect(self._on_drone_ready)
        self._drone_wizard = wizard
        wizard.open()  # window-modal but non-blocking, so live mocap keeps updating it
        return wizard

    def _on_drone_ready(self, obj, options):
        self._sync_connections_to_storage()
        toast(f"{obj.name} is set up")
        if options.get("control"):
            self.command_panel.select_object(obj)
            self._show_panel("command")
        if options.get("follow"):
            self.focus_object(obj)

    def focus_object(self, obj):
        """Lock the camera onto ``obj`` and keep the settings dropdown in sync."""
        combo = self.settings_panel.lock_object_combo
        index = next((i for i in range(combo.count()) if combo.itemData(i) is obj), -1)
        if index >= 0:
            combo.setCurrentIndex(index)  # emits lock_object_changed → on_lock_object_changed
        else:
            self.on_lock_object_changed(obj)

    def _on_object_removed(self, obj):
        if self.glWidget.get_locked_object() is obj:
            self.glWidget.set_locked_object(None)

    @pyqtSlot(str)
    def _show_panel(self, tag: str):
        """Show a dock panel and keep the navbar selection in sync."""
        tag = self.dock.resolve_tag(tag)
        if self.dock.set_active_panel(tag):
            self.navbar.set_active(tag)

    @pyqtSlot(object)
    def on_input_update(self, obj):
        """Handle input device updates (replaces on_joystick_update)"""
        # Update command panel position display live
        if hasattr(self, 'command_panel'):
            self.command_panel.refresh()
        self.glWidget.update()
    
    @pyqtSlot(object)
    def on_input_type_changed(self, input_type):
        """Handle input type change from settings panel or command panel"""
        if hasattr(self, 'input_service'):
            self.input_service.set_input_type(input_type)
            logger.info("Input method changed to: %s", getattr(input_type, "value", str(input_type)))
        # Persist input type
        if hasattr(self, 'storage_service'):
            settings = self.storage_service.get_settings()
            settings.input_type = input_type.value if hasattr(input_type, 'value') else str(input_type)
            self.storage_service.update_settings(settings)
    
    @pyqtSlot(float)
    def on_sensitivity_changed(self, sensitivity):
        """Handle sensitivity change from settings panel or command panel"""
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
        # Persist last locked object name (or empty string)
        if hasattr(self, 'storage_service'):
            settings = self.storage_service.get_settings()
            settings.last_locked_object = obj.name if (obj is not None and hasattr(obj, 'name')) else ""
            self.storage_service.update_settings(settings)

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

    def save_motion_capture_config(self, config: MotionCaptureConfig):
        """Apply and persist motion capture settings."""
        self.motion_capture_service.configure(config)
        settings = self.storage_service.get_settings()
        settings.motion_capture = config.to_dict()
        self.storage_service.update_settings(settings)

    def set_pilot_name(self, name: str):
        """Persist the pilot name and show it in the navbar and Trainer panel."""
        name = (name or "").strip()
        self.navbar.set_pilot_name(name)
        if self.trainer_panel.pilot_name() != name:
            self.trainer_panel.set_pilot_name(name)
        settings = self.storage_service.get_settings()
        if settings.pilot_name != name:
            settings.pilot_name = name
            self.storage_service.update_settings(settings)

    def _on_profile_clicked(self):
        from PyQt5.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Pilot", "Pilot name for training results:",
                                        text=self.trainer_panel.pilot_name())
        if ok:
            self.set_pilot_name(name)

    def _on_trainer_preferences_changed(self, prefs):
        settings = self.storage_service.get_settings()
        settings.trainer = prefs
        self.storage_service.update_settings(settings)

    @pyqtSlot(str)
    def _on_theme_changed(self, name: str):
        """Switch light/dark and remember it."""
        theme.apply(name)
        self.settings_panel.set_theme_name(name)
        settings = self.storage_service.get_settings()
        settings.ui_theme = name
        self.storage_service.update_settings(settings)

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
        
        Args:
            system_id: System ID of the changed connection (unused; full sync performed).
            connected: Whether the connection was established or removed (unused).
        """
        # Persist last active connection if one was just connected
        try:
            if connected and hasattr(self, 'mavlink_service') and hasattr(self, 'storage_service'):
                all_conns = self.mavlink_service.get_all_connections()
                # Find first connection matching system_id
                for name, cfg in all_conns.items():
                    try:
                        if getattr(cfg, 'system_id', None) == system_id:
                            s = self.storage_service.get_settings()
                            s.last_active_connection = name
                            self.storage_service.update_settings(s)
                            break
                    except Exception:
                        continue
        except Exception:
            pass

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
                auto_connect=getattr(config, "auto_connect", True),
            )
            self.storage_service.upsert_connection(entry)
            current_names.add(name)

        # Remove any entries no longer known to the mavlink service
        stale = [s.name for s in self.storage_service.list_connections()
                 if s.name not in current_names]
        for name in stale:
            self.storage_service.delete_connection(name)

    def _on_active_panel_changed(self, tag: str):
        """Persist the currently selected dock panel tag."""
        if hasattr(self, 'storage_service'):
            settings = self.storage_service.get_settings()
            settings.active_panel = tag
            self.storage_service.update_settings(settings)

    def _on_object_mavlink_config_changed(self, obj, config):
        """Persist a minimal per-object MAVLink config when changed from the UI.

        We store only plain serializable fields so storage remains simple.
        """
        if not hasattr(self, 'storage_service'):
            return
        if obj is None or not hasattr(obj, 'name'):
            return
        s = self.storage_service.get_settings()
        # Minimal representation
        s.object_mavlink_configs[obj.name] = {
            'enabled': bool(getattr(config, 'enabled', False)),
            'linked_connection_name': getattr(config, 'linked_connection_name', ''),
            'system_id': int(getattr(config, 'system_id', 0)),
            'send_mocap': bool(getattr(config, 'send_mocap', True)),
        }
        self.storage_service.update_settings(s)

    def changeEvent(self, event):
        """Handle window state changes, including focus loss."""
        from PyQt5.QtCore import QEvent as _QEvent
        super().changeEvent(event)
        # When the window loses activation, clear input key states to avoid stuck keys
        try:
            if event.type() == _QEvent.ActivationChange and not self.isActiveWindow():
                if hasattr(self, 'input_service') and self.input_service:
                    self.input_service.clear_key_states()
        except Exception:
            # Be defensive: don't let UI event handling crash the app
            pass

    def resizeEvent(self, event):
        """Handle widget resize: keep overlay and status positioned."""
        try:
            super().resizeEvent(event)
        except Exception:
            pass
        try:
            self.overlay.setGeometry(self.rect())
            self._position_overlay_widgets()
        except Exception:
            pass

    def closeEvent(self, event):
        """Properly stop all services before closing the application.

        Persist settings and connections, stop threaded services and timers.
        Runs once: the window can be closed again by QApplication.aboutToQuit.
        """
        if getattr(self, "_shut_down", False):
            event.accept()
            return
        self._shut_down = True
        # Persist latest connection state and some UI state
        try:
            if hasattr(self, 'storage_service') and hasattr(self, 'mavlink_service'):
                try:
                    s = self.storage_service.get_settings()
                    s.window_geometry = {'x': self.x(), 'y': self.y(), 'w': self.width(), 'h': self.height()}
                    # Persist camera state if GL widget present
                    try:
                        if hasattr(self, 'glWidget') and self.glWidget is not None:
                            s.camera_distance = float(getattr(self.glWidget, 'camera_distance', s.camera_distance))
                            s.camera_angle_x = float(getattr(self.glWidget, 'camera_angle_x', s.camera_angle_x))
                            s.camera_angle_y = float(getattr(self.glWidget, 'camera_angle_y', s.camera_angle_y))
                    except Exception:
                        pass
                    # Persist splitter sizes if available
                    try:
                        if hasattr(self, 'splitter') and self.splitter is not None:
                            s.splitter_sizes = self.splitter.sizes()
                    except Exception:
                        pass
                    cur = getattr(self.dock, 'current_widget', None)
                    if cur is not None and hasattr(cur, 'NavTag'):
                        s.active_panel = getattr(cur, 'NavTag')
                    self.storage_service.update_settings(s)
                except Exception:
                    pass
                # Ensure connections are synced afterwards
                try:
                    self._sync_connections_to_storage()
                except Exception:
                    pass
        except Exception:
            pass

        self.trainer_service.stop()
        self._save_session_scene()

        # Stop services to ensure timers are stopped in their own threads
        # Include storage_service and object_service so their QThreads are
        # cleanly stopped before the app tears down Qt objects.
        for svc_name in ('status_service', 'input_service', 'mavlink_service', 'motion_capture_service',
                         'storage_service', 'object_service'):
            svc = getattr(self, svc_name, None)
            if svc is not None:
                try:
                    svc.stop()
                except Exception:
                    pass

        # Detach UI logging sink before Qt objects are torn down.
        try:
            if self._root_log_handler is not None:
                logging.getLogger().removeHandler(self._root_log_handler)
                self._root_log_handler = None
        except Exception:
            pass

        # Stop the GL widget timer if present
        try:
            if hasattr(self, 'glWidget') and self.glWidget and hasattr(self.glWidget, 'timer'):
                self.glWidget.timer.stop()
        except Exception:
            pass

        # Accept the close event
        try:
            super().closeEvent(event)
        except Exception:
            pass
        event.accept()

    def _on_import_settings_triggered(self):
        """Handle Import Settings menu action."""
        options = QFileDialog.Options()
        file_name, _ = QFileDialog.getOpenFileName(self, "Import Settings", "", "Settings Files (*.json);;All Files (*)", options=options)
        if not file_name:
            return  # User canceled

        # Parse the file first and show preview
        try:
            with open(file_name, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
        except Exception as e:
            QMessageBox.critical(self, "Import Settings", f"Failed to read/parse file:\n{str(e)}")
            return

        # Show preview dialog and ask user to confirm
        if not self._show_import_preview(file_name, data):
            return

        # Perform the import
        success = self.storage_service.import_from_file(file_name)

        # Show result message
        if success:
            QMessageBox.information(self, "Import Settings", "Settings imported successfully.")
            # Ensure storage service mirrors what's on disk (some imports write nested structure)
            try:
                new_settings = StorageService.load_settings_from_disk()
                # Replace in-memory settings without triggering another disk write
                try:
                    self.storage_service._settings = new_settings
                except Exception:
                    # Fallback: update_settings (safe, small write)
                    try:
                        self.storage_service.update_settings(new_settings)
                    except Exception:
                        pass
            except Exception:
                pass

            # Apply imported settings to the running UI and services
            try:
                self._apply_imported_settings()
            except Exception:
                pass
        else:
            QMessageBox.critical(self, "Import Settings", "Failed to import settings. Please check the file and try again.")

    def _show_import_preview(self, file_name: str, data) -> bool:
        """Show a modal preview dialog for the import. Returns True if user confirms import."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Import Preview")
        dlg.setModal(True)
        layout = QVBoxLayout(dlg)

        info_label = QLabel(f"Previewing: {file_name}")
        layout.addWidget(info_label)

        # Summarize content
        try:
            summary_lines = []
            if isinstance(data, dict):
                keys = list(data.keys())
                summary_lines.append(f"Top-level keys: {', '.join(keys)}")
                if 'connections' in data and isinstance(data['connections'], list):
                    summary_lines.append(f"Connections: {len(data['connections'])} entries")
            elif isinstance(data, list):
                summary_lines.append(f"Connections list: {len(data)} entries")
            else:
                summary_lines.append(f"Data type: {type(data).__name__}")
        except Exception:
            summary_lines = ["Unable to summarize preview."]

        summary_label = QLabel("\n".join(summary_lines))
        layout.addWidget(summary_label)

        # Show a truncated pretty JSON preview
        try:
            pretty = json.dumps(data, indent=2)
            if len(pretty) > 10000:
                pretty = pretty[:10000] + "\n... (truncated)"
        except Exception:
            pretty = str(data)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText(pretty)
        text.setMinimumSize(600, 300)
        layout.addWidget(text)

        # Buttons
        btn_layout = QHBoxLayout()
        import_btn = QPushButton("Import")
        cancel_btn = QPushButton("Cancel")
        btn_layout.addStretch(1)
        btn_layout.addWidget(import_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        result = {'confirmed': False}

        def on_import():
            result['confirmed'] = True
            dlg.accept()

        def on_cancel():
            dlg.reject()

        import_btn.clicked.connect(on_import)
        cancel_btn.clicked.connect(on_cancel)

        dlg.exec_()
        return result['confirmed']

    def _apply_imported_settings(self):
        """Apply settings currently stored in StorageService to the running UI/services

        This mirrors the startup restore logic and is intentionally conservative
        (wrapped in try/except to avoid crashing the UI on malformed imports).
        """
        if not hasattr(self, 'storage_service'):
            return
        s = self.storage_service.get_settings()

        # Apply viewport and UI preferences
        try:
            if hasattr(self, 'glWidget') and self.glWidget:
                self.glWidget.set_zoom_sensitivity(s.zoom_sensitivity)
                try:
                    if getattr(s, 'camera_distance', None) is not None:
                        self.glWidget.camera_distance = float(s.camera_distance)
                        self.glWidget.camera_angle_x = float(s.camera_angle_x)
                        self.glWidget.camera_angle_y = float(s.camera_angle_y)
                except Exception:
                    pass
                try:
                    if getattr(s, 'splitter_sizes', None) and hasattr(self, 'splitter'):
                        self.splitter.setSizes(list(s.splitter_sizes))
                except Exception:
                    pass

        except Exception:
            pass

        if s.ui_theme in theme.PALETTES and s.ui_theme != theme.current_name():
            theme.apply(s.ui_theme)
            self.settings_panel.set_theme_name(s.ui_theme)

        # Update settings panel UI (zoom slider)
        try:
            self.settings_panel.zoom_sensitivity_slider.blockSignals(True)
            self.settings_panel.zoom_sensitivity_slider.setValue(int(s.zoom_sensitivity * 100))
            self.settings_panel.zoom_sensitivity_label.setText(f"{s.zoom_sensitivity:.1f}x")
            self.settings_panel.zoom_sensitivity_slider.blockSignals(False)
        except Exception:
            pass

        # Apply MAVLink global settings
        try:
            mav_settings = self._build_mavlink_settings(s)
            if hasattr(self, 'mavlink_service') and self.mavlink_service:
                self.mavlink_service.update_global_settings(mav_settings)
                # Also refresh the settings panel UI so the MAVLink controls reflect the new values
                try:
                    if hasattr(self, 'settings_panel') and getattr(self.settings_panel, '_refresh_mavlink_ui', None):
                        self.settings_panel._mavlink_settings = mav_settings
                        self.settings_panel._refresh_mavlink_ui()
                except Exception:
                    pass
        except Exception:
            pass

        # Load connections from storage into mavlink service
        try:
            if hasattr(self, 'mavlink_service') and self.mavlink_service:
                for entry in self.storage_service.list_connections():
                    try:
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
                            auto_connect=entry.auto_connect,
                        )
                        self.mavlink_service.save_connection_config(config)
                    except Exception:
                        continue
        except Exception:
            pass

        # Restore active panel and locked object
        if getattr(s, 'active_panel', None):
            self._show_panel(s.active_panel)
        try:
            if getattr(s, 'last_locked_object', None):
                for obj in self.object_service.get_objects():
                    if getattr(obj, 'name', None) == s.last_locked_object:
                        self.glWidget.set_locked_object(obj)
                        break
        except Exception:
            pass

        # Restore window maximized and font size
        try:
            if getattr(s, 'window_maximized', False):
                self.showMaximized()
        except Exception:
            pass

    def _on_export_settings_triggered(self):
        """Handle Export Settings menu action."""
        options = QFileDialog.Options()
        file_name, _ = QFileDialog.getSaveFileName(self, "Export Settings", "", "Settings Files (*.json);;All Files (*)", options=options)
        if not file_name:
            return  # User canceled

        # Confirm export action
        confirm = QMessageBox.question(self, "Confirm Export", f"Are you sure you want to export settings to:\n{file_name}?",
                                        QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if confirm != QMessageBox.Yes:
            return  # User canceled

        # Ensure current connections are synced into storage before exporting
        try:
            self._sync_connections_to_storage()
        except Exception:
            pass

        # Use StorageService.export_to_file to write a full settings+connections file
        try:
            ok = False
            if hasattr(self, 'storage_service') and self.storage_service:
                ok = self.storage_service.export_to_file(file_name)
            if ok:
                QMessageBox.information(self, "Export Settings", "Settings exported successfully.")
            else:
                QMessageBox.critical(self, "Export Settings", "Failed to export settings. See console for details.")
        except Exception as e:
            QMessageBox.critical(self, "Export Settings", f"Failed to export settings: {str(e)}")
