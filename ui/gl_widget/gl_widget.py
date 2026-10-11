import time

from PyQt5.QtCore import QTimer, Qt, pyqtSignal
from PyQt5.QtWidgets import QLabel, QOpenGLWidget

from models.cad_mesh import CadMesh
from models.rect_prism import RectPrism
from models.grid import Grid
from models.axes import Axes
from ui.gl_widget.scene_renderer import Camera, SceneRenderer


class GLWidget(QOpenGLWidget):
    # Base zoom speed factor for mouse wheel zoom
    BASE_ZOOM_SPEED = 0.001
    HUD_REFRESH_MS = 250

    # Signal emitted when camera is reset (for UI synchronization)
    camera_reset = pyqtSignal()

    def __init__(self, object_service, parent=None):
        super().__init__(parent)
        self.setMinimumSize(800, 600)
        self.setFocusPolicy(Qt.StrongFocus)  # Enable keyboard focus

        self.object_service = object_service
        self.input_service = None  # Will be set by MainWindow
        self.renderer = SceneRenderer()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(16)  # Update approximately every 16 milliseconds (about 60 FPS)

        self.prev_time = time.perf_counter()
        self.fps = 0.0

        grid = Grid(name="Grid", colour=(0.68, 0.68, 0.68, 1.0))
        axes = Axes(name="Axes")

        red_cube = RectPrism(name="Red Cube", colour=(1.0, 0.0, 0.0))
        green_cube = RectPrism(name="Green Cube", colour=(0.0, 1.0, 0.0))
        green_cube.set_pose((2.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0))

        blue_cube = RectPrism(name="Blue Cube", colour=(0.0, 0.0, 1.0, 0.5))
        blue_cube.set_pose((0.0, 0.0, 2.0, 1.0, 0.0, 0.0, 0.0))

        quad = CadMesh("cad_files/basic_quadcopter.stl", scale=0.05, colour=(0.5, 0.9, 0.5))

        self.object_service.add_object(grid)
        self.object_service.add_object(axes)
        self.object_service.add_object(red_cube)
        self.object_service.add_object(green_cube)
        self.object_service.add_object(blue_cube)
        self.object_service.add_object(quad)

        # Camera parameters
        self.camera_distance = 10.0
        self.camera_angle_x = 30.0
        self.camera_angle_y = 45.0
        self.mouse_last_x = 0
        self.mouse_last_y = 0
        self.mouse_left_button_down = False

        # Zoom constraints
        self.camera_distance_min = 2.0
        self.camera_distance_max = 50.0
        self.zoom_sensitivity = 1.0

        # Object lock feature - camera follows and orbits around this object
        self.locked_object = None

        # Heads-up readout (FPS / camera). A Qt overlay rather than GL text, so
        # no GLUT and no interference with GL state.
        self.hud_label = QLabel(self)
        self.hud_label.setObjectName("ViewportHud")
        self.hud_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.hud_label.setStyleSheet(
            "QLabel#ViewportHud { background: rgba(255, 255, 255, 170); color: #222;"
            " border-radius: 6px; padding: 4px 8px; font-family: monospace; }")
        self.hud_label.move(10, 10)
        self._hud_timer = QTimer(self)
        self._hud_timer.timeout.connect(self._update_hud)
        self._hud_timer.start(self.HUD_REFRESH_MS)
        self._update_hud()

    def camera(self) -> Camera:
        """The current view as a renderer camera (follows the locked object)."""
        target = (0.0, 0.0, 0.0)
        if self.locked_object is not None and len(getattr(self.locked_object, "pose", ())) >= 3:
            target = tuple(self.locked_object.pose[:3])
        return Camera(distance=self.camera_distance, angle_x=self.camera_angle_x,
                      angle_y=self.camera_angle_y, target=target)

    def initializeGL(self):
        self.renderer.initialize()

    def paintGL(self):
        now = time.perf_counter()
        delta = now - self.prev_time
        self.prev_time = now
        if delta > 0:
            # Smooth so the readout is legible.
            self.fps = 0.9 * self.fps + 0.1 * (1.0 / delta) if self.fps else 1.0 / delta

        self.renderer.render(self.object_service.get_objects(), self.camera(),
                             self.width(), self.height())

    def _update_hud(self):
        self.hud_label.setText(
            f"FPS {self.fps:5.1f}   Cam {self.camera_angle_x:5.1f}° / {self.camera_angle_y:6.1f}°")
        self.hud_label.adjustSize()

    def resizeGL(self, width, height):
        pass  # QOpenGLWidget sets the viewport before each paintGL

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.mouse_left_button_down = True
            self.mouse_last_x = event.x()
            self.mouse_last_y = event.y()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.mouse_left_button_down = False

    def mouseMoveEvent(self, event):
        if self.mouse_left_button_down:
            dx = event.x() - self.mouse_last_x
            dy = event.y() - self.mouse_last_y
            self.camera_angle_y -= dx * 0.5
            self.camera_angle_x += dy * 0.5
            self.camera_angle_x = max(-90.0, min(90.0, self.camera_angle_x))
            self.mouse_last_x = event.x()
            self.mouse_last_y = event.y()

    def wheelEvent(self, event):
        """Handle mouse wheel events for zooming in/out."""
        delta = event.angleDelta().y()
        zoom_factor = self.BASE_ZOOM_SPEED * self.zoom_sensitivity

        # Proportional zoom: faster when far, slower when close for smooth control
        self.camera_distance -= delta * zoom_factor * self.camera_distance

        # Clamp to min/max zoom levels
        self.camera_distance = max(self.camera_distance_min,
                                   min(self.camera_distance_max, self.camera_distance))
        self.update()

    def keyPressEvent(self, event):
        """Handle key press events and forward to input service"""
        if self.input_service:
            self.input_service.handle_key_press(event.key())
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        """Handle key release events and forward to input service"""
        if self.input_service:
            self.input_service.handle_key_release(event.key())
        super().keyReleaseEvent(event)

    def set_input_service(self, input_service):
        """Set the input service for this widget"""
        self.input_service = input_service

    def set_zoom_sensitivity(self, sensitivity):
        """Set the zoom sensitivity for mouse wheel zoom.

        Args:
            sensitivity: Zoom sensitivity multiplier (default 1.0)
        """
        self.zoom_sensitivity = sensitivity

    def reset_camera(self):
        """Reset camera to default position, zoom level, and clear object lock.

        Emits camera_reset signal for UI synchronization.
        """
        self.camera_distance = 10.0
        self.camera_angle_x = 30.0
        self.camera_angle_y = 45.0
        self.zoom_sensitivity = 1.0
        self.locked_object = None
        self.camera_reset.emit()
        self.update()

    def set_locked_object(self, obj):
        """Set the object to lock the camera view onto.

        When locked, the camera will orbit around this object and follow it
        as it moves. Set to None to unlock and return to orbiting around origin.

        Args:
            obj: SceneObject to lock onto, or None to unlock
        """
        self.locked_object = obj
        self.update()

    def get_locked_object(self):
        """Get the currently locked object.

        Returns:
            The locked SceneObject, or None if not locked
        """
        return self.locked_object
