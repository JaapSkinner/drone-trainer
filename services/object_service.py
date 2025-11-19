import numpy as np
import pygame
from PyQt5.QtCore import pyqtSignal, pyqtSlot

from models.debug_text import DebugText
from models.scene_object import SceneObject
from services.joystick_service import JoystickService
from services.service_base import ServiceBase,DebugLevel,ServiceLevel  # your base service
from models.structs import PositionData
from PyQt5.QtCore import QTimer

class ObjectService(ServiceBase):
    def __init__(self, joystick_service: JoystickService = None, debug_level=None):
        if debug_level is None:
            debug_level = DebugLevel.LOG
        print(f"ObjectService initialized with debug level: {debug_level}")
        print(f"instance of DebugLevel: {isinstance(debug_level, DebugLevel)}")
        super().__init__(debug_level=debug_level)

        self.objects: list[SceneObject] = []
        self.controlled_object = None
        self.joystick_service = joystick_service

        self.debug_count = 0

    def on_start(self):
        pass

    def on_stop(self):
        pass

    def load_input_service(self, joystick_service: JoystickService):
        self.joystick_service = joystick_service
        self.set_controlled_object(obj=self.controlled_object)

    def update_debug_text(self, name: str, value: float, dimensions: tuple = None):
        """Update or create a debug text object."""
        debug_text = self.get_object(name)
        if debug_text is None:
            debug_text = DebugText(name=name, text=name, colour=(0.0, 0.0, 0.0, 1.0), dimensions=dimensions)
            self.add_object(debug_text)

        debug_text.update(value, dimensions)
        self.status_changed.emit(ServiceLevel.RUNNING.value, f"Debug text {name} updated to {value}.")

    def add_object(self, obj):
        if obj not in self.objects:
            if isinstance(obj, DebugText):
                self.debug_count += 1
                obj.set_offset((obj.offset[0], obj.offset[1], self.debug_count * 20))  # Offset debug text to a new line

            self.objects.append(obj)
            self.status_changed.emit(ServiceLevel.RUNNING.value, f"Object {obj.name} added.")


            # Sort objects by their colour's alpha channel (4th element in the tuple)
            self.objects.sort(key=lambda obj: obj.colour[3], reverse=True)
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
            self.controlled_object = obj

            if self.joystick_service:
                self.joystick_service.set_controlled_object(obj)

            self.status_changed.emit(ServiceLevel.RUNNING.value, f"Controlled object set to {obj.name}.")


    def draw_objects(self):
        for obj in self.objects:
            obj.draw()

    def update(self):
        pass