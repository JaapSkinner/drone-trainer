import pygame
from PyQt5.QtCore import QTimer, Qt, pyqtSlot
from PyQt5.QtWidgets import QMainWindow, QVBoxLayout, QPushButton, QWidget

from ui.gl_widget.gl_widget import GLWidget
from ui.dock.dock_manager import create_dock
from models.structs import PositionData

class MainWindow(QMainWindow):
    def __init__(self, vicon, parent=None):
        
        super().__init__(parent)
        self.vicon = vicon
        self.initUI()

        pygame.init()
        pygame.joystick.init()
        self.controller = pygame.joystick.Joystick(0)
        self.controller.init()
        self.controller_object = 0
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_controller)
        self.timer.start(16)

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

    def set_controlled_object(self, index):
        self.controller_object = index

    def update_controller(self):
        def deadzone(val): return val if abs(val) > 0.1 else 0
        pygame.event.pump()

        lx = deadzone(self.controller.get_axis(0))
        ly = deadzone(self.controller.get_axis(1))
        rx = deadzone(self.controller.get_axis(3))
        ry = deadzone(self.controller.get_axis(4))
        lb = self.controller.get_button(4)
        rb = self.controller.get_button(5)

        i = self.controller_object
        if i != -1:
            obj = self.glWidget.objects[i]
            obj.x_vel = lx * 0.1
            obj.z_vel = ly * 0.1
            obj.y_vel = (rb - lb) * 0.1
            obj.x_pos += obj.x_vel
            obj.z_pos += obj.z_vel
            obj.y_pos += obj.y_vel
            obj.x_rot += ry * 2.0
            obj.z_rot -= rx * 2.0

        self.object_panel.refresh()
        self.glWidget.update() 

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
