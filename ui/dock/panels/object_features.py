"""Features that can be attached to a scene object from its card in the Objects panel.

A feature is a capability (motion capture tracking, MAVLink, user control …)
shown as a small box on the object's card, added from the "Add feature" menu
and removed with its ✕. Each feature maps onto attributes the services already
use, so adding one here doesn't change any service code.

To add a feature (e.g. "Gate" for an obstacle course), subclass ObjectFeature
and append an instance to FEATURES.
"""
from dataclasses import dataclass
from typing import Any, Optional

from PyQt5.QtWidgets import QCheckBox, QComboBox, QFormLayout, QLabel, QWidget


@dataclass
class FeatureContext:
    object_service: Any
    mavlink_service: Optional[Any] = None
    motion_capture_service: Optional[Any] = None


class FeatureEditor(QWidget):
    """Base editor widget; ``refresh()`` is called ~10× a second while visible."""

    def refresh(self):
        pass


class ObjectFeature:
    key = ""
    title = ""
    description = ""

    def applies_to(self, obj) -> bool:
        return not obj.helper

    def is_present(self, obj) -> bool:
        raise NotImplementedError

    def add(self, obj, ctx: FeatureContext):
        raise NotImplementedError

    def remove(self, obj, ctx: FeatureContext):
        raise NotImplementedError

    def build_editor(self, obj, ctx: FeatureContext) -> FeatureEditor:
        editor = FeatureEditor()
        form = QFormLayout(editor)
        form.setContentsMargins(0, 0, 0, 0)
        hint = QLabel(self.description)
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666;")
        form.addRow(hint)
        return editor


def _hint(text):
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet("color: #666;")
    return label


# ---------------------------------------------------------------------------

class ControllableFeature(ObjectFeature):
    key = "controllable"
    title = "Controllable"
    description = "Can be selected and driven from the Command panel (jog, target, gamepad)."

    def is_present(self, obj):
        return obj.controllable

    def add(self, obj, ctx):
        obj.controllable = True
        ctx.object_service.notify_object_changed(obj)
        ctx.object_service.objects_changed.emit()  # refresh "controlled object" lists

    def remove(self, obj, ctx):
        obj.controllable = False
        if ctx.object_service.get_controlled_object() is obj:
            ctx.object_service.clear_controlled_object()
        ctx.object_service.notify_object_changed(obj)
        ctx.object_service.objects_changed.emit()


# ---------------------------------------------------------------------------

class _MotionCaptureEditor(FeatureEditor):
    def __init__(self, obj, ctx: FeatureContext):
        super().__init__()
        self.obj, self.ctx = obj, ctx
        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)

        self.subject_combo = QComboBox()
        self.subject_combo.setEditable(True)
        self.subject_combo.setToolTip("Vicon object / OptiTrack rigid body name")
        self.subject_combo.lineEdit().editingFinished.connect(self._on_subject_edited)
        self.subject_combo.activated.connect(lambda _i: self._on_subject_edited())
        form.addRow("Subject:", self.subject_combo)

        self.follow_check = QCheckBox("Follow subject")
        self.follow_check.toggled.connect(self._on_follow_toggled)
        self.lock_check = QCheckBox("Lock pose")
        self.lock_check.setToolTip("Keep the current pose and ignore incoming mocap")
        self.lock_check.toggled.connect(self._on_lock_toggled)
        form.addRow(self.follow_check, self.lock_check)

        self.status_label = QLabel()
        form.addRow("Status:", self.status_label)
        self._known_subjects = []
        self.refresh()

    def _subjects(self):
        service = self.ctx.motion_capture_service
        return [s.name for s in service.subjects_snapshot()] if service else []

    def refresh(self):
        subjects = self._subjects()
        if subjects != self._known_subjects and not self.subject_combo.hasFocus():
            self._known_subjects = subjects
            self.subject_combo.blockSignals(True)
            self.subject_combo.clear()
            self.subject_combo.addItems(subjects)
            self.subject_combo.blockSignals(False)
        if not self.subject_combo.hasFocus():
            self.subject_combo.setEditText(self.obj.tracking_id or "")
        for check, value in ((self.follow_check, self.obj.tracked), (self.lock_check, self.obj.pose_locked)):
            check.blockSignals(True)
            check.setChecked(value)
            check.blockSignals(False)

        age = self.obj.tracking_age()
        if not self.obj.tracked:
            text, colour = "Not following", "#666"
        elif age is None:
            text, colour = "Waiting for this subject", "#b36b00"
        elif age > 1.0:
            text, colour = f"Lost ({age:.0f} s ago)", "#c82333"
        else:
            text, colour = ("Receiving (pose locked)" if self.obj.pose_locked else "Receiving"), "#1e7e34"
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {colour};")

    def _on_subject_edited(self):
        subject = self.subject_combo.currentText().strip()
        if subject and subject != self.obj.tracking_id:
            self.obj.set_tracked(self.obj.tracked, subject)
            self.ctx.object_service.notify_object_changed(self.obj)

    def _on_follow_toggled(self, checked):
        if checked and not self.obj.tracking_id:
            self.follow_check.setChecked(False)
            return
        self.obj.tracked = checked
        self.ctx.object_service.notify_object_changed(self.obj)

    def _on_lock_toggled(self, checked):
        self.obj.pose_locked = checked
        self.ctx.object_service.notify_object_changed(self.obj)


class MotionCaptureFeature(ObjectFeature):
    key = "motion_capture"
    title = "Motion capture"
    description = "Follows a Vicon/OptiTrack subject."

    def is_present(self, obj):
        return obj.tracking_id is not None

    def add(self, obj, ctx):
        # Default to a subject with the object's name, which is the usual convention.
        obj.set_tracked(True, obj.tracking_id or obj.name)
        ctx.object_service.notify_object_changed(obj)

    def remove(self, obj, ctx):
        obj.tracked = False
        obj.tracking_id = None
        obj.pose_locked = False
        obj.last_tracking_update = None
        ctx.object_service.notify_object_changed(obj)

    def build_editor(self, obj, ctx):
        return _MotionCaptureEditor(obj, ctx)


# ---------------------------------------------------------------------------

class _MavlinkEditor(FeatureEditor):
    NONE = "— not linked —"

    def __init__(self, obj, ctx: FeatureContext):
        super().__init__()
        self.obj, self.ctx = obj, ctx
        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)

        self.connection_combo = QComboBox()
        self.connection_combo.activated.connect(self._on_connection_chosen)
        form.addRow("Connection:", self.connection_combo)

        self.send_mocap_check = QCheckBox("Send pose to the vehicle as mocap")
        self.send_mocap_check.toggled.connect(self._on_send_mocap_toggled)
        form.addRow(self.send_mocap_check)

        self.status_label = QLabel()
        form.addRow("Status:", self.status_label)
        if ctx.mavlink_service is None:
            form.addRow(_hint("MAVLink service unavailable."))
        self._names = None
        self.refresh()

    def refresh(self):
        service = self.ctx.mavlink_service
        cfg = self.obj.mavlink_config
        names = service.get_available_connection_names() if service else []
        if names != self._names and not self.connection_combo.view().isVisible():
            self._names = names
            self.connection_combo.blockSignals(True)
            self.connection_combo.clear()
            self.connection_combo.addItem(self.NONE, "")
            for name in names:
                self.connection_combo.addItem(name, name)
            self.connection_combo.blockSignals(False)
        index = self.connection_combo.findData(cfg.linked_connection_name)
        if index < 0 and cfg.linked_connection_name:  # linked to a connection that no longer exists
            self.connection_combo.addItem(cfg.linked_connection_name, cfg.linked_connection_name)
            index = self.connection_combo.count() - 1
        self.connection_combo.setCurrentIndex(max(0, index))

        self.send_mocap_check.blockSignals(True)
        self.send_mocap_check.setChecked(cfg.send_mocap)
        self.send_mocap_check.blockSignals(False)

        if not cfg.linked_connection_name:
            text, colour = "Not linked to a connection", "#666"
        else:
            conn = service.get_connection_by_name(cfg.linked_connection_name) if service else None
            if conn is None or not conn.is_connected:
                text, colour = f"{cfg.linked_connection_name} is not connected", "#b36b00"
            elif cfg.send_mocap:
                text, colour = f"Streaming mocap to {cfg.linked_connection_name}", "#1e7e34"
            else:
                text, colour = f"Linked to {cfg.linked_connection_name}", "#1e7e34"
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {colour};")

    def _on_connection_chosen(self, index):
        service = self.ctx.mavlink_service
        if service is None:
            return
        name = self.connection_combo.itemData(index)
        if name:
            service.link_object(self.obj, name)
        else:
            service.unlink_object(self.obj)
        self.ctx.object_service.notify_object_changed(self.obj)

    def _on_send_mocap_toggled(self, checked):
        self.obj.mavlink_config.send_mocap = checked
        if self.ctx.mavlink_service is not None:
            self.ctx.mavlink_service.update_object_config(self.obj, self.obj.mavlink_config)
        self.ctx.object_service.notify_object_changed(self.obj)


class MavlinkFeature(ObjectFeature):
    key = "mavlink"
    title = "MAVLink vehicle"
    description = "Linked to a PX4 vehicle connection."

    def is_present(self, obj):
        return obj.mavlink_config.enabled

    def add(self, obj, ctx):
        obj.mavlink_config.enabled = True
        if ctx.mavlink_service is not None:
            ctx.mavlink_service.update_object_config(obj, obj.mavlink_config)
        ctx.object_service.notify_object_changed(obj)

    def remove(self, obj, ctx):
        if ctx.mavlink_service is not None:
            ctx.mavlink_service.unlink_object(obj, disable=True)
        else:
            obj.mavlink_config.enabled = False
            obj.mavlink_config.linked_connection_name = ""
        ctx.object_service.notify_object_changed(obj)

    def build_editor(self, obj, ctx):
        return _MavlinkEditor(obj, ctx)


FEATURES = [ControllableFeature(), MotionCaptureFeature(), MavlinkFeature()]
