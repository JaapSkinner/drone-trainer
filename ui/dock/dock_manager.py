from PyQt5.QtWidgets import QDockWidget
from PyQt5.QtCore import Qt

from ui.dock.panels.object_panel import ObjectPanel
from ui.dock.panels.vicon_panel import ViconPanel

class DockManager(QDockWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.setFeatures(QDockWidget.NoDockWidgetFeatures)
        self.setMinimumWidth(300)
        self.setMinimumHeight(300)
        self.current_widget = None

        # Public references for external access
        self.object_panel = None
        self.controller_panel = None
        self.vicon_panel = None

    def set_content(self, widget):
        if self.current_widget:
            self.current_widget.setParent(None)
        self.setWidget(widget)
        self.current_widget = widget

def create_dock(parent, gl_widget, control_callback, vicon):
    dock = DockManager(parent)

    dock.object_panel = ObjectPanel(gl_widget, control_callback)
    dock.vicon_panel = ViconPanel(vicon)

    dock.set_content(dock.object_panel)

    return dock
