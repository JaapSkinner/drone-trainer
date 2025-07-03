import pygame
from PyQt5.QtCore import QTimer, Qt, pyqtSlot
from PyQt5.QtWidgets import QMainWindow, QVBoxLayout, QPushButton, QWidget

from services.joystick_service import JoystickService
from ui.gl_widget.gl_widget import GLWidget
from ui.dock.dock_manager import create_dock
from models.structs import PositionData

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


    def initUI(self):
        self.setWindowTitle('Collaborative Control Interface')
        self.setGeometry(50, 50, 800, 600)

        central_widget = QWidget(self)
        layout = QVBoxLayout(central_widget)
        self.setCentralWidget(central_widget)

        self.glWidget = GLWidget(self)
        layout.addWidget(self.glWidget)

        layout.addWidget(QPushButton('Connect to Drone', self))

        self.dock = create_dock(self, self.glWidget, self.set_controlled_object, self.vicon)

        self.object_panel = self.dock.object_panel
        self.addDockWidget(Qt.LeftDockWidgetArea, self.dock)

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
        
        