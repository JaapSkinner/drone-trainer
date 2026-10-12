"""Calibration dialog: align the motion capture frame with the lab.

Opened from the Motion Capture panel. Changes preview live (tracked objects move
as you adjust); Apply keeps them, Cancel restores the previous calibration.
"""
from PyQt5.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDoubleSpinBox,
                             QFormLayout, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
                             QPushButton, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout,
                             QWidget)

from models.mocap_calibration import (CalibrationError, MocapCalibration, solve_origin_direction,
                                      solve_reference_points)
from ui import theme
from ui.dialogs.shell import DialogShell

CAPTURE_SECONDS = 1.0
STEADY_LIMIT_M = 0.005   # warn if the object moved more than this during a capture

_GOOD, _WARN, _BAD, _MUTED = "success", "warning", "danger", "muted"   # label tones


def _fmt(p):
    x, y, z = (round(v, 3) + 0.0 for v in p[:3])  # + 0.0 turns -0.0 into 0.0
    return f"({x:+.3f}, {y:+.3f}, {z:+.3f})"


def _spin(minimum, maximum, decimals, step):
    spin = QDoubleSpinBox()
    spin.setRange(minimum, maximum)
    spin.setDecimals(decimals)
    spin.setSingleStep(step)
    spin.setKeyboardTracking(False)
    return spin


def _hint(text):
    return theme.hint(text)


class MocapCalibrationDialog(DialogShell):
    calibration_applied = pyqtSignal(object)   # MocapCalibration that should be saved

    def __init__(self, motion_capture_service, parent=None):
        super().__init__("Calibrate motion capture",
                         "Align the motion capture frame with the lab. Changes preview live in the viewport; "
                         "Apply keeps them, Cancel puts the old calibration back.",
                         accept_text="Apply", parent=parent)
        # No explicit minimum size: Qt then derives it from the layout, so
        # nothing can overlap when the window is made small.
        self.resize(580, 620)
        self.service = motion_capture_service
        self._original = motion_capture_service.get_calibration()
        self._preview = self._original
        self._pending_capture = None       # "origin" | "direction" | "point"
        self._origin = None
        self._direction = None
        self._points = []                  # [{"measured": (x,y,z), "target": [x,y,z]}]
        self._updating_manual = False

        layout = self.body

        subject_row = QHBoxLayout()
        subject_row.addWidget(QLabel("Calibration object:"))
        self.subject_combo = QComboBox()
        self.subject_combo.setMinimumWidth(160)
        subject_row.addWidget(self.subject_combo, 1)
        layout.addLayout(subject_row)
        self.live_label = theme.label("", "hint", wrap=True)
        layout.addWidget(self.live_label)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_origin_tab(), "Origin && direction")
        self.tabs.addTab(self._build_points_tab(), "Reference points")
        self.tabs.addTab(self._build_manual_tab(), "Manual")
        layout.addWidget(self.tabs)

        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        self.summary_label.setProperty("role", "banner")
        self.summary_label.setProperty("tone", "accent")
        layout.addWidget(self.summary_label)

        self.reset_button = theme.button("Reset to none", "ghost", "refresh-cw")
        self.reset_button.setToolTip("Use the mocap system's frame unchanged")
        self.reset_button.clicked.connect(lambda: self.set_preview(MocapCalibration()))
        self.footer_left.addWidget(self.reset_button)
        self.apply_button = self.accept_button

        self.service.subjects_updated.connect(self.on_subjects_updated)
        self.service.capture_finished.connect(self.on_capture_finished)
        self.on_subjects_updated(self.service.subjects_snapshot())
        self._show_calibration(self._original)

    # ------------------------------------------------------------------
    # Tabs
    # ------------------------------------------------------------------

    def _build_origin_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)
        form.addRow(_hint("Quickest method. Keeps the mocap system's vertical axis and sets where the "
                          "origin is and which way +X (forward / North) points."))

        self.origin_button = theme.button("1. Capture origin", "subtle", "crosshair")
        self.origin_button.setToolTip("Place the object where the scene origin should be, hold it still")
        self.origin_button.clicked.connect(lambda: self.start_capture("origin"))
        self.origin_status = QLabel("Place the object at the new origin.")
        form.addRow(self.origin_button, self.origin_status)

        self.direction_button = theme.button("2. Capture direction", "subtle", "crosshair")
        self.direction_button.setToolTip("Move the object along the new +X axis (at least 20 cm)")
        self.direction_button.clicked.connect(lambda: self.start_capture("direction"))
        self.direction_status = QLabel("Then move it along the new +X axis.")
        form.addRow(self.direction_button, self.direction_status)

        self.origin_height_spin = _spin(-5.0, 5.0, 3, 0.01)
        self.origin_height_spin.setSuffix(" m")
        self.origin_height_spin.setToolTip("Height of the object's tracked point above the floor at the "
                                           "origin (0 if its origin is at its base)")
        form.addRow("Object height at origin:", self.origin_height_spin)

        self.origin_compute_button = theme.button("Use origin && direction", "primary", "check")
        self.origin_compute_button.clicked.connect(self.compute_origin_direction)
        compute_row = QHBoxLayout()
        compute_row.addStretch()
        compute_row.addWidget(self.origin_compute_button)
        form.addRow(compute_row)
        self.origin_error = QLabel()
        self.origin_error.setWordWrap(True)
        form.addRow(self.origin_error)
        return tab

    def _build_points_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(_hint("Most accurate. Put the object on marks whose lab positions you know "
                               "(floor tape, a corner…), capture each, and type the true position."))
        self.points_table = QTableWidget(0, 5)
        self.points_table.setHorizontalHeaderLabels(["Measured (m)", "Target X", "Target Y", "Target Z", "Error"])
        self.points_table.verticalHeader().setVisible(True)
        self.points_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        header = self.points_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        self.points_table.itemChanged.connect(self._on_target_edited)
        self.points_table.setMinimumHeight(170)
        layout.addWidget(self.points_table, 1)

        row = QHBoxLayout()
        self.point_button = theme.button("Capture point", "subtle", "crosshair")
        self.point_button.clicked.connect(lambda: self.start_capture("point"))
        row.addWidget(self.point_button)
        remove = theme.button("Remove", "ghost", "trash", "sm")
        remove.clicked.connect(self._remove_selected_points)
        row.addWidget(remove)
        row.addStretch()
        layout.addLayout(row)

        self.keep_vertical_check = QCheckBox("Keep the vertical axis (only rotate about up)")
        self.keep_vertical_check.setChecked(True)
        self.keep_vertical_check.setToolTip("Untick to also correct a tilted floor — needs 3+ points "
                                            "that aren't in a line")
        layout.addWidget(self.keep_vertical_check)

        self.solve_button = theme.button("Solve from points", "primary", "target")
        self.solve_button.clicked.connect(self.solve_points)
        layout.addWidget(self.solve_button, 0, Qt.AlignRight)
        self.points_status = QLabel()
        self.points_status.setWordWrap(True)
        layout.addWidget(self.points_status)
        return tab

    def _build_manual_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.addWidget(_hint("Rotate and shift the mocap frame directly. Results from the other tabs "
                               "show up here too, so you can fine-tune them."))
        grid = QGridLayout()
        for col, axis in enumerate(("X", "Y (up)", "Z")):
            grid.addWidget(theme.label(axis, "hint"), 0, col + 1, Qt.AlignCenter)
        grid.addWidget(QLabel("Rotate (°)"), 1, 0)
        grid.addWidget(QLabel("Offset (m)"), 2, 0)
        self.rotation_spins = [_spin(-180.0, 180.0, 2, 1.0) for _ in range(3)]
        self.offset_spins = [_spin(-100.0, 100.0, 3, 0.01) for _ in range(3)]
        for col in range(3):
            grid.addWidget(self.rotation_spins[col], 1, col + 1)
            grid.addWidget(self.offset_spins[col], 2, col + 1)
            self.rotation_spins[col].valueChanged.connect(self._on_manual_edited)
            self.offset_spins[col].valueChanged.connect(self._on_manual_edited)
        layout.addLayout(grid)
        layout.addStretch()
        return tab

    # ------------------------------------------------------------------
    # Preview / summary
    # ------------------------------------------------------------------

    def preview(self) -> MocapCalibration:
        return self._preview

    def set_preview(self, calibration: MocapCalibration):
        self._preview = calibration
        self.service.set_calibration(calibration)
        self._show_calibration(calibration)

    def _show_calibration(self, calibration):
        self.summary_label.setText(calibration.describe())
        self._updating_manual = True
        try:
            for spin, value in zip(self.rotation_spins, calibration.euler_deg()):
                spin.setValue(value)
            for spin, value in zip(self.offset_spins, calibration.translation):
                spin.setValue(value)
        finally:
            self._updating_manual = False

    def _on_manual_edited(self, _value=None):
        if self._updating_manual:
            return
        cal = MocapCalibration.from_manual([s.value() for s in self.rotation_spins],
                                           [s.value() for s in self.offset_spins])
        self._preview = cal
        self.service.set_calibration(cal)
        self.summary_label.setText(cal.describe())

    # ------------------------------------------------------------------
    # Live subjects
    # ------------------------------------------------------------------

    def selected_subject(self):
        return self.subject_combo.currentText().strip() or None

    @pyqtSlot(object)
    def on_subjects_updated(self, subjects):
        names = [s.name for s in subjects]
        current = self.selected_subject()
        existing = [self.subject_combo.itemText(i) for i in range(self.subject_combo.count())]
        if names != existing:
            self.subject_combo.blockSignals(True)
            self.subject_combo.clear()
            self.subject_combo.addItems(names)
            if current in names:
                self.subject_combo.setCurrentIndex(names.index(current))
            self.subject_combo.blockSignals(False)

        info = next((s for s in subjects if s.name == self.selected_subject()), None)
        connected = self.service.is_connected()
        if not connected:
            self._set_live("Connect to a motion capture source to capture positions.", _MUTED)
        elif info is None:
            self._set_live("Waiting for subjects…", _WARN)
        elif info.age_s > 1.0:
            self._set_live(f"'{info.name}' is not visible to the cameras.", _BAD)
        else:
            self._set_live(f"'{info.name}' is at {_fmt(info.pose)} m in the calibrated frame.", _GOOD)
        can_capture = connected and info is not None and self._pending_capture is None
        for button in (self.origin_button, self.direction_button, self.point_button):
            button.setEnabled(can_capture)

    def _set_live(self, text, colour):
        self.live_label.setText(text)
        theme.set_tone(self.live_label, colour)

    # ------------------------------------------------------------------
    # Capturing
    # ------------------------------------------------------------------

    def start_capture(self, purpose: str):
        subject = self.selected_subject()
        if not subject:
            return
        self._pending_capture = purpose
        status = {"origin": self.origin_status, "direction": self.direction_status,
                  "point": self.points_status}[purpose]
        status.setText("Capturing… hold the object still.")
        theme.set_tone(status, _WARN)
        for button in (self.origin_button, self.direction_button, self.point_button):
            button.setEnabled(False)
        self.service.capture_subject(subject, CAPTURE_SECONDS)

    @pyqtSlot(object)
    def on_capture_finished(self, result):
        purpose, self._pending_capture = self._pending_capture, None
        if purpose is None or result.subject != self.selected_subject():
            return
        status = {"origin": self.origin_status, "direction": self.direction_status,
                  "point": self.points_status}[purpose]
        if not result.ok:
            status.setText("No data — is the object visible to the cameras?")
            theme.set_tone(status, _BAD)
            return
        text = f"✓ {_fmt(result.mean)}"
        colour = _GOOD
        if result.std_m > STEADY_LIMIT_M:
            text += f"  (moved ±{1000 * result.std_m:.0f} mm — recapture holding it still)"
            colour = _WARN
        status.setText(text)
        theme.set_tone(status, colour)
        if purpose == "origin":
            self._origin = result.mean
        elif purpose == "direction":
            self._direction = result.mean
        else:
            self.add_point(result.mean)
        self.on_subjects_updated(self.service.subjects_snapshot())

    # ------------------------------------------------------------------
    # Solving
    # ------------------------------------------------------------------

    def compute_origin_direction(self):
        if self._origin is None or self._direction is None:
            self._show_error(self.origin_error, "Capture both the origin and the direction first.")
            return None
        try:
            cal = solve_origin_direction(self._origin, self._direction, self.origin_height_spin.value())
        except CalibrationError as exc:
            self._show_error(self.origin_error, str(exc))
            return None
        self.origin_error.setText("")
        self.set_preview(cal)
        return cal

    def add_point(self, measured, target=None):
        target = list(target) if target is not None else [0.0, 0.0, 0.0]
        self._points.append({"measured": tuple(measured), "target": target})
        self._refresh_points_table()

    def _refresh_points_table(self, residuals=None):
        table = self.points_table
        table.blockSignals(True)
        table.setRowCount(len(self._points))
        for row, point in enumerate(self._points):
            x, y, z = (round(v, 2) + 0.0 for v in point["measured"])
            measured = QTableWidgetItem(f"{x:+.2f}, {y:+.2f}, {z:+.2f}")
            measured.setToolTip(f"Uncalibrated position {_fmt(point['measured'])} m")
            measured.setFlags(measured.flags() & ~Qt.ItemIsEditable)
            table.setItem(row, 0, measured)
            for col in range(3):
                table.setItem(row, col + 1, QTableWidgetItem(f"{point['target'][col]:.3f}"))
            error = QTableWidgetItem("" if residuals is None else f"{1000 * residuals[row]:.1f} mm")
            error.setFlags(error.flags() & ~Qt.ItemIsEditable)
            table.setItem(row, 4, error)
        table.blockSignals(False)

    def _on_target_edited(self, item):
        if item.column() not in (1, 2, 3):
            return
        try:
            value = float(item.text())
        except ValueError:
            value = self._points[item.row()]["target"][item.column() - 1]
        self._points[item.row()]["target"][item.column() - 1] = value
        self.points_table.blockSignals(True)
        item.setText(f"{value:.3f}")
        self.points_table.blockSignals(False)

    def _remove_selected_points(self):
        rows = sorted({i.row() for i in self.points_table.selectedIndexes()}, reverse=True)
        for row in rows:
            del self._points[row]
        self._refresh_points_table()

    def solve_points(self):
        try:
            fit = solve_reference_points([p["measured"] for p in self._points],
                                         [p["target"] for p in self._points],
                                         keep_vertical=self.keep_vertical_check.isChecked())
        except CalibrationError as exc:
            self._show_error(self.points_status, str(exc))
            return None
        self._refresh_points_table(fit.residuals_m)
        rms_mm = 1000 * fit.calibration.rms_error_m
        colour = _GOOD if rms_mm < 10 else _WARN
        note = "" if rms_mm < 10 else " — check the targets, or untick “keep vertical axis”"
        self.points_status.setText(f"Fit error {rms_mm:.1f} mm RMS over {len(self._points)} point(s){note}")
        theme.set_tone(self.points_status, colour)
        self.set_preview(fit.calibration)
        return fit

    @staticmethod
    def _show_error(label, text):
        label.setText(text)
        theme.set_tone(label, _BAD)

    # ------------------------------------------------------------------
    # Close
    # ------------------------------------------------------------------

    def accept(self):
        self.service.set_calibration(self._preview)
        self.calibration_applied.emit(self._preview)
        self._disconnect()
        super().accept()

    def reject(self):
        self.service.set_calibration(self._original)
        self._disconnect()
        super().reject()

    def _disconnect(self):
        for signal, slot in ((self.service.subjects_updated, self.on_subjects_updated),
                             (self.service.capture_finished, self.on_capture_finished)):
            try:
                signal.disconnect(slot)
            except TypeError:
                pass
