import time

from PyQt5.QtCore import QPoint, QTimer, Qt, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QSurfaceFormat
from PyQt5.QtWidgets import QLabel, QOpenGLWidget

from models import grid, picking
from models.grid import Grid
from ui import theme
from ui.gl_widget.ground_overlay import GroundOverlay

from ui.gl_widget.scene_renderer import Camera, SceneRenderer


class GLWidget(QOpenGLWidget):
    # Base zoom speed factor for mouse wheel zoom
    BASE_ZOOM_SPEED = 0.001
    HUD_REFRESH_MS = 250
    MSAA_SAMPLES = 4   # multisample antialiasing: smooth edges and lines
    CLICK_SLOP_PX = 4  # a press that moves less than this before release is a click, not an orbit
    HOVER_PICK_MS = 40
    SELECTED_RIM = 0.9
    HOVER_RIM = 0.45

    # Signal emitted when camera is reset (for UI synchronization)
    camera_reset = pyqtSignal()
    # Mouse on objects (object or None for empty space)
    object_clicked = pyqtSignal(object)
    object_double_clicked = pyqtSignal(object)
    object_context_menu = pyqtSignal(object, QPoint)   # object (or None), global position

    def __init__(self, object_service, parent=None):
        super().__init__(parent)
        surface = QSurfaceFormat(self.format())
        surface.setSamples(self.MSAA_SAMPLES)
        surface.setDepthBufferSize(24)
        self.setFormat(surface)
        self.setMinimumSize(800, 600)
        self.setFocusPolicy(Qt.StrongFocus)  # Enable keyboard focus

        self.object_service = object_service
        self.input_service = None  # Will be set by MainWindow
        self.renderer = SceneRenderer()
        self._apply_theme()
        theme.signals.changed.connect(self._apply_theme)
        # Overlays (SetpointOverlay, TrainerService…) provide drawables() and may provide
        # alpha_for(obj) and colour_for(obj).
        self.overlays = []
        # Shadows / height lines / selection ring; always drawn first (see overlay_arguments).
        self.ground_overlay = GroundOverlay(object_service, hovered=self._get_hovered)
        self.hovered_object = None
        self._press_pos = None
        self._press_button = None
        self._dragging = False
        self._hover_pos = None
        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.timeout.connect(self._update_hover)
        self.setMouseTracking(True)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(16)  # Update approximately every 16 milliseconds (about 60 FPS)

        self.prev_time = time.perf_counter()
        self.fps = 0.0

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
        self.hud_label.move(10, 10)
        self.game_hud = QLabel(self)
        self.game_hud.setObjectName("GameHud")
        self.game_hud.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.game_hud.hide()

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
        # Also runs again if Qt recreates the context (e.g. the widget moves to another window).
        self.renderer.initialize()

    @pyqtSlot(object)
    def _apply_theme(self, _palette=None):
        """Viewport background follows the light/dark palette."""
        self.renderer.background = theme.rgba("viewport_bottom")
        self.renderer.background_gradient = (theme.rgba("viewport_top"), theme.rgba("viewport_bottom"))
        self.update()

    def paintGL(self):
        now = time.perf_counter()
        delta = now - self.prev_time
        self.prev_time = now
        if delta > 0:
            # Smooth so the readout is legible.
            self.fps = 0.9 * self.fps + 0.1 * (1.0 / delta) if self.fps else 1.0 / delta

        self.renderer.render(self.object_service.get_objects(), self.camera(),
                             self.width(), self.height(), **self.overlay_arguments())

    def overlay_arguments(self) -> dict:
        """Renderer keyword arguments combining every overlay."""
        overlays = [self.ground_overlay, *self.overlays]
        alpha_sources = [o.alpha_for for o in overlays if hasattr(o, "alpha_for")]
        colour_sources = [o.colour_for for o in overlays if hasattr(o, "colour_for")] + [self._theme_colour_for]

        def alpha_for(obj):
            return min((f(obj) for f in alpha_sources), default=1.0)

        def colour_for(obj):
            return next((c for c in (f(obj) for f in colour_sources) if c is not None), None)

        return {"overlays": [d for o in overlays for d in o.drawables()],
                "alpha_for": alpha_for if alpha_sources else None,
                "colour_for": colour_for,
                "rim_for": self._rim_for}

    def _rim_for(self, obj):
        """Silhouette glow: strong on the selected object, faint on the one under the mouse."""
        selected = self.object_service.get_selected_object() if self.object_service is not None else None
        if obj is selected:
            strength = self.SELECTED_RIM
        elif obj is self.hovered_object:
            strength = self.HOVER_RIM
        else:
            return None
        r, g, b, _ = theme.rgba("accent")
        return (r, g, b, strength)

    # -- picking ------------------------------------------------------------------

    def object_at(self, x: float, y: float):
        """The pickable object under widget pixel (x, y), or None."""
        if self.object_service is None:
            return None
        origin, direction = picking.screen_ray(self.camera(), x, y, self.width(), self.height())
        obj, _ = picking.pick(self.object_service.get_objects(), origin, direction)
        return obj

    def _get_hovered(self):
        return self.hovered_object

    def _set_hovered(self, obj):
        if obj is not self.hovered_object:
            self.hovered_object = obj
            self.setCursor(Qt.PointingHandCursor if obj is not None else Qt.ArrowCursor)
            self.update()

    @pyqtSlot()
    def _update_hover(self):
        if self._hover_pos is not None and self._press_pos is None:
            self._set_hovered(self.object_at(self._hover_pos.x(), self._hover_pos.y()))

    def leaveEvent(self, event):
        self._hover_timer.stop()
        self._hover_pos = None
        self._set_hovered(None)
        super().leaveEvent(event)

    @staticmethod
    def _theme_colour_for(obj):
        """A grid left at its default colour follows the light/dark theme."""
        if isinstance(obj, Grid) and tuple(obj.colour) == grid.DEFAULT_COLOUR:
            return theme.rgba("grid")
        return None

    def set_game_hud(self, text: str):
        """Large status line at the top of the viewport (empty hides it)."""
        self.game_hud.setText(text)
        self.game_hud.setVisible(bool(text))
        self.game_hud.adjustSize()
        self._place_game_hud()

    def _place_game_hud(self):
        # Bottom centre: clear of the FPS readout and the status panel at the top.
        self.game_hud.move(max(0, (self.width() - self.game_hud.width()) // 2),
                           max(0, self.height() - self.game_hud.height() - 28))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_game_hud()

    def _update_hud(self):
        self.hud_label.setText(
            f"FPS {self.fps:5.1f}   Cam {self.camera_angle_x:5.1f}° / {self.camera_angle_y:6.1f}°")
        self.hud_label.adjustSize()

    def resizeGL(self, width, height):
        pass  # QOpenGLWidget sets the viewport before each paintGL

    def mousePressEvent(self, event):
        self._press_pos = event.pos()
        self._press_button = event.button()
        self._dragging = False
        if event.button() == Qt.LeftButton:
            self.mouse_left_button_down = True
            self.mouse_last_x = event.x()
            self.mouse_last_y = event.y()

    def mouseReleaseEvent(self, event):
        clicked = self._press_pos is not None and not self._dragging and event.button() == self._press_button
        self._press_pos = None
        if event.button() == Qt.LeftButton:
            self.mouse_left_button_down = False
        if not clicked:
            return
        obj = self.object_at(event.x(), event.y())
        if event.button() == Qt.LeftButton:
            self.object_clicked.emit(obj)
        elif event.button() == Qt.RightButton:
            self.object_context_menu.emit(obj, event.globalPos())

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.object_double_clicked.emit(self.object_at(event.x(), event.y()))
        # Qt still sends the release that ends the double click: don't count it as a click too.
        self._press_pos = None

    def mouseMoveEvent(self, event):
        if self._press_pos is not None and not self._dragging:
            moved = event.pos() - self._press_pos
            if abs(moved.x()) + abs(moved.y()) >= self.CLICK_SLOP_PX:
                self._dragging = True     # from here on it's an orbit, not a click
        if self.mouse_left_button_down and self._dragging:
            dx = event.x() - self.mouse_last_x
            dy = event.y() - self.mouse_last_y
            self.camera_angle_y -= dx * 0.5
            self.camera_angle_x += dy * 0.5
            self.camera_angle_x = max(-90.0, min(90.0, self.camera_angle_x))
            self.mouse_last_x = event.x()
            self.mouse_last_y = event.y()
        elif self._press_pos is None:
            self._hover_pos = event.pos()
            if not self._hover_timer.isActive():
                self._hover_timer.start(self.HOVER_PICK_MS)

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
