from PyQt5.QtCore import QTimer, Qt, pyqtSlot
from PyQt5.QtWidgets import QMainWindow, QSplitter,QHBoxLayout, QWidget

from services.joystick_service import JoystickService
from ui.gl_widget.gl_widget import GLWidget
from ui.dock.dock_manager import DockManager
from models.structs import PositionData
from ui.navbar.navbar import SideNavbar
from ui.style import load_stylesheet

class MainWindow(QMainWindow):
    def __init__(self, vicon, parent=None):
        
        super().__init__(parent)
        self.vicon = vicon
        self.initUI()

        # Setup JoystickService
        self.joystick_service = JoystickService(self.glWidget)
        self.joystick_service.joystick_updated.connect(self.on_joystick_update)
        self.joystick_service.start()
        
        self.vicon.position_updated.connect(self.update_vicon_position)
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

        # Dockand GLWidget on the right
        self.glWidget = GLWidget(self)
        self.dock = DockManager(self, self.glWidget, self.set_controlled_object, self.vicon)
        self.object_panel = self.dock.panels[5]
        
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.dock)
        splitter.addWidget(self.glWidget)
        splitter.setStretchFactor(1, 1)  # let GLWidget expand
        main_layout.addWidget(splitter)
        splitter.setCollapsible(0, False)  # Prevent dock collapsing
        splitter.setCollapsible(1, False)  # Prevent GL collapsing
        self.glWidget.setMinimumWidth(200)
        self.dock.setMinimumWidth(250)
        

        # Optional: connect nav signal
        self.navbar.panel_selected.connect(self.dock.set_active_panel)
        



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
    def on_joystick_update(self, obj):
        self.object_panel.refresh()
        self.glWidget.update()

    def set_controlled_object(self, index):
        if hasattr(self, 'joystick_service'):
            self.joystick_service.set_controlled_object_slot(index)
        
        