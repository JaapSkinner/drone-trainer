from PyQt5.QtWidgets import QWidget, QVBoxLayout, QPushButton
from PyQt5.QtCore import pyqtSlot

class MotionCapturePanel(QWidget):
    NavTag = "vicon"
    def __init__(self, motion_capture_service, on_connected_callback=None, parent=None):
        super().__init__(parent)
        self.vicon = motion_capture_service
        self.on_connected_callback = on_connected_callback

        self.vicon_button = QPushButton("Connect to Vicon")
        self.tracking_button = QPushButton("Start Tracking")

        self.vicon_button.clicked.connect(self.connect_to_motion_capture)
        self.tracking_button.clicked.connect(self.start_stop_tracking)

        layout = QVBoxLayout(self)
        layout.addWidget(self.vicon_button)
        layout.addWidget(self.tracking_button)
        layout.addStretch()

    @pyqtSlot()
    def connect_to_motion_capture(self):
        if self.vicon.connect():
            self.vicon_button.setEnabled(False)
            self.vicon_button.setText("Connected to Vicon")
            self.vicon_button.setStyleSheet("background-color : green")
            if self.on_connected_callback:
                self.on_connected_callback()
        else:
            self.vicon_button.setEnabled(True)
            self.vicon_button.setText("Connect to Vicon")
            self.vicon_button.setStyleSheet("")

    @pyqtSlot()
    def start_stop_tracking(self):
        if self.vicon.tracking:
            self.vicon.stop_tracking()
            self.tracking_button.setText("Start Tracking")
            self.tracking_button.setStyleSheet("")
        else:
            if self.vicon.start_tracking():
                self.tracking_button.setText("Stop Tracking")
                self.tracking_button.setStyleSheet("background-color : red")
