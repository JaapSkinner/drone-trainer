from PyQt5.QtWidgets import QDockWidget
from PyQt5.QtCore import Qt

from ui.dock.panels.object_panel import ObjectPanel
from ui.dock.panels.vicon_panel import ViconPanel
from ui.dock.panels.home_panel import HomePanel
from ui.dock.panels.trainer_panel import TrainerPanel
from ui.dock.panels.leaderboard_panel import LeaderboardPanel
from ui.dock.panels.config_panel import ConfigPanel
# Line 10 removed as it is redundant.
from ui.dock.panels.settings_panel import SettingsPanel

class DockManager(QDockWidget):
    def __init__(self, parent=None, gl_widget=None, control_callback=None, vicon=None):
        super().__init__(parent)
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.setFeatures(QDockWidget.NoDockWidgetFeatures)
        self.setMinimumWidth(300)
        self.setMinimumHeight(300)
        self.current_widget = None

        # Public references for external access
        self.panels = [
            HomePanel(self),
            TrainerPanel(self),
            LeaderboardPanel(self),
            ConfigPanel(self),
            ViconPanel(self, vicon),
            ObjectPanel(gl_widget,control_callback,self),
            SettingsPanel(self)
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
        for panel in self.panels:
            if getattr(panel, "NavTag", None) == tag:
                self.set_content(panel)
                return



