"""Owner of every scene object.

All code that needs scene objects goes through this service. Structural
changes (add / remove / rename / property edits) emit signals so panels can
refresh; pose changes do not (they happen at mocap/input rates — read poses
when you draw or on a display timer instead).

Lives on the GUI thread: it is never started as a threaded service, because
widgets and the renderer read its objects directly.
"""
import time
from typing import Dict, Iterable, List, Optional

from PyQt5.QtCore import pyqtSignal

from models.scene_object import SceneObject
from services.service_base import DebugLevel, ServiceBase, ServiceLevel


class ObjectService(ServiceBase):
    object_added = pyqtSignal(object)
    object_removed = pyqtSignal(object)
    object_changed = pyqtSignal(object)        # a property other than pose changed
    objects_changed = pyqtSignal()             # anything structural (add/remove/rename/clear)
    controlled_object_changed = pyqtSignal(object)  # SceneObject or None

    def __init__(self, input_service=None, debug_level=None):
        super().__init__(debug_level=debug_level or DebugLevel.LOG)
        self.objects: List[SceneObject] = []
        self.controlled_object = None
        self.input_service = input_service

    def on_start(self):
        pass

    def on_stop(self):
        pass

    def update(self):
        pass

    def load_input_service(self, input_service):
        self.input_service = input_service
        if self.input_service:
            self.input_service.set_controlled_object(self.controlled_object)

    # ------------------------------------------------------------------
    # Collection
    # ------------------------------------------------------------------

    def unique_name(self, base: str, exclude: SceneObject = None) -> str:
        """``base`` if no other object uses it, else ``base 2``, ``base 3`` …"""
        taken = {o.name for o in self.objects if o is not exclude}
        if base not in taken:
            return base
        n = 2
        while f"{base} {n}" in taken:
            n += 1
        return f"{base} {n}"

    def add_object(self, obj: SceneObject) -> SceneObject:
        """Add an object, renaming it if its name is already taken."""
        if obj in self.objects:
            self.status_changed.emit(ServiceLevel.WARNING.value, f"Object {obj.name} already exists.")
            return obj
        obj.name = self.unique_name(obj.name)
        self.objects.append(obj)
        self.status_changed.emit(ServiceLevel.RUNNING.value, f"Object {obj.name} added.")
        self.object_added.emit(obj)
        self.objects_changed.emit()
        return obj

    def add_objects(self, objects: Iterable[SceneObject]):
        for obj in objects:
            self.add_object(obj)

    def remove_object(self, name: str = "", obj: SceneObject = None) -> bool:
        if obj is None:
            obj = self.get_object(name) if name else None
        if obj is None or obj not in self.objects:
            self.status_changed.emit(ServiceLevel.WARNING.value, f"Object {name or obj} not found.")
            return False

        self.objects.remove(obj)
        obj.release_gl()
        if obj is self.controlled_object:
            self.clear_controlled_object()
        self.status_changed.emit(ServiceLevel.RUNNING.value, f"Object {obj.name} removed.")
        self.object_removed.emit(obj)
        self.objects_changed.emit()
        return True

    def clear_objects(self, keep=None):
        """Remove every object, except those for which ``keep(obj)`` is true."""
        for obj in list(self.objects):
            if keep is None or not keep(obj):
                self.remove_object(obj=obj)

    def rename_object(self, obj: SceneObject, new_name: str) -> str:
        """Rename an object (made unique if needed). Returns the name used."""
        new_name = (new_name or "").strip() or obj.name
        obj.name = self.unique_name(new_name, exclude=obj)
        self.notify_object_changed(obj)
        self.objects_changed.emit()
        return obj.name

    def notify_object_changed(self, obj: SceneObject):
        """Call after editing an object's properties (colour, flags, tracking …)."""
        self.object_changed.emit(obj)

    def get_objects(self) -> List[SceneObject]:
        return self.objects

    def get_object(self, name) -> Optional[SceneObject]:
        for obj in self.objects:
            if obj.name == name:
                return obj
        return None

    def get_tracked_objects(self) -> List[SceneObject]:
        return [o for o in self.objects if o.tracked and o.tracking_id]

    # ------------------------------------------------------------------
    # Motion capture
    # ------------------------------------------------------------------

    def apply_tracking_poses(self, poses: Dict[str, tuple]) -> int:
        """Move tracked objects to the latest mocap poses.

        ``poses`` maps mocap subject names to scene poses. Objects whose
        ``tracking_id`` matches are updated unless their pose is locked.
        Returns the number of objects moved.
        """
        now = time.monotonic()
        moved = 0
        for obj in self.objects:
            if not obj.tracked or not obj.tracking_id:
                continue
            pose = poses.get(obj.tracking_id)
            if pose is None:
                continue
            obj.last_tracking_update = now
            if not obj.pose_locked:
                obj.set_pose(pose)
                moved += 1
        return moved

    # ------------------------------------------------------------------
    # Controlled object
    # ------------------------------------------------------------------

    def get_controlled_object(self):
        return self.controlled_object

    def set_controlled_object(self, name: str = "", obj: SceneObject = None) -> None:
        if obj is None:
            obj = self.get_object(name) if name else None
        if not isinstance(obj, SceneObject):
            self.status_changed.emit(ServiceLevel.WARNING.value, "No object provided or found by name.")
            return

        if not obj.controllable:
            self.status_changed.emit(ServiceLevel.WARNING.value, "Object is not controllable.")
            return

        self.controlled_object = obj
        if self.input_service:
            self.input_service.set_controlled_object(obj)
        self.status_changed.emit(ServiceLevel.RUNNING.value, f"Controlled object set to {obj.name}.")
        self.controlled_object_changed.emit(obj)

    def clear_controlled_object(self) -> None:
        """Clear the currently controlled object."""
        self.controlled_object = None
        if self.input_service:
            self.input_service.set_controlled_object(None)
        self.status_changed.emit(ServiceLevel.RUNNING.value, "Controlled object cleared.")
        self.controlled_object_changed.emit(None)

    def draw_objects(self):
        for obj in self.objects:
            obj.draw()
