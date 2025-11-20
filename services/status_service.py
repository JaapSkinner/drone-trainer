from PyQt5.QtCore import pyqtSignal, QTimer
from services.service_base import ServiceBase, DebugLevel, ServiceLevel
from time import time

class StatusService(ServiceBase):
    def __init__(self, status_panel, joystick_service, mavlink_service, debug_level=DebugLevel.LOG):
        super().__init__(debug_level)
        self.status_panel = status_panel
        self.joystick_service = joystick_service
        self.timer = None

    def on_start(self):
        self.timer = QTimer()
        self.timer.setInterval(1000)  # 1 Hz
        self.timer.timeout.connect(self.safe(self.update))
        self.timer.start()

    def on_stop(self):
        if self.timer:
            self.timer.stop()
            self.timer.deleteLater()
            self.timer = None

    def update(self):
        # Joystick
        js = self.joystick_service
        self.status_panel.handle_status_change(js.status.value, getattr(js, "status_label", ""), "joystick")
