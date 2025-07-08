import numpy as np
import pygame
from PyQt5.QtCore import pyqtSignal, pyqtSlot
from services.service_base import ServiceBase,DebugLevel,ServiceLevel  # your base service
from models.structs import PositionData
from PyQt5.QtCore import QTimer

class JoystickService(ServiceBase):
    joystick_updated = pyqtSignal(object)  # emits the updated object state or index

    def __init__(self, gl_widget, update_interval_ms=16, debug_level=None):
        super().__init__(debug_level=debug_level or DebugLevel.LOG)
        self.gl_widget = gl_widget
        self.update_interval = update_interval_ms
        self.joystick = None
        self.joystick_object = 0
        self.timer = None

    def on_start(self):
        pygame.init()
        pygame.joystick.init()
        if pygame.joystick.get_count() > 0:
            self.joystick = pygame.joystick.Joystick(0)
            self.joystick.init()
            self.status_label = f"Joystick: {self.joystick.get_name()}"
            self.status = ServiceLevel.RUNNING
        else:
            self.joystick = None
            self.status_label = "Joystick: Not Found"
            self.status = ServiceLevel.STOPPED

        self.timer = QTimer()
        self.timer.timeout.connect(self.safe(self.update))
        self.timer.start(self.update_interval)

    def on_stop(self):
        if self.timer:
            self.timer.stop()
            self.timer = None
        pygame.quit()

    def update(self):
        if not self.joystick or not self.joystick.get_init():
            # No joystick connected or joystick was disconnected, check for new connection
            pygame.joystick.quit()
            pygame.joystick.init()
            if pygame.joystick.get_count() > 0:
                self.joystick = pygame.joystick.Joystick(0)
                self.joystick.init()
                self.status_label = f"{self.joystick.get_name()}"
                self.status = ServiceLevel.RUNNING
            else:
                self.joystick = None
                self.status_label = "Not Found"
                self.status = ServiceLevel.STOPPED
            return
        elif self.joystick.get_id() >= pygame.joystick.get_count():
            # Joystick was disconnected
            self.joystick = None
            self.status_label = "Disconnected"
            self.status = ServiceLevel.STOPPED
            return
        
        pygame.event.pump()

        def deadzone(val): return val if abs(val) > 0.1 else 0

        # read camera angles from gl_widget and rotate joystick axes accordingly
        cam_angle_x = self.gl_widget.camera_angle_x
        cam_angle_y = self.gl_widget.camera_angle_y
        
        # Adjust joystick axes based on camera angles
        lx = deadzone(self.joystick.get_axis(0)) * np.cos(np.radians(cam_angle_y)) + deadzone(self.joystick.get_axis(1)) * np.sin(np.radians(cam_angle_y))
        ly = - deadzone(self.joystick.get_axis(0)) * np.sin(np.radians(cam_angle_y)) + deadzone(self.joystick.get_axis(1)) * np.cos(np.radians(cam_angle_y))
        rx = deadzone(self.joystick.get_axis(3))
        # rx = np.sin(np.radians(cam_angle_y)) * deadzone(self.joystick.get_axis(4)) + np.cos(np.radians(cam_angle_y)) * deadzone(self.joystick.get_axis(3))
        ry = deadzone(self.joystick.get_axis(4)) 
        # ry = - np.sin(np.radians(cam_angle_y)) * deadzone(self.joystick.get_axis(3)) + np.cos(np.radians(cam_angle_y)) * deadzone(self.joystick.get_axis(4))
        rz = deadzone(((self.joystick.get_axis(5) + 1) / 2) - ((self.joystick.get_axis(2) + 1) / 2))  # RT - LT, normalized to [-1, 1]
        lb = self.joystick.get_button(4)
        rb = self.joystick.get_button(5)


        i = self.joystick_object
        if i != -1:
            obj = self.gl_widget.objects[i]
            obj.set_velocity(lx * 0.1,
                            (rb - lb) * 0.1, 
                            ly * 0.1)
            obj.set_position(obj.x_pos + obj.x_vel, 
                             obj.y_pos + obj.y_vel, 
                             obj.z_pos + obj.z_vel)
            obj.set_rotation(ry * 0.03, 
                             -rz * 0.03, 
                             -rx * 0.03)
            

            self.joystick_updated.emit(obj)  # notify main window or UI

    @pyqtSlot(int)
    def set_controlled_object_slot(self, index):
        self.joystick_object = index
