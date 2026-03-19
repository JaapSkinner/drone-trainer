from PyQt5.QtWidgets import QDockWidget
from PyQt5.QtCore import Qt

from ui.dock.panels.object_panel import ObjectPanel
from ui.dock.panels.vicon_panel import ViconPanel
from ui.dock.panels.home_panel import HomePanel
from ui.dock.panels.trainer_panel import TrainerPanel
from ui.dock.panels.leaderboard_panel import LeaderboardPanel
from ui.dock.panels.command_panel import CommandPanel
from ui.dock.panels.settings_panel import SettingsPanel
from ui.dock.panels.mavlink_panel import MavlinkPanel

class DockManager(QDockWidget):
    """Manager for dock panel widgets.

    Handles switching between different panels in the dock area,
    including home, trainer, mavlink, object, settings, and command panels.
    """

    def __init__(self, gl_widget=None, parent=None, object_service=None, mavlink_service=None):
        """Initialize the dock manager.

        Args:
            gl_widget: GL widget reference
            parent: Parent widget
            object_service: Object service instance
            mavlink_service: MAVLink service instance (optional, can be set later)
        """
        super().__init__(parent)
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.setFeatures(QDockWidget.NoDockWidgetFeatures)
        self.setMinimumWidth(380)  # Increased to prevent horizontal scroll and button clipping
        self.setMinimumHeight(300)
        self.current_widget = None

        # Store service references
        self._mavlink_service = mavlink_service
        self._object_service = object_service

        # Create mavlink panel (can connect service later)
        self.mavlink_panel = MavlinkPanel(self, mavlink_service=mavlink_service)

        # Create object panel with mavlink service reference
        self.object_panel = ObjectPanel(
            gl_widget, self,
            object_service=object_service,
            mavlink_service=mavlink_service
        )

        # Create settings panel with mavlink service reference
        self.settings_panel = SettingsPanel(
            self,
            object_service=object_service,
            mavlink_service=mavlink_service
        )

        # Public references for external access
        self.panels = [
            HomePanel(self),
            TrainerPanel(self),
            LeaderboardPanel(self),
            # ViconPanel(self, vicon),
            self.mavlink_panel,
            self.object_panel,
            self.settings_panel,
            CommandPanel(self, object_service=object_service)
        ]
        for panel in self.panels:
            if hasattr(panel, "NavTag"):
                panel.setParent(None)
       
        self.set_active_panel("home")

    def set_content(self, widget):
        if self.current_widget:
            self.current_widget.setParent(None)
        self.setWidget(widget)
        self.current_widget = widget
        
    def set_active_panel(self, tag):
        if tag == "config":
            tag = "settings"
        for panel in self.panels:
            if getattr(panel, "NavTag", None) == tag:
                self.set_content(panel)
                return

    def set_mavlink_service(self, mavlink_service):
        """Set the mavlink service for all relevant panels.

        Args:
            mavlink_service: MAVLink service instance
        """
        self._mavlink_service = mavlink_service
        self.mavlink_panel.set_mavlink_service(mavlink_service)
        self.settings_panel.set_mavlink_service(mavlink_service)

        # Connect object panel's config change signal to mavlink service
        if mavlink_service is not None:
            self.object_panel.mavlink_config_changed.connect(
                lambda obj, config: mavlink_service.update_object_config(obj, config)
            )
