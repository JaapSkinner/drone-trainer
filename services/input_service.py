"""
Input Service for handling various input devices (Controllers, Keyboards, etc.)
Refactored from JoystickService to support multiple input types.
"""
import numpy as np
import pygame
from PyQt5.QtCore import pyqtSignal, Qt
from services.service_base import ServiceBase, DebugLevel, ServiceLevel
from PyQt5.QtCore import QTimer
from enum import Enum


class InputType(Enum):
    """Enumeration of supported input types"""
    CONTROLLER = "Controller"
    WASD = "WASD"
    ARROW_KEYS = "Arrow Keys"


class InputService(ServiceBase):
    """
    Generic input service that handles multiple input types:
    - Controller/Gamepad (Xbox, PlayStation, etc.)
    - WASD keyboard input
    - Arrow Keys keyboard input
    """
    input_updated = pyqtSignal(object)  # emits the updated object state

    def __init__(self, gl_widget, input_type=InputType.CONTROLLER, 
                 sensitivity=1.0, update_interval_ms=16, debug_level=None):
        """
        Initialize the input service.
        
        Args:
            gl_widget: The GL widget for camera angle access
            input_type: Type of input device (Controller, WASD, Arrow Keys)
            sensitivity: Input sensitivity multiplier (0.1 to 5.0)
            update_interval_ms: Update interval in milliseconds
            debug_level: Debug level for error handling
        """
        super().__init__(debug_level=debug_level or DebugLevel.LOG)
        self.gl_widget = gl_widget
        self.update_interval = update_interval_ms
        self.input_type = input_type
        self.sensitivity = max(0.1, min(5.0, sensitivity))  # Clamp between 0.1 and 5.0
        
        # Controller-specific attributes
        self.joystick = None
        
        # Keyboard-specific attributes
        self.key_states = {
            # WASD keys
            Qt.Key_W: False, Qt.Key_S: False, Qt.Key_A: False, Qt.Key_D: False,
            Qt.Key_Q: False, Qt.Key_E: False,  # Up/Down
            Qt.Key_R: False, Qt.Key_F: False,  # Rotation
            # Arrow keys
            Qt.Key_Up: False, Qt.Key_Down: False, Qt.Key_Left: False, Qt.Key_Right: False,
            Qt.Key_PageUp: False, Qt.Key_PageDown: False,  # Up/Down
            Qt.Key_Home: False, Qt.Key_End: False,  # Rotation
        }
        
        self.controlled_object = None
        self.timer = None
    
    @staticmethod
    def _apply_deadzone(value, threshold=0.1):
        """
        Apply deadzone to input value to filter out small unintentional movements.
        
        Args:
            value: Input value to filter
            threshold: Deadzone threshold (default 0.1)
            
        Returns:
            Filtered value (0 if within deadzone, otherwise original value)
        """
        return value if abs(value) > threshold else 0

    def on_start(self):
        """Initialize the input service based on input type"""
        if self.input_type == InputType.CONTROLLER:
            self._init_controller()
        else:
            # For keyboard input, we just need to set up the status
            self.status_label = f"{self.input_type.value}"
            self.status = ServiceLevel.RUNNING

        self.timer = QTimer()
        self.timer.timeout.connect(self.safe(self.update))
        self.timer.start(self.update_interval)

    def _init_controller(self):
        """Initialize pygame for controller input"""
        pygame.init()
        pygame.joystick.init()
        if pygame.joystick.get_count() > 0:
            self.joystick = pygame.joystick.Joystick(0)
            self.joystick.init()
            self.status_label = f"{self.input_type.value}: {self.joystick.get_name()}"
            self.status = ServiceLevel.RUNNING
        else:
            self.joystick = None
            self.status_label = f"{self.input_type.value}: Not Found"
            self.status = ServiceLevel.STOPPED

    def on_stop(self):
        """Clean up resources"""
        if self.timer:
            self.timer.stop()
            self.timer.deleteLater()
            self.timer = None
        if self.input_type == InputType.CONTROLLER:
            pygame.quit()

    def set_input_type(self, input_type: InputType):
        """
        Change the input type.
        
        Args:
            input_type: New input type to use
        """
        if self.input_type != input_type:
            # Clean up old input type
            if self.input_type == InputType.CONTROLLER:
                pygame.quit()
            
            self.input_type = input_type
            
            # Initialize new input type
            if input_type == InputType.CONTROLLER:
                self._init_controller()
            else:
                self.status_label = f"{input_type.value}"
                self.status = ServiceLevel.RUNNING

    def set_sensitivity(self, sensitivity: float):
        """
        Set input sensitivity.
        
        Args:
            sensitivity: Sensitivity multiplier (0.1 to 5.0)
        """
        self.sensitivity = max(0.1, min(5.0, sensitivity))

    def handle_key_press(self, key):
        """
        Handle key press events from the GL widget.
        
        Args:
            key: Qt key code
        """
        if key in self.key_states:
            self.key_states[key] = True

    def handle_key_release(self, key):
        """
        Handle key release events from the GL widget.
        
        Args:
            key: Qt key code
        """
        if key in self.key_states:
            self.key_states[key] = False

    def update(self):
        """Update input and control the object based on input type"""
        if self.input_type == InputType.CONTROLLER:
            self._update_controller()
        elif self.input_type == InputType.WASD:
            self._update_keyboard_wasd()
        elif self.input_type == InputType.ARROW_KEYS:
            self._update_keyboard_arrows()

    def _update_controller(self):
        """Update controller input (original joystick logic)"""
        if not self.joystick or not self.joystick.get_init():
            # No joystick connected or joystick was disconnected, check for new connection
            pygame.joystick.quit()
            pygame.joystick.init()
            if pygame.joystick.get_count() > 0:
                self.joystick = pygame.joystick.Joystick(0)
                self.joystick.init()
                self.status_label = f"{self.input_type.value}: {self.joystick.get_name()}"
                self.status = ServiceLevel.RUNNING
            else:
                self.joystick = None
                self.status_label = f"{self.input_type.value}: Not Found"
                self.status = ServiceLevel.STOPPED
            return
        elif self.joystick.get_id() >= pygame.joystick.get_count():
            # Joystick was disconnected
            self.joystick = None
            self.status_label = f"{self.input_type.value}: Disconnected"
            self.status = ServiceLevel.STOPPED
            return
        
        pygame.event.pump()

        # read camera angles from gl_widget and rotate joystick axes accordingly
        cam_angle_x = self.gl_widget.camera_angle_x
        cam_angle_y = self.gl_widget.camera_angle_y
        
        # Adjust joystick axes based on camera angles
        lx = self._apply_deadzone(self.joystick.get_axis(0)) * np.cos(np.radians(cam_angle_y)) + self._apply_deadzone(self.joystick.get_axis(1)) * np.sin(np.radians(cam_angle_y))
        ly = -(self._apply_deadzone(self.joystick.get_axis(0)) * np.sin(np.radians(cam_angle_y))) + self._apply_deadzone(self.joystick.get_axis(1)) * np.cos(np.radians(cam_angle_y))
        rx = self._apply_deadzone(self.joystick.get_axis(3))
        ry = self._apply_deadzone(self.joystick.get_axis(4)) 
        rz = self._apply_deadzone(((self.joystick.get_axis(5) + 1) / 2) - ((self.joystick.get_axis(2) + 1) / 2))  # RT - LT, normalized to [-1, 1]
        lb = self.joystick.get_button(4)
        rb = self.joystick.get_button(5)

        obj = self.controlled_object
        if obj is not None:
            obj.set_pose_delta([lx * 0.1 * self.sensitivity,
                                (rb - lb) * 0.1 * self.sensitivity,
                                ly * 0.1 * self.sensitivity, 0, 0, 0, 0])
            obj.set_pose([obj.pose[0] + obj.pose_delta[0],
                          obj.pose[1] + obj.pose_delta[1],
                          obj.pose[2] + obj.pose_delta[2],
                          1, ry * 0.03 * self.sensitivity, -rz * 0.03 * self.sensitivity, -rx * 0.03 * self.sensitivity])
            
            self.input_updated.emit(obj)

    def _update_keyboard_wasd(self):
        """Update WASD keyboard input"""
        if self.controlled_object is None:
            return

        # Read camera angles from gl_widget
        cam_angle_x = self.gl_widget.camera_angle_x
        cam_angle_y = self.gl_widget.camera_angle_y
        
        # Calculate movement based on key states
        forward = -1.0 if self.key_states[Qt.Key_W] else (1.0 if self.key_states[Qt.Key_S] else 0.0)
        strafe = -1.0 if self.key_states[Qt.Key_A] else (1.0 if self.key_states[Qt.Key_D] else 0.0)
        vertical = 1.0 if self.key_states[Qt.Key_Q] else (-1.0 if self.key_states[Qt.Key_E] else 0.0)
        
        # Rotation controls
        rot_x = 1.0 if self.key_states[Qt.Key_R] else (-1.0 if self.key_states[Qt.Key_F] else 0.0)
        
        # Apply camera rotation to movement
        lx = strafe * np.cos(np.radians(cam_angle_y)) + forward * np.sin(np.radians(cam_angle_y))
        ly = -strafe * np.sin(np.radians(cam_angle_y)) + forward * np.cos(np.radians(cam_angle_y))
        
        obj = self.controlled_object
        obj.set_pose_delta([lx * 0.1 * self.sensitivity,
                            vertical * 0.1 * self.sensitivity,
                            ly * 0.1 * self.sensitivity, 0, 0, 0, 0])
        obj.set_pose([obj.pose[0] + obj.pose_delta[0],
                      obj.pose[1] + obj.pose_delta[1],
                      obj.pose[2] + obj.pose_delta[2],
                      1, 0, 0, -rot_x * 0.03 * self.sensitivity])
        
        self.input_updated.emit(obj)

    def _update_keyboard_arrows(self):
        """Update Arrow Keys keyboard input"""
        if self.controlled_object is None:
            return

        # Read camera angles from gl_widget
        cam_angle_x = self.gl_widget.camera_angle_x
        cam_angle_y = self.gl_widget.camera_angle_y
        
        # Calculate movement based on key states
        forward = -1.0 if self.key_states[Qt.Key_Up] else (1.0 if self.key_states[Qt.Key_Down] else 0.0)
        strafe = -1.0 if self.key_states[Qt.Key_Left] else (1.0 if self.key_states[Qt.Key_Right] else 0.0)
        vertical = 1.0 if self.key_states[Qt.Key_PageUp] else (-1.0 if self.key_states[Qt.Key_PageDown] else 0.0)
        
        # Rotation controls
        rot_x = 1.0 if self.key_states[Qt.Key_Home] else (-1.0 if self.key_states[Qt.Key_End] else 0.0)
        
        # Apply camera rotation to movement
        lx = strafe * np.cos(np.radians(cam_angle_y)) + forward * np.sin(np.radians(cam_angle_y))
        ly = -strafe * np.sin(np.radians(cam_angle_y)) + forward * np.cos(np.radians(cam_angle_y))
        
        obj = self.controlled_object
        obj.set_pose_delta([lx * 0.1 * self.sensitivity,
                            vertical * 0.1 * self.sensitivity,
                            ly * 0.1 * self.sensitivity, 0, 0, 0, 0])
        obj.set_pose([obj.pose[0] + obj.pose_delta[0],
                      obj.pose[1] + obj.pose_delta[1],
                      obj.pose[2] + obj.pose_delta[2],
                      1, 0, 0, -rot_x * 0.03 * self.sensitivity])
        
        self.input_updated.emit(obj)

    def set_controlled_object(self, obj):
        """
        Set the object to be controlled by this input service.
        
        Args:
            obj: The scene object to control
        """
        self.controlled_object = obj
