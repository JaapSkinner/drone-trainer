from PyQt5.QtCore import pyqtSignal, pyqtSlot

from models.scene_object import SceneObject
from services.service_base import ServiceBase,DebugLevel,ServiceLevel  # your base service
from models.structs import PositionData
from PyQt5.QtCore import QTimer

class ObjectService(ServiceBase):
    def __init__(self, input_service=None, debug_level=None):
        if debug_level is None:
            debug_level = DebugLevel.LOG
        print(f"ObjectService initialized with debug level: {debug_level}")
        print(f"instance of DebugLevel: {isinstance(debug_level, DebugLevel)}")
        super().__init__(debug_level=debug_level)

        self.objects: list[SceneObject] = []
        self.controlled_object = None
        self.input_service = input_service


    def on_start(self):
        pass

    def on_stop(self):
        pass

    def load_input_service(self, input_service):
        self.input_service = input_service
        self.set_controlled_object(obj=self.controlled_object)

    def add_object(self, obj):
        if obj not in self.objects:
            self.objects.append(obj)
            self.status_changed.emit(ServiceLevel.RUNNING.value, f"Object {obj.name} added.")
        else:
            self.status_changed.emit(ServiceLevel.WARNING.value, f"Object {obj.name} already exists.")

    def remove_object(self, name: str = "", obj: SceneObject = None) -> None:
        if obj is None:
            if name:
                obj = self.get_object(name)
            else:
                self.status_changed.emit(ServiceLevel.WARNING.value, "No object provided or found by name.")
                return

        if obj in self.objects:
            self.objects.remove(obj)
            obj.release_gl()
            self.status_changed.emit(ServiceLevel.RUNNING.value, f"Object {obj.name} removed.")
        else:
            self.status_changed.emit(ServiceLevel.WARNING.value, f"Object {obj.name} not found.")

    def get_objects(self):
        return self.objects

    def get_object(self, name):
        for obj in self.objects:
            if obj.name == name:
                return obj
        self.status_changed.emit(ServiceLevel.WARNING.value, f"Object {name} not found.")
        return None

    def get_controlled_object(self):
        if self.controlled_object:
            return self.controlled_object
        else:
            self.status_changed.emit(ServiceLevel.WARNING.value, "No controlled object set.")
            return None

    def set_controlled_object(self, name: str = "", obj: SceneObject = None) -> None:
        if obj is None:
            if name:
                obj = self.get_object(name)
            else:
                self.status_changed.emit(ServiceLevel.WARNING.value, "No object provided or found by name.")
                return

        if isinstance(obj, SceneObject):
            self.controlled_object = obj if obj.controllable else None


            if self.input_service:
                self.input_service.set_controlled_object(obj)

            if not obj.controllable:
                self.status_changed.emit(ServiceLevel.WARNING.value, "Object is not controllable.")

            self.status_changed.emit(ServiceLevel.RUNNING.value, f"Controlled object set to {obj.name}.")

    def clear_controlled_object(self) -> None:
        """Clear the currently controlled object."""
        self.controlled_object = None
        if self.input_service:
            self.input_service.set_controlled_object(None)
        self.status_changed.emit(ServiceLevel.RUNNING.value, "Controlled object cleared.")


    def draw_objects(self):
        for obj in self.objects:
            obj.draw()

    def update(self):
        pass