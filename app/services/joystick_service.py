import pygame
from PyQt5.QtCore import pyqtSignal, pyqtSlot
from services.service_base import ServiceBase,DebugLevel  # your base service
from models.structs import PositionData

class JoystickService(ServiceBase):
    joystick_updated = pyqtSignal(object)  # emits the updated object state or index

    def __init__(self, gl_widget, update_interval_ms=16, debug_level=None):
        super().__init__(debug_level=debug_level or DebugLevel.LOG)
        self.gl_widget = gl_widget
        self.update_interval = update_interval_ms
        self.controller = None
        self.controller_object = -1
        self.timer = None

    def on_start(self):
        pygame.init()
        pygame.joystick.init()
        if pygame.joystick.get_count() > 0:
            self.controller = pygame.joystick.Joystick(0)
            self.controller.init()
        else:
            self.controller = None
        from PyQt5.QtCore import QTimer
        self.timer = QTimer()
        self.timer.timeout.connect(self.safe(self.update))
        self.timer.start(self.update_interval)

    def on_stop(self):
        if self.timer:
            self.timer.stop()
            self.timer = None
        pygame.quit()

    def update(self):
        if not self.controller:
            return
        pygame.event.pump()

        def deadzone(val): return val if abs(val) > 0.1 else 0

        lx = deadzone(self.controller.get_axis(0))
        ly = deadzone(self.controller.get_axis(1))
        rx = deadzone(self.controller.get_axis(3))
        ry = deadzone(self.controller.get_axis(4))
        lb = self.controller.get_button(4)
        rb = self.controller.get_button(5)

        i = self.controller_object
        if i != -1:
            obj = self.gl_widget.objects[i]
            obj.x_vel = lx * 0.1
            obj.z_vel = ly * 0.1
            obj.y_vel = (rb - lb) * 0.1
            obj.x_pos += obj.x_vel
            obj.z_pos += obj.z_vel
            obj.y_pos += obj.y_vel
            obj.x_rot += ry * 2.0
            obj.z_rot -= rx * 2.0

            self.joystick_updated.emit(obj)  # notify main window or UI

    def set_controlled_object(self, index):
        self.controller_object = index
