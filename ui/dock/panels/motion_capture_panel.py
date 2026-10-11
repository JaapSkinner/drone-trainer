"""Motion capture panel: pick a source, connect, and map subjects to scene objects."""
from PyQt5.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout,
                             QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit,
                             QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
                             QVBoxLayout, QWidget)

from models.mocap_calibration import MocapCalibration
from models.sphere import Sphere
from models.structs import MotionCaptureConfig
from services.service_base import ServiceLevel
from ui.dock.panels.mocap_calibration_dialog import MocapCalibrationDialog

_STATUS_COLOURS = {
    ServiceLevel.RUNNING: "#1e7e34",
    ServiceLevel.WARNING: "#b36b00",
    ServiceLevel.ERROR: "#c82333",
    ServiceLevel.STOPPED: "#666666",
}


class MotionCapturePanel(QWidget):
    NavTag = "motion_capture"

    # Emitted with the MotionCaptureConfig to apply and persist.
    config_changed = pyqtSignal(object)

    COLUMNS = ("Subject", "Rate", "Position (m)", "Tracked by")

    def __init__(self, parent=None, motion_capture_service=None, object_service=None):
        super().__init__(parent)
        self.service = motion_capture_service
        self.object_service = object_service
        self._rows = {}  # subject name → table row
        self._connected = False

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignTop)
        title = QLabel("Motion Capture")
        title.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title)

        layout.addWidget(self._build_connection_group())
        layout.addWidget(self._build_subjects_group(), 1)

        config = self.service.get_config() if self.service else MotionCaptureConfig()
        self._load_config(config)

        if self.service is not None:
            self.service.subjects_updated.connect(self.on_subjects_updated)
            self.service.connection_changed.connect(self.on_connection_changed)
            self.service.status_changed.connect(self.on_status_changed)
            self.on_status_changed(self.service.status.value, self.service.status_text)
        if self.object_service is not None:
            self.object_service.objects_changed.connect(self._refresh_tracked_by)
            self.object_service.object_changed.connect(lambda _obj: self._refresh_tracked_by())

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_connection_group(self):
        group = QGroupBox("Connection")
        form = QFormLayout(group)

        self.source_combo = QComboBox()
        self.source_combo.addItem("Vicon (Tracker UDP stream)", "vicon")
        self.source_combo.addItem("OptiTrack (Motive NatNet)", "optitrack")
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)
        form.addRow("Source:", self.source_combo)

        # One settings page per source; only the selected one is shown.
        self.source_pages = [self._build_vicon_fields(), self._build_optitrack_fields()]
        for page in self.source_pages:
            form.addRow(page)

        filter_row = QHBoxLayout()
        self.filter_check = QCheckBox("Low-pass filter")
        self.filter_cutoff_spin = QDoubleSpinBox()
        self.filter_cutoff_spin.setRange(0.5, 100.0)
        self.filter_cutoff_spin.setSuffix(" Hz")
        self.filter_check.toggled.connect(self.filter_cutoff_spin.setEnabled)
        filter_row.addWidget(self.filter_check)
        filter_row.addWidget(self.filter_cutoff_spin)
        form.addRow("Smoothing:", filter_row)

        self.auto_connect_check = QCheckBox("Connect when the app starts")
        self.auto_connect_check.toggled.connect(lambda _checked: self._emit_config())
        form.addRow("", self.auto_connect_check)

        button_row = QHBoxLayout()
        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self._on_connect_clicked)
        button_row.addWidget(self.connect_button)
        self.calibrate_button = QPushButton("Calibrate…")
        self.calibrate_button.setToolTip("Align the motion capture axes and origin with the lab")
        self.calibrate_button.clicked.connect(self.open_calibration)
        button_row.addWidget(self.calibrate_button)
        form.addRow(button_row)

        self.calibration_label = QLabel()
        self.calibration_label.setWordWrap(True)
        self.calibration_label.setStyleSheet("color: #666; font-size: 11px;")
        form.addRow("Calibration:", self.calibration_label)

        self.status_label = QLabel("Not connected")
        self.status_label.setWordWrap(True)
        form.addRow("Status:", self.status_label)
        return group

    def _build_vicon_fields(self):
        widget = QWidget()
        form = QFormLayout(widget)
        form.setContentsMargins(0, 0, 0, 0)
        self.vicon_address_edit = QLineEdit()
        self.vicon_address_edit.setToolTip("Local address to listen on (0.0.0.0 = all interfaces)")
        form.addRow("Listen address:", self.vicon_address_edit)
        self.vicon_port_spin = QSpinBox()
        self.vicon_port_spin.setRange(1, 65535)
        form.addRow("UDP port:", self.vicon_port_spin)
        hint = QLabel("In Vicon Tracker enable the UDP Object Stream and send it to this PC's IP "
                      "and the port above.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666; font-size: 11px;")
        form.addRow(hint)
        return widget

    def _build_optitrack_fields(self):
        widget = QWidget()
        form = QFormLayout(widget)
        form.setContentsMargins(0, 0, 0, 0)
        self.optitrack_server_edit = QLineEdit()
        self.optitrack_server_edit.setToolTip("IP address of the PC running Motive")
        form.addRow("Motive PC IP:", self.optitrack_server_edit)
        self.optitrack_client_edit = QLineEdit()
        self.optitrack_client_edit.setToolTip("This PC's IP on the network Motive streams to")
        form.addRow("This PC's IP:", self.optitrack_client_edit)
        self.optitrack_multicast_check = QCheckBox("Multicast (Motive default)")
        form.addRow("Transport:", self.optitrack_multicast_check)
        self.optitrack_up_combo = QComboBox()
        self.optitrack_up_combo.addItem("Y up (Motive default)", "y")
        self.optitrack_up_combo.addItem("Z up", "z")
        form.addRow("Up axis:", self.optitrack_up_combo)
        hint = QLabel("In Motive enable NatNet streaming. Rigid body names are matched to "
                      "objects' tracking IDs.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666; font-size: 11px;")
        form.addRow(hint)
        return widget

    def _build_subjects_group(self):
        group = QGroupBox("Subjects")
        layout = QVBoxLayout(group)

        self.subjects_table = QTableWidget(0, len(self.COLUMNS))
        self.subjects_table.setHorizontalHeaderLabels(self.COLUMNS)
        self.subjects_table.verticalHeader().setVisible(False)
        self.subjects_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.subjects_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.subjects_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        header = self.subjects_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        self.subjects_table.itemSelectionChanged.connect(self._update_action_buttons)
        layout.addWidget(self.subjects_table)

        self.empty_label = QLabel("Connect to see tracked subjects.")
        self.empty_label.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(self.empty_label)

        buttons = QHBoxLayout()
        self.assign_button = QPushButton("Assign to object…")
        self.assign_button.clicked.connect(self._on_assign_clicked)
        self.create_button = QPushButton("Create object")
        self.create_button.setToolTip("Add a marker that follows this subject")
        self.create_button.clicked.connect(self._on_create_clicked)
        self.unassign_button = QPushButton("Unassign")
        self.unassign_button.clicked.connect(self._on_unassign_clicked)
        for b in (self.assign_button, self.create_button, self.unassign_button):
            buttons.addWidget(b)
        layout.addLayout(buttons)
        self._update_action_buttons()
        return group

    # ------------------------------------------------------------------
    # Config <-> widgets
    # ------------------------------------------------------------------

    def _load_config(self, config: MotionCaptureConfig):
        index = self.source_combo.findData(config.source)
        self.source_combo.setCurrentIndex(max(0, index))
        self.vicon_address_edit.setText(config.vicon_address)
        self.vicon_port_spin.setValue(int(config.vicon_port))
        self.optitrack_server_edit.setText(config.optitrack_server_ip)
        self.optitrack_client_edit.setText(config.optitrack_client_ip)
        self.optitrack_multicast_check.setChecked(config.optitrack_multicast)
        self.optitrack_up_combo.setCurrentIndex(max(0, self.optitrack_up_combo.findData(config.optitrack_up_axis)))
        self.filter_check.setChecked(config.filter_enabled)
        self.filter_cutoff_spin.setValue(config.filter_cutoff_hz)
        self.filter_cutoff_spin.setEnabled(config.filter_enabled)
        self.auto_connect_check.blockSignals(True)
        self.auto_connect_check.setChecked(config.auto_connect)
        self.auto_connect_check.blockSignals(False)
        self._poll_rate_hz = config.poll_rate_hz
        self._calibration_dict = dict(config.calibration)
        self._show_calibration(MocapCalibration.from_dict(config.calibration))
        self._on_source_changed(self.source_combo.currentIndex())

    def current_config(self) -> MotionCaptureConfig:
        return MotionCaptureConfig(
            source=self.source_combo.currentData(),
            vicon_address=self.vicon_address_edit.text().strip() or "0.0.0.0",
            vicon_port=self.vicon_port_spin.value(),
            optitrack_server_ip=self.optitrack_server_edit.text().strip() or "127.0.0.1",
            optitrack_client_ip=self.optitrack_client_edit.text().strip() or "127.0.0.1",
            optitrack_multicast=self.optitrack_multicast_check.isChecked(),
            optitrack_up_axis=self.optitrack_up_combo.currentData(),
            filter_enabled=self.filter_check.isChecked(),
            filter_cutoff_hz=self.filter_cutoff_spin.value(),
            poll_rate_hz=self._poll_rate_hz,
            auto_connect=self.auto_connect_check.isChecked(),
            calibration=(self.service.get_config().calibration if self.service
                         else dict(self._calibration_dict)),
        )

    def _emit_config(self):
        self.config_changed.emit(self.current_config())

    # ------------------------------------------------------------------
    # Calibration
    # ------------------------------------------------------------------

    def _show_calibration(self, calibration):
        text = calibration.describe()
        self.calibration_label.setText("None" if calibration.is_identity else text)

    def open_calibration(self):
        """Open (or raise) the calibration dialog."""
        if self.service is None:
            return None
        dialog = getattr(self, "_calibration_dialog", None)
        if dialog is None or not dialog.isVisible():
            dialog = MocapCalibrationDialog(self.service, self)
            dialog.calibration_applied.connect(self._on_calibration_applied)
            dialog.finished.connect(lambda _r: self._show_calibration(self.service.get_calibration()))
            self._calibration_dialog = dialog
        dialog.show()
        dialog.raise_()
        return dialog

    def _on_calibration_applied(self, calibration):
        self._calibration_dict = calibration.to_dict()
        self._show_calibration(calibration)
        self._emit_config()  # MainWindow applies and saves it

    def _on_source_changed(self, index):
        for i, page in enumerate(self.source_pages):
            page.setVisible(i == index)

    def _set_settings_enabled(self, enabled: bool):
        for w in (self.source_combo, *self.source_pages, self.filter_check):
            w.setEnabled(enabled)
        self.filter_cutoff_spin.setEnabled(enabled and self.filter_check.isChecked())

    # ------------------------------------------------------------------
    # Service events
    # ------------------------------------------------------------------

    def _on_connect_clicked(self):
        if self.service is None:
            return
        if self._connected:
            self.service.disconnect_source()
        else:
            self._emit_config()  # MainWindow applies and saves it
            self.service.connect_source()

    @pyqtSlot(bool)
    def on_connection_changed(self, connected: bool):
        self._connected = connected
        self.connect_button.setText("Disconnect" if connected else "Connect")
        self._set_settings_enabled(not connected)
        if not connected:
            self.on_subjects_updated([])

    @pyqtSlot(int, str)
    def on_status_changed(self, level: int, label: str):
        level_enum = ServiceLevel(level)
        self.status_label.setText(label or level_enum.name.capitalize())
        self.status_label.setStyleSheet(f"color: {_STATUS_COLOURS.get(level_enum, '#666')};")

    @pyqtSlot(object)
    def on_subjects_updated(self, subjects):
        table = self.subjects_table
        names = [s.name for s in subjects]
        if names != list(self._rows):
            selected = self.selected_subject()
            table.setRowCount(len(subjects))
            self._rows = {name: row for row, name in enumerate(names)}
            for row, name in enumerate(names):
                table.setItem(row, 0, QTableWidgetItem(name))
                for col in range(1, len(self.COLUMNS)):
                    table.setItem(row, col, QTableWidgetItem(""))
            if selected in self._rows:
                table.selectRow(self._rows[selected])
        for info in subjects:
            row = self._rows[info.name]
            stale = info.age_s > 1.0
            table.item(row, 1).setText("lost" if stale else f"{info.rate_hz:.0f} Hz")
            x, y, z = info.pose[:3]
            table.item(row, 2).setText(f"{x:+.2f}, {y:+.2f}, {z:+.2f}")
        self.empty_label.setVisible(not subjects)
        self.empty_label.setText("Connect to see tracked subjects." if not self._connected
                                 else "Connected — no subjects received yet.")
        self._refresh_tracked_by()

    def _refresh_tracked_by(self):
        for name, row in self._rows.items():
            objects = self._objects_tracking(name)
            item = self.subjects_table.item(row, 3)
            if item is not None:
                item.setText(", ".join(o.name for o in objects) or "—")
        self._update_action_buttons()

    # ------------------------------------------------------------------
    # Subject → object mapping
    # ------------------------------------------------------------------

    def selected_subject(self):
        rows = self.subjects_table.selectionModel().selectedRows() if self.subjects_table.selectionModel() else []
        if not rows:
            return None
        item = self.subjects_table.item(rows[0].row(), 0)
        return item.text() if item else None

    def _objects_tracking(self, subject):
        if self.object_service is None:
            return []
        return [o for o in self.object_service.get_objects() if o.tracked and o.tracking_id == subject]

    def _update_action_buttons(self):
        subject = self.selected_subject()
        has_objects = self.object_service is not None
        self.assign_button.setEnabled(bool(subject) and has_objects)
        self.create_button.setEnabled(bool(subject) and has_objects)
        self.unassign_button.setEnabled(bool(subject) and bool(self._objects_tracking(subject)))

    def assign_subject(self, subject: str, obj):
        """Make ``obj`` follow ``subject`` (one object per subject)."""
        for other in self._objects_tracking(subject):
            if other is not obj:
                other.tracked = False
                self.object_service.notify_object_changed(other)
        obj.set_tracked(True, subject)
        self.object_service.notify_object_changed(obj)
        self._refresh_tracked_by()

    def create_object_for_subject(self, subject: str):
        marker = Sphere(name=subject, radius=0.08, colour=(1.0, 0.55, 0.0, 1.0), controllable=True)
        info = next((s for s in (self.service.subjects_snapshot() if self.service else []) if s.name == subject), None)
        if info is not None:
            marker.set_pose(info.pose)
        self.object_service.add_object(marker)
        self.assign_subject(subject, marker)
        return marker

    def _on_assign_clicked(self):
        subject = self.selected_subject()
        if not subject:
            return
        candidates = [o for o in self.object_service.get_objects() if not o.helper]
        if not candidates:
            return
        names = [o.name for o in candidates]
        current = next((i for i, o in enumerate(candidates) if o.tracking_id == subject), 0)
        name, ok = QInputDialog.getItem(self, "Assign subject", f"Object to follow '{subject}':",
                                        names, current, False)
        if ok:
            self.assign_subject(subject, candidates[names.index(name)])

    def _on_create_clicked(self):
        subject = self.selected_subject()
        if subject:
            self.create_object_for_subject(subject)

    def _on_unassign_clicked(self):
        subject = self.selected_subject()
        for obj in self._objects_tracking(subject):
            obj.tracked = False
            self.object_service.notify_object_changed(obj)
        self._refresh_tracked_by()
