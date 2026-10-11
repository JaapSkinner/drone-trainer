"""Add a drone — a step-by-step setup that ties tracking, the flight controller
and control together for one object.

Steps: 1 Drone (name, model) → 2 Tracking (mocap subject or simulated) →
3 Vehicle (MAVLink connection or none) → 4 Review (live readiness).

Opened with ``edit_object`` it re-runs the same steps for an existing drone.
Everything it sets can still be changed afterwards on the object's card in the
Objects panel, the Motion Capture panel and the MAVLink panel.
"""
import os
import re

from PyQt5.QtCore import QTimer, Qt, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (QButtonGroup, QCheckBox, QColorDialog, QComboBox, QDialog, QDoubleSpinBox,
                             QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                             QListWidgetItem, QPushButton, QRadioButton, QStackedWidget, QVBoxLayout,
                             QWidget)

from models.cad_mesh import CadMesh
from models.sphere import Sphere
from models.structs import MavlinkConnectionConfig
from ui.widgets.drone_status import COLOURS, OK, OFF, SYMBOLS, WARN, BAD

QUAD_MESH = "cad_files/basic_quadcopter.stl"
QUAD_SCALE = 0.004          # the STL is in mm and 84 mm across → ~0.34 m
NEW_CONNECTION = "__new__"
DEFAULT_PORT = 14550

STEPS = ("Drone", "Tracking", "Vehicle", "Review")


def _hint(text):
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet("color: #666;")
    return label


def _heading(text):
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet("font-size: 15px; font-weight: 600; margin-bottom: 4px;")
    return label


def _status(label, state, text):
    label.setText(f"{SYMBOLS[state]} {text}")
    label.setStyleSheet(f"color: {COLOURS[state]};")


def _swatch_style(colour):
    r, g, b = (int(round(c * 255)) for c in colour[:3])
    return (f"QPushButton {{ background: rgb({r},{g},{b}); border: 1px solid #888; border-radius: 4px;"
            " min-width: 28px; max-width: 28px; min-height: 20px; }")


class AddDroneWizard(QDialog):
    # (object, {"control": bool, "follow": bool}) after Finish
    drone_ready = pyqtSignal(object, object)

    def __init__(self, object_service, motion_capture_service=None, mavlink_service=None,
                 edit_object=None, parent=None):
        super().__init__(parent)
        self.objects = object_service
        self.mocap = motion_capture_service
        self.mavlink = mavlink_service
        self.edit_object = edit_object
        self._colour = tuple(edit_object.colour) if edit_object is not None else (0.2, 0.6, 1.0, 1.0)
        self._mesh_path = ""
        self._pending_connection = None   # name of a connection this wizard started
        self.setWindowTitle(f"Drone setup — {edit_object.name}" if edit_object else "Add a drone")
        self.resize(560, 600)

        layout = QVBoxLayout(self)
        self.steps_label = QLabel()
        self.steps_label.setStyleSheet("color: #555; padding-bottom: 6px;")
        layout.addWidget(self.steps_label)

        self.pages = QStackedWidget()
        for build in (self._build_drone_page, self._build_tracking_page,
                      self._build_vehicle_page, self._build_review_page):
            self.pages.addWidget(build())
        layout.addWidget(self.pages, 1)

        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet(f"color: {COLOURS[BAD]};")
        layout.addWidget(self.error_label)

        buttons = QHBoxLayout()
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        buttons.addWidget(self.cancel_button)
        buttons.addStretch()
        self.back_button = QPushButton("< Back")
        self.back_button.clicked.connect(self.back)
        buttons.addWidget(self.back_button)
        self.next_button = QPushButton("Next >")
        self.next_button.setDefault(True)
        self.next_button.clicked.connect(self.next)
        buttons.addWidget(self.next_button)
        layout.addLayout(buttons)

        self._prefill()
        if self.mocap is not None:
            self.mocap.subjects_updated.connect(self._on_subjects_updated)
            self.mocap.connection_changed.connect(self._on_mocap_connection_changed)
        if self.mavlink is not None:
            self.mavlink.connection_attempt_finished.connect(self._on_connection_attempt_finished)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_live)
        self._timer.start(500)
        self.go_to(0)

    # ------------------------------------------------------------------
    # Pages
    # ------------------------------------------------------------------

    def _build_drone_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(_heading("Name your drone and pick how it looks"))
        form = QFormLayout()
        self.drone_form = form
        self.name_edit = QLineEdit()
        form.addRow("Name:", self.name_edit)

        self.model_combo = QComboBox()
        self.model_combo.addItem("Quadcopter (built-in model)", "quad")
        self.model_combo.addItem("Marker ball", "ball")
        self.model_combo.addItem("Custom mesh (STL / OBJ)…", "mesh")
        self.model_combo.currentIndexChanged.connect(self._update_model_fields)
        form.addRow("Model:", self.model_combo)

        mesh_row = QHBoxLayout()
        self.mesh_label = QLabel("No file chosen")
        self.mesh_label.setStyleSheet("color: #666;")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._choose_mesh)
        mesh_row.addWidget(self.mesh_label, 1)
        mesh_row.addWidget(browse)
        self.mesh_row_widget = QWidget()
        self.mesh_row_widget.setLayout(mesh_row)
        form.addRow("Mesh file:", self.mesh_row_widget)
        self.scale_spin = QDoubleSpinBox()
        self.scale_spin.setRange(0.0001, 1000)
        self.scale_spin.setDecimals(4)
        self.scale_spin.setValue(0.001)
        self.scale_spin.setToolTip("Mesh units → metres (0.001 for millimetre CAD exports)")
        form.addRow("Mesh scale:", self.scale_spin)

        self.colour_button = QPushButton()
        self.colour_button.setStyleSheet(_swatch_style(self._colour))
        self.colour_button.clicked.connect(self._choose_colour)
        form.addRow("Colour:", self.colour_button)
        layout.addLayout(form)
        self.model_note = _hint("")
        layout.addWidget(self.model_note)
        layout.addStretch()
        return page

    def _build_tracking_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(_heading("How is the drone tracked?"))
        self.tracked_radio = QRadioButton("By motion capture (Vicon / OptiTrack)")
        self.simulated_radio = QRadioButton("Not tracked — a simulated drone you fly from the Command panel")
        group = QButtonGroup(page)
        for radio in (self.tracked_radio, self.simulated_radio):
            group.addButton(radio)
            layout.addWidget(radio)
            radio.toggled.connect(self._update_tracking_fields)

        self.tracking_box = QWidget()
        box = QVBoxLayout(self.tracking_box)
        box.setContentsMargins(20, 4, 0, 0)
        mocap_row = QHBoxLayout()
        self.mocap_status = QLabel()
        mocap_row.addWidget(self.mocap_status, 1)
        self.mocap_connect_button = QPushButton("Connect motion capture")
        self.mocap_connect_button.clicked.connect(self._connect_mocap)
        mocap_row.addWidget(self.mocap_connect_button)
        box.addLayout(mocap_row)

        box.addWidget(QLabel("Pick the drone's subject:"))
        self.subject_list = QListWidget()
        self.subject_list.setMinimumHeight(130)
        self.subject_list.currentItemChanged.connect(self._on_subject_picked)
        box.addWidget(self.subject_list)
        subject_row = QHBoxLayout()
        subject_row.addWidget(QLabel("Subject name:"))
        self.subject_edit = QLineEdit()
        self.subject_edit.setPlaceholderText("as named in Vicon Tracker / Motive")
        subject_row.addWidget(self.subject_edit, 1)
        box.addLayout(subject_row)
        self.subject_status = QLabel()
        self.subject_status.setWordWrap(True)
        box.addWidget(self.subject_status)
        box.addWidget(_hint("Not sure which one it is? Pick it up and move it — its position changes in the list."))
        layout.addWidget(self.tracking_box)
        layout.addStretch()
        self.subject_edit.textChanged.connect(lambda _t: self._refresh_live())
        return page

    def _build_vehicle_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(_heading("Is there a flight controller to talk to?"))
        self.no_vehicle_radio = QRadioButton("No — show and track it only")
        self.vehicle_radio = QRadioButton("Yes — connect to its PX4 flight controller over MAVLink")
        group = QButtonGroup(page)
        for radio in (self.no_vehicle_radio, self.vehicle_radio):
            group.addButton(radio)
            layout.addWidget(radio)
            radio.toggled.connect(self._update_vehicle_fields)

        self.vehicle_box = QWidget()
        box = QFormLayout(self.vehicle_box)
        box.setContentsMargins(20, 4, 0, 0)
        self.connection_combo = QComboBox()
        self.connection_combo.currentIndexChanged.connect(self._update_vehicle_fields)
        box.addRow("Connection:", self.connection_combo)

        self.new_connection_box = QWidget()
        new_form = QFormLayout(self.new_connection_box)
        new_form.setContentsMargins(0, 0, 0, 0)
        self.connection_name_edit = QLineEdit()
        self._connection_name_touched = False
        self.connection_name_edit.textEdited.connect(lambda _t: setattr(self, "_connection_name_touched", True))
        new_form.addRow("Name:", self.connection_name_edit)
        address_row = QHBoxLayout()
        self.address_edit = QLineEdit()
        self.address_edit.setToolTip("udpin:0.0.0.0:<port> listens for the drone on that UDP port")
        address_row.addWidget(self.address_edit, 1)
        self.find_button = QPushButton("Find vehicles")
        self.find_button.clicked.connect(self._find_vehicles)
        address_row.addWidget(self.find_button)
        new_form.addRow("Address:", address_row)
        self.found_list = QListWidget()
        self.found_list.setMaximumHeight(80)
        self.found_list.itemClicked.connect(lambda item: self.address_edit.setText(item.data(Qt.UserRole)))
        self.found_list.hide()
        new_form.addRow("", self.found_list)
        new_form.addRow(_hint("Each drone needs its own port: it must send MAVLink to this PC on that port, "
                              "and each needs a different MAV_SYS_ID."))
        box.addRow(self.new_connection_box)

        connect_row = QHBoxLayout()
        self.vehicle_status = QLabel()
        self.vehicle_status.setWordWrap(True)
        connect_row.addWidget(self.vehicle_status, 1)
        self.vehicle_connect_button = QPushButton("Connect now")
        self.vehicle_connect_button.clicked.connect(self._connect_vehicle)
        connect_row.addWidget(self.vehicle_connect_button)
        box.addRow(connect_row)

        self.send_mocap_check = QCheckBox("Send motion capture to the vehicle")
        self.send_mocap_check.setToolTip("PX4 uses it as its position (external vision). Only fresh tracking is "
                                         "sent; it pauses automatically if tracking is lost.")
        box.addRow(self.send_mocap_check)
        layout.addWidget(self.vehicle_box)
        layout.addStretch()
        return page

    def _build_review_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(_heading("Check and finish"))
        self.review_rows = QVBoxLayout()
        layout.addLayout(self.review_rows)
        self._review_labels = {}
        for key in ("drone", "tracking", "vehicle", "mocap"):
            label = QLabel()
            label.setWordWrap(True)
            label.setStyleSheet("padding: 2px 0;")
            self.review_rows.addWidget(label)
            self._review_labels[key] = label
        layout.addSpacing(10)
        self.control_check = QCheckBox("Fly it now — select it in the Command panel")
        self.control_check.setChecked(True)
        layout.addWidget(self.control_check)
        self.follow_check = QCheckBox("Follow it with the camera")
        layout.addWidget(self.follow_check)
        layout.addSpacing(10)
        layout.addWidget(_hint("Anything that isn't green yet can be finished later — the drone keeps its setup, "
                               "the vehicle reconnects automatically, and \"Drone setup…\" in the Command panel "
                               "brings you back here."))
        layout.addStretch()
        return page

    # ------------------------------------------------------------------
    # Prefill
    # ------------------------------------------------------------------

    def _prefill(self):
        obj = self.edit_object
        if obj is None:
            self.name_edit.setText(self.objects.unique_name("Drone"))
            self.simulated_radio.setChecked(True)
            self.no_vehicle_radio.setChecked(True)
        else:
            self.name_edit.setText(obj.name)
            self.model_combo.setEnabled(False)
            self.model_note.setText("The model of an existing drone is kept. Change its size on its card in the "
                                    "Objects panel.")
            (self.tracked_radio if obj.tracked else self.simulated_radio).setChecked(True)
            self.subject_edit.setText(obj.tracking_id or "")
            (self.vehicle_radio if obj.mavlink_config.enabled else self.no_vehicle_radio).setChecked(True)
            self.send_mocap_check.setChecked(obj.mavlink_config.send_mocap)
        self._refill_connections(select=obj.mavlink_config.linked_connection_name if obj else None)
        self.connection_name_edit.setText(self.name_edit.text())
        self.address_edit.setText(f"udpin:0.0.0.0:{self.suggest_port()}")
        self._update_model_fields()
        self._on_subjects_updated(self.mocap.subjects_snapshot() if self.mocap else [])

    def suggest_port(self) -> int:
        """A UDP port no existing connection listens on."""
        used = set()
        if self.mavlink is not None:
            for config in self.mavlink.get_all_connections().values():
                match = re.search(r":(\d+)$", config.connection_string)
                if match:
                    used.add(int(match.group(1)))
        port = DEFAULT_PORT
        while port in used:
            port += 1
        return port

    def _refill_connections(self, select=None):
        current = select if select is not None else self.connection_combo.currentData()
        self.connection_combo.blockSignals(True)
        self.connection_combo.clear()
        if self.mavlink is not None:
            for name in self.mavlink.get_available_connection_names():
                conn = self.mavlink.get_connection_by_name(name)
                state = "connected" if conn is not None and conn.is_connected else "not connected"
                self.connection_combo.addItem(f"{name} ({state})", name)
        self.connection_combo.addItem("New connection…", NEW_CONNECTION)
        index = self.connection_combo.findData(current)
        if index < 0:
            index = self.connection_combo.findData(NEW_CONNECTION) if not current else 0
        self.connection_combo.setCurrentIndex(max(0, index))
        self.connection_combo.blockSignals(False)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def current_step(self) -> int:
        return self.pages.currentIndex()

    def go_to(self, index):
        self.pages.setCurrentIndex(index)
        self.error_label.setText("")
        self.steps_label.setText("  ›  ".join(
            f"<b>{i + 1}. {name}</b>" if i == index else f"{i + 1}. {name}" for i, name in enumerate(STEPS)))
        self.back_button.setEnabled(index > 0)
        self.next_button.setText("Finish" if index == len(STEPS) - 1 else "Next >")
        if index == 2:
            if not self._connection_name_touched and self._pending_connection is None:
                self.connection_name_edit.setText(self.name_edit.text().strip())
            self._update_vehicle_fields()
        if index == 3:
            self._refresh_review()

    def next(self):
        error = self.validate_step(self.current_step())
        if error:
            self.error_label.setText(error)
            return
        if self.current_step() == len(STEPS) - 1:
            self.finish()
        else:
            self.go_to(self.current_step() + 1)

    def back(self):
        if self.current_step() > 0:
            self.go_to(self.current_step() - 1)

    def validate_step(self, step):
        if step == 0:
            if not self.name_edit.text().strip():
                return "Give the drone a name."
            if self.model_combo.currentData() == "mesh" and not self._mesh_path and self.edit_object is None:
                return "Choose a mesh file, or pick another model."
        if step == 1 and self.tracked_radio.isChecked() and not self.subject_edit.text().strip():
            return "Pick the drone's motion capture subject (or choose “Not tracked”)."
        if step == 2 and self.vehicle_radio.isChecked():
            if self.connection_combo.currentData() == NEW_CONNECTION:
                if not self.address_edit.text().strip():
                    return "Enter the connection address (e.g. udpin:0.0.0.0:14550)."
                name = self.connection_name_edit.text().strip()
                if not name:
                    return "Give the connection a name."
                if (self._pending_connection is None and self.mavlink is not None
                        and name in self.mavlink.get_all_connections()):
                    return (f"A connection called '{name}' already exists — pick it from the list, "
                            "or give the new one another name.")
        return None

    # ------------------------------------------------------------------
    # Step 1 helpers
    # ------------------------------------------------------------------

    def _update_model_fields(self):
        is_mesh = self.model_combo.currentData() == "mesh" and self.edit_object is None
        self.mesh_row_widget.setVisible(is_mesh)
        self.scale_spin.setVisible(is_mesh)
        for widget in (self.mesh_row_widget, self.scale_spin):
            label = self.drone_form.labelForField(widget)
            if label is not None:
                label.setVisible(is_mesh)

    def _choose_mesh(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose mesh", "cad_files", "Meshes (*.stl *.obj)")
        if path:
            self.set_mesh_path(path)

    def set_mesh_path(self, path):
        self._mesh_path = path
        self.mesh_label.setText(os.path.basename(path))

    def _choose_colour(self):
        colour = QColorDialog.getColor(QColor.fromRgbF(*self._colour[:3]), self, "Drone colour")
        if colour.isValid():
            self._colour = (colour.redF(), colour.greenF(), colour.blueF(), 1.0)
            self.colour_button.setStyleSheet(_swatch_style(self._colour))

    # ------------------------------------------------------------------
    # Step 2 helpers
    # ------------------------------------------------------------------

    def _update_tracking_fields(self, *_):
        self.tracking_box.setEnabled(self.tracked_radio.isChecked())
        self._refresh_live()

    def _connect_mocap(self):
        if self.mocap is not None:
            self.mocap.connect_source()
            _status(self.mocap_status, WARN, "Connecting…")

    @pyqtSlot(bool)
    def _on_mocap_connection_changed(self, _connected):
        self._refresh_live()

    def _subject_owner(self, subject):
        return next((o for o in self.objects.get_objects()
                     if o.tracked and o.tracking_id == subject and o is not self.edit_object), None)

    @pyqtSlot(object)
    def _on_subjects_updated(self, subjects):
        names = [s.name for s in subjects]
        existing = [self.subject_list.item(i).data(Qt.UserRole) for i in range(self.subject_list.count())]
        if names != existing:
            self.subject_list.blockSignals(True)
            self.subject_list.clear()
            for name in names:
                item = QListWidgetItem()
                item.setData(Qt.UserRole, name)
                self.subject_list.addItem(item)
            self.subject_list.blockSignals(False)
            self._auto_pick_subject(names)
        for i, info in enumerate(subjects):
            owner = self._subject_owner(info.name)
            x, y, z = info.pose[:3]
            text = f"{info.name}    {info.rate_hz:.0f} Hz    ({x:+.2f}, {y:+.2f}, {z:+.2f})"
            if info.age_s > 1.0:
                text = f"{info.name}    lost"
            if owner is not None:
                text += f"    — used by '{owner.name}'"
            item = self.subject_list.item(i)
            item.setText(text)
            if item.data(Qt.UserRole) == self.subject_edit.text().strip():
                self.subject_list.blockSignals(True)
                self.subject_list.setCurrentItem(item)
                self.subject_list.blockSignals(False)
        self._refresh_live()

    def _auto_pick_subject(self, names):
        """Pre-select a subject named like the drone (or the only unused one)."""
        if self.subject_edit.text().strip() or not names:
            return
        drone = self.name_edit.text().strip().lower()
        match = next((n for n in names if n.lower() == drone), None)
        if match is None:
            free = [n for n in names if self._subject_owner(n) is None]
            match = free[0] if len(free) == 1 else None
        if match is not None:
            self.subject_edit.setText(match)
            if self.edit_object is None:
                self.tracked_radio.setChecked(True)

    def _on_subject_picked(self, item, _previous=None):
        if item is not None:
            self.subject_edit.setText(item.data(Qt.UserRole))

    # ------------------------------------------------------------------
    # Step 3 helpers
    # ------------------------------------------------------------------

    def selected_connection_name(self):
        data = self.connection_combo.currentData()
        if data == NEW_CONNECTION:
            return self._pending_connection or self.connection_name_edit.text().strip()
        return data

    def _update_vehicle_fields(self, *_):
        wants_vehicle = self.vehicle_radio.isChecked()
        self.vehicle_box.setEnabled(wants_vehicle)
        new = self.connection_combo.currentData() == NEW_CONNECTION
        self.new_connection_box.setVisible(new)
        tracked = self.tracked_radio.isChecked()
        self.send_mocap_check.setEnabled(tracked)
        if not tracked:
            self.send_mocap_check.setChecked(False)
            self.send_mocap_check.setText("Send motion capture to the vehicle (needs tracking — step 2)")
        else:
            self.send_mocap_check.setText("Send motion capture to the vehicle")
            if self.edit_object is None and not self.send_mocap_check.isChecked() and wants_vehicle:
                self.send_mocap_check.setChecked(True)
        self._refresh_live()

    def _find_vehicles(self):
        if self.mavlink is None:
            return
        from ui.dock.panels.mavlink_panel import DiscoveryWorker
        self.find_button.setEnabled(False)
        self.find_button.setText("Searching…")
        self._discovery = DiscoveryWorker(self.mavlink, timeout_secs=2.0, parent=self)
        self._discovery.devices_discovered.connect(self._on_vehicles_found)
        self._discovery.error.connect(lambda message: self._on_vehicles_found([]))
        self._discovery.start()

    @pyqtSlot(object)
    def _on_vehicles_found(self, devices):
        self.find_button.setEnabled(True)
        self.find_button.setText("Find vehicles")
        self.found_list.clear()
        for device in devices:
            item = QListWidgetItem(device.display_name)
            item.setData(Qt.UserRole, device.connection_string)
            self.found_list.addItem(item)
        if not devices:
            self.found_list.addItem("No vehicles found — check it's powered and sending to this PC.")
        self.found_list.show()

    def _connect_vehicle(self):
        if self.mavlink is None:
            return
        if self.connection_combo.currentData() == NEW_CONNECTION:
            config = MavlinkConnectionConfig(self.address_edit.text().strip(),
                                             name=self.connection_name_edit.text().strip())
            self._pending_connection = self.mavlink.add_connection_async(config)
        else:
            name = self.connection_combo.currentData()
            saved = self.mavlink.get_all_connections().get(name)
            if saved is not None:
                self.mavlink.add_connection_async(saved)
        self._refresh_live()

    @pyqtSlot(str, bool, str)
    def _on_connection_attempt_finished(self, name, success, message):
        if name != self.selected_connection_name():
            return
        if success and self.connection_combo.currentData() == NEW_CONNECTION:
            self._refill_connections(select=name)
            self._pending_connection = None
            self._update_vehicle_fields()
        self._last_attempt_message = "" if success else message
        self._refresh_live()

    # ------------------------------------------------------------------
    # Live status
    # ------------------------------------------------------------------

    def _subject_state(self):
        subject = self.subject_edit.text().strip()
        if not self.tracked_radio.isChecked():
            return OFF, "Not tracked — simulated drone"
        if self.mocap is None or not self.mocap.is_connected():
            return WARN, "Motion capture isn't connected yet"
        if not subject:
            return WARN, "No subject chosen"
        info = next((s for s in self.mocap.subjects_snapshot() if s.name == subject), None)
        if info is None:
            return WARN, f"Subject '{subject}' isn't being received right now"
        if info.age_s > 1.0:
            return BAD, f"Subject '{subject}' is not visible (lost {info.age_s:.0f} s ago)"
        owner = self._subject_owner(subject)
        note = f" — will be taken over from '{owner.name}'" if owner is not None else ""
        return OK, f"Tracked by '{subject}' · {info.rate_hz:.0f} Hz{note}"

    def _vehicle_state(self):
        if not self.vehicle_radio.isChecked():
            return OFF, "No flight controller (visual only)"
        if self.mavlink is None:
            return WARN, "MAVLink unavailable"
        name = self.selected_connection_name()
        conn = self.mavlink.get_connection_by_name(name) if name else None
        if conn is not None and conn.is_connected:
            return OK, f"'{name}' connected (system ID {conn.status.system_id})"
        if name and self.mavlink.is_connecting(name):
            return WARN, f"Connecting to '{name}'…"
        message = getattr(self, "_last_attempt_message", "")
        if message:
            return BAD, message
        return WARN, f"'{name or 'new connection'}' not connected yet — it will connect when you finish"

    def _refresh_live(self):
        connected = self.mocap is not None and self.mocap.is_connected()
        if self.mocap is None:
            _status(self.mocap_status, OFF, "Motion capture unavailable")
        elif connected:
            _status(self.mocap_status, OK, "Motion capture connected")
        else:
            _status(self.mocap_status, WARN, "Motion capture isn't connected")
        self.mocap_connect_button.setVisible(self.mocap is not None and not connected)
        _status(self.subject_status, *self._subject_state())
        state, text = self._vehicle_state()
        _status(self.vehicle_status, state, text)
        self.vehicle_connect_button.setVisible(self.vehicle_radio.isChecked() and state != OK)
        self.vehicle_connect_button.setEnabled(not text.startswith("Connecting"))
        if self.current_step() == 3:
            self._refresh_review()

    def _refresh_review(self):
        model = {"quad": "quadcopter", "ball": "marker ball", "mesh": "custom mesh"}[self.model_combo.currentData()]
        verb = "Update" if self.edit_object else "Create"
        drone_text = f"{verb} drone '{self.name_edit.text().strip()}'" + ("" if self.edit_object else f" ({model})")
        _status(self._review_labels["drone"], OK, drone_text)
        _status(self._review_labels["tracking"], *self._subject_state())
        _status(self._review_labels["vehicle"], *self._vehicle_state())
        mocap_label = self._review_labels["mocap"]
        if not self.vehicle_radio.isChecked():
            mocap_label.hide()
        else:
            mocap_label.show()
            if self.send_mocap_check.isChecked():
                _status(mocap_label, OK, "Motion capture will be sent to the vehicle while tracking is good")
            elif self.tracked_radio.isChecked():
                _status(mocap_label, WARN, "Motion capture will NOT be sent to the vehicle")
            else:
                _status(mocap_label, OFF, "No motion capture to send (not tracked)")

    # ------------------------------------------------------------------
    # Finish
    # ------------------------------------------------------------------

    def _make_object(self, name):
        model = self.model_combo.currentData()
        if model == "quad":
            return CadMesh(QUAD_MESH, name=name, scale=QUAD_SCALE, colour=self._colour)
        if model == "ball":
            return Sphere(name=name, radius=0.08, colour=self._colour, controllable=True)
        return CadMesh(self._mesh_path, name=name, scale=self.scale_spin.value(), colour=self._colour)

    def apply(self):
        """Create or update the drone from the wizard's choices; returns it."""
        name = self.name_edit.text().strip()
        obj = self.edit_object
        if obj is None:
            obj = self._make_object(name)
            obj.set_pose((0.0, 0.3, 0.0, 1.0, 0.0, 0.0, 0.0))
        else:
            self.objects.rename_object(obj, name)
            obj.colour = self._colour
        obj.controllable = True

        # Tracking
        subject = self.subject_edit.text().strip()
        if self.tracked_radio.isChecked() and subject:
            for other in self.objects.get_objects():
                if other is not obj and other.tracked and other.tracking_id == subject:
                    other.tracked = False
                    self.objects.notify_object_changed(other)
            obj.set_tracked(True, subject)
            obj.pose_locked = False
            info = next((s for s in self.mocap.subjects_snapshot() if s.name == subject), None) if self.mocap else None
            if info is not None:
                obj.set_pose(info.pose)   # appear where it really is
        else:
            obj.tracked = False
            obj.tracking_id = None

        if self.edit_object is None:
            self.objects.add_object(obj)

        # Vehicle
        if self.mavlink is not None:
            if self.vehicle_radio.isChecked():
                connection = self.selected_connection_name()
                if self.connection_combo.currentData() == NEW_CONNECTION and \
                        connection not in self.mavlink.get_all_connections() and \
                        not self.mavlink.is_connecting(connection):
                    config = MavlinkConnectionConfig(self.address_edit.text().strip(), name=connection)
                    self.mavlink.save_connection_config(config)
                    connection = config.name
                    self.mavlink.add_connection_async(config)
                obj.mavlink_config.send_mocap = self.send_mocap_check.isChecked()
                self.mavlink.link_object(obj, connection)
            elif obj.mavlink_config.enabled:
                self.mavlink.unlink_object(obj, disable=True)
        self.objects.notify_object_changed(obj)
        return obj

    def finish(self):
        obj = self.apply()
        self.drone_ready.emit(obj, {"control": self.control_check.isChecked(),
                                    "follow": self.follow_check.isChecked()})
        self.accept()

    def done(self, result):
        for signal, slot in (
                (getattr(self.mocap, "subjects_updated", None), self._on_subjects_updated),
                (getattr(self.mocap, "connection_changed", None), self._on_mocap_connection_changed),
                (getattr(self.mavlink, "connection_attempt_finished", None), self._on_connection_attempt_finished)):
            if signal is not None:
                try:
                    signal.disconnect(slot)
                except TypeError:
                    pass
        self._timer.stop()
        super().done(result)
