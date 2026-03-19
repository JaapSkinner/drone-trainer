from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QPushButton,
    QComboBox,
    QLineEdit,
    QDoubleSpinBox,
    QSpinBox,
    QFormLayout,
    QGroupBox,
)
from PyQt5.QtCore import pyqtSlot

from services.motion_capture_service import MotionCaptureSource


class MotionCapturePanel(QWidget):
    NavTag = "motion_capture"

    def __init__(self, motion_capture_service, on_connected_callback=None, parent=None):
        super().__init__(parent)
        self.motion_capture_service = motion_capture_service
        self.on_connected_callback = on_connected_callback

        self.connect_button = QPushButton("Connect")
        self.tracking_button = QPushButton("Start Tracking")
        self.disconnect_button = QPushButton("Disconnect")

        self.source_combo = QComboBox()
        self.source_combo.addItem("Vicon (UDP)", MotionCaptureSource.VICON.value)
        self.source_combo.addItem("OptiTrack (NatNet)", MotionCaptureSource.OPTITRACK.value)
        self.address_edit = QLineEdit()
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.frequency_spin = QDoubleSpinBox()
        self.frequency_spin.setRange(1.0, 500.0)
        self.frequency_spin.setSuffix(" Hz")
        self.object_name_edit = QLineEdit()

        self.connect_button.clicked.connect(self.connect_to_source)
        self.tracking_button.clicked.connect(self.start_stop_tracking)
        self.disconnect_button.clicked.connect(self.disconnect_source)

        layout = QVBoxLayout(self)
        settings_group = QGroupBox("Motion Capture Settings")
        form = QFormLayout(settings_group)
        form.addRow("Source:", self.source_combo)
        form.addRow("Address:", self.address_edit)
        form.addRow("Port:", self.port_spin)
        form.addRow("Frequency:", self.frequency_spin)
        form.addRow("Object Name:", self.object_name_edit)
        layout.addWidget(settings_group)

        layout.addWidget(self.connect_button)
        layout.addWidget(self.disconnect_button)
        layout.addWidget(self.tracking_button)
        layout.addStretch()

        self._load_from_service()

    def _load_from_service(self):
        config = self.motion_capture_service.get_config()
        source_idx = self.source_combo.findData(config.get("source", MotionCaptureSource.VICON.value))
        if source_idx >= 0:
            self.source_combo.setCurrentIndex(source_idx)
        self.address_edit.setText(config.get("address", "0.0.0.0"))
        self.port_spin.setValue(int(config.get("port", 51001)))
        self.frequency_spin.setValue(float(config.get("frequency_hz", 100.0)))
        self.object_name_edit.setText(config.get("tracked_object_name", "tracked_object"))

    def _apply_config(self):
        self.motion_capture_service.configure(
            source=self.source_combo.currentData(),
            address=self.address_edit.text().strip(),
            port=self.port_spin.value(),
            frequency_hz=self.frequency_spin.value(),
            tracked_object_name=self.object_name_edit.text().strip(),
        )

    @pyqtSlot()
    def connect_to_source(self):
        self._apply_config()
        if self.motion_capture_service.connect():
            self.connect_button.setEnabled(False)
            self.connect_button.setText("Connected")
            self.connect_button.setStyleSheet("background-color : green")
            if self.on_connected_callback:
                self.on_connected_callback()
        else:
            self.connect_button.setEnabled(True)
            self.connect_button.setText("Connect")
            self.connect_button.setStyleSheet("")

    @pyqtSlot()
    def disconnect_source(self):
        self.motion_capture_service.disconnect()
        self.connect_button.setEnabled(True)
        self.connect_button.setText("Connect")
        self.connect_button.setStyleSheet("")
        self.tracking_button.setText("Start Tracking")
        self.tracking_button.setStyleSheet("")

    @pyqtSlot()
    def start_stop_tracking(self):
        if self.motion_capture_service.tracking:
            self.motion_capture_service.stop_tracking()
            self.tracking_button.setText("Start Tracking")
            self.tracking_button.setStyleSheet("")
        else:
            if self.motion_capture_service.start_tracking():
                self.tracking_button.setText("Stop Tracking")
                self.tracking_button.setStyleSheet("background-color : red")


# Backward compatibility for existing imports.
ViconPanel = MotionCapturePanel
