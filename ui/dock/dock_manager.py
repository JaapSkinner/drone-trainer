import logging

from PyQt5.QtWidgets import QDockWidget
from PyQt5.QtCore import Qt

from ui.dock.panels.objects_panel import ObjectsPanel
from ui.dock.panels.home_panel import HomePanel
from ui.dock.panels.trainer_panel import TrainerPanel
from ui.dock.panels.leaderboard_panel import LeaderboardPanel
from ui.dock.panels.command_panel import CommandPanel
from ui.dock.panels.settings_panel import SettingsPanel
from ui.dock.panels.mavlink_panel import MavlinkPanel
from ui.dock.panels.motion_capture_panel import MotionCapturePanel

logger = logging.getLogger(__name__)

# Panel tags that were renamed; persisted settings may still contain the old ones.
_TAG_ALIASES = {
    "config": "settings",
    "live_data": "objects",
    "vicon": "motion_capture",
}


class DockManager(QDockWidget):
    """Manager for dock panel widgets.

    Handles switching between different panels in the dock area,
    including home, trainer, mavlink, object, settings, and command panels.
    """

    def __init__(self, gl_widget=None, parent=None, object_service=None, mavlink_service=None,
                 motion_capture_service=None, control_service=None, trainer_service=None):
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
        self.mavlink_panel = MavlinkPanel(self, mavlink_service=mavlink_service,
                                          object_service=object_service)

        self.objects_panel = ObjectsPanel(
            self, object_service=object_service, mavlink_service=mavlink_service,
            motion_capture_service=motion_capture_service)

        self.home_panel = HomePanel(self)
        self.command_panel = CommandPanel(self, object_service=object_service, control_service=control_service,
                                          motion_capture_service=motion_capture_service)
        self.trainer_panel = TrainerPanel(self, trainer_service=trainer_service, object_service=object_service)
        self.leaderboard_panel = LeaderboardPanel(self, trainer_service=trainer_service)

        self.motion_capture_panel = MotionCapturePanel(
            self, motion_capture_service=motion_capture_service, object_service=object_service)

        # Create settings panel with mavlink service reference
        self.settings_panel = SettingsPanel(
            self,
            object_service=object_service,
            mavlink_service=mavlink_service
        )

        # Public references for external access
        self.panels = [
            self.home_panel,
            self.trainer_panel,
            self.leaderboard_panel,
            self.motion_capture_panel,
            self.mavlink_panel,
            self.objects_panel,
            self.settings_panel,
            self.command_panel
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
        
    @staticmethod
    def resolve_tag(tag):
        """Map legacy panel tags to their current name."""
        return _TAG_ALIASES.get(tag, tag)

    def get_panel(self, tag):
        tag = self.resolve_tag(tag)
        for panel in self.panels:
            if getattr(panel, "NavTag", None) == tag:
                return panel
        return None

    def set_active_panel(self, tag) -> bool:
        """Show the panel with this NavTag. Returns False if there is none."""
        panel = self.get_panel(tag)
        if panel is None:
            logger.warning("No dock panel for navigation tag %r", tag)
            return False
        self.set_content(panel)
        return True

    def set_mavlink_service(self, mavlink_service):
        """Set the mavlink service for all relevant panels.

        Args:
            mavlink_service: MAVLink service instance
        """
        self._mavlink_service = mavlink_service
        self.mavlink_panel.set_mavlink_service(mavlink_service)
        self.settings_panel.set_mavlink_service(mavlink_service)
        self.objects_panel.ctx.mavlink_service = mavlink_service
        self.command_panel.mavlink_service = mavlink_service
        self.command_panel.drone_status.mavlink_service = mavlink_service
