"""Drone readiness: is this object tracked, connected and streaming?

``drone_checks()`` turns the state spread over motion capture, MAVLink and the
object into a short checklist; ``DroneStatusWidget`` shows it live (Command
panel, Add-a-drone review step) with a button to fix things.
"""
from dataclasses import dataclass
from typing import List, Optional

from PyQt5.QtCore import QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ui import theme

OK, WARN, BAD, OFF = "ok", "warn", "bad", "off"
SYMBOLS = {OK: "●", WARN: "●", BAD: "●", OFF: "○"}


@dataclass
class Check:
    key: str        # "tracking" | "vehicle" | "mocap"
    title: str
    state: str      # OK | WARN | BAD | OFF
    text: str


def subject_info(motion_capture_service, subject):
    if motion_capture_service is None or not subject:
        return None
    return next((s for s in motion_capture_service.subjects_snapshot() if s.name == subject), None)


def tracking_check(obj, motion_capture_service) -> Check:
    if not obj.tracked or not obj.tracking_id:
        return Check("tracking", "Tracking", OFF, "Not tracked — simulated (fly it from the Command panel)")
    subject = obj.tracking_id
    if obj.pose_locked:
        return Check("tracking", "Tracking", WARN, f"Pose locked — motion capture for '{subject}' is ignored")
    if motion_capture_service is None or not motion_capture_service.is_connected():
        return Check("tracking", "Tracking", WARN, "Motion capture isn't connected")
    info = subject_info(motion_capture_service, subject)
    if info is None:
        similar = similar_subject(motion_capture_service, subject)
        if similar:
            return Check("tracking", "Tracking", WARN, f"Waiting for '{subject}' — did you mean '{similar}'?")
        return Check("tracking", "Tracking", WARN, f"Waiting for subject '{subject}' — is it visible to the cameras?")
    if info.age_s > 1.0:
        return Check("tracking", "Tracking", BAD, f"Lost '{subject}' {info.age_s:.0f} s ago")
    return Check("tracking", "Tracking", OK, f"{subject} · {info.rate_hz:.0f} Hz")


def similar_subject(motion_capture_service, subject):
    """A live subject whose name matches ``subject`` apart from case/spaces (common typo)."""
    if motion_capture_service is None or not subject:
        return None
    key = subject.replace(" ", "").lower()
    return next((s.name for s in motion_capture_service.subjects_snapshot()
                 if s.name != subject and s.name.replace(" ", "").lower() == key), None)


def vehicle_check(obj, mavlink_service) -> Check:
    cfg = obj.mavlink_config
    if not cfg.enabled:
        return Check("vehicle", "Vehicle", OFF, "No flight controller (visual only)")
    name = cfg.linked_connection_name
    if not name:
        return Check("vehicle", "Vehicle", BAD, "MAVLink is on but no connection is chosen")
    if mavlink_service is None:
        return Check("vehicle", "Vehicle", WARN, f"'{name}' — MAVLink unavailable")
    conn = mavlink_service.get_connection_by_name(name)
    if conn is not None and conn.is_connected:
        return Check("vehicle", "Vehicle", OK, f"{name} · connected (ID {conn.status.system_id})")
    if mavlink_service.is_connecting(name):
        return Check("vehicle", "Vehicle", WARN, f"Connecting to '{name}'…")
    saved = mavlink_service.get_all_connections().get(name)
    if saved is None:
        return Check("vehicle", "Vehicle", BAD, f"Connection '{name}' doesn't exist any more")
    retrying = saved.auto_connect and mavlink_service.get_global_settings().auto_reconnect
    return Check("vehicle", "Vehicle", WARN,
                 f"'{name}' not connected" + (" — retrying automatically" if retrying else ""))


_MOCAP_TEXT = {
    "streaming": (OK, "Sending to the vehicle"),
    "disabled": (OFF, "Not sending motion capture (turned off)"),
    "not_linked": (OFF, "No vehicle to send motion capture to"),
    "not_connected": (WARN, "Will send motion capture once the vehicle connects"),
    "not_tracked": (WARN, "Not sending motion capture: the drone isn't tracked"),
    "locked": (WARN, "Not sending motion capture: the pose is locked"),
    "tracking_lost": (BAD, "Motion capture paused: tracking lost"),
}


def mocap_check(obj, mavlink_service) -> Optional[Check]:
    if not obj.mavlink_config.enabled or mavlink_service is None:
        return None
    state, text = _MOCAP_TEXT.get(mavlink_service.mocap_stream_state(obj), (WARN, "Unknown"))
    return Check("mocap", "Mocap → vehicle", state, text)


def drone_checks(obj, motion_capture_service=None, mavlink_service=None) -> List[Check]:
    checks = [tracking_check(obj, motion_capture_service), vehicle_check(obj, mavlink_service)]
    mocap = mocap_check(obj, mavlink_service)
    if mocap is not None:
        checks.append(mocap)
    return checks


def summary_state(checks: List[Check]) -> str:
    states = {c.state for c in checks}
    return BAD if BAD in states else WARN if WARN in states else OK


class DroneStatusWidget(QWidget):
    """Live readiness checklist for one object."""

    setup_requested = pyqtSignal(object)   # the object to (re)configure; None = add a new drone
    REFRESH_MS = 500

    def __init__(self, motion_capture_service=None, mavlink_service=None, parent=None):
        super().__init__(parent)
        self.motion_capture_service = motion_capture_service
        self.mavlink_service = mavlink_service
        self.obj = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(8)
        self.grid.setVerticalSpacing(6)
        layout.addLayout(self.grid)
        self._rows = {}
        for row, key in enumerate(("tracking", "vehicle", "mocap")):
            dot, title, text = QLabel(), QLabel(), QLabel()
            dot.setFixedWidth(16)
            text.setWordWrap(True)
            title.setProperty("role", "hint")
            for col, widget in enumerate((dot, title, text)):
                self.grid.addWidget(widget, row, col)
            self._rows[key] = (dot, title, text)
        self.grid.setColumnStretch(2, 1)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.setup_button = theme.button("Drone setup…", None, "sliders-horizontal")
        self.setup_button.clicked.connect(lambda: self.setup_requested.emit(self.obj))
        buttons.addWidget(self.setup_button)
        layout.addLayout(buttons)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(self.REFRESH_MS)
        self.set_object(None)

    def set_object(self, obj):
        self.obj = obj
        self.setup_button.setText("Drone setup…" if obj is not None else "Add a drone…")
        theme.decorate(self.setup_button, None if obj is not None else "primary",
                       "sliders-horizontal" if obj is not None else "plus")
        self.refresh()

    def checks(self) -> List[Check]:
        if self.obj is None:
            return []
        return drone_checks(self.obj, self.motion_capture_service, self.mavlink_service)

    @pyqtSlot()
    def refresh(self):
        checks = {c.key: c for c in self.checks()}
        for key, (dot, title, text) in self._rows.items():
            check = checks.get(key)
            visible = check is not None
            for widget in (dot, title, text):
                widget.setVisible(visible)
            if not visible:
                continue
            dot.setPixmap(theme.state_pixmap(check.state))
            title.setText(check.title)
            text.setText(check.text)
            theme.set_tone(text, {BAD: "danger", OFF: "muted"}.get(check.state))
        if self.obj is None:
            dot, title, text = self._rows["tracking"]
            for widget in (dot, title, text):
                widget.setVisible(True)
            dot.setPixmap(theme.state_pixmap(OFF))
            title.setText("")
            text.setText("No drone selected. Choose one above, or add one.")
            theme.set_tone(text, "muted")
