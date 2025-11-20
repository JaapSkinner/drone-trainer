from PyQt5.QtWidgets import QOpenGLWidget
from PyQt5.QtCore import QTimer, Qt
from OpenGL.GL import *
from OpenGL.GLUT import *
from OpenGL.GLU import *
import OpenGL.GLUT as GLUT

from models.scene_object import SceneObject
import numpy as np
from models.cad_mesh import CadMesh
from models.rect_prism import RectPrism
from models.grid import Grid
from models.axes import Axes
from models.debug_text import DebugText
import time

class GLWidget(QOpenGLWidget):
    def __init__(self, object_service, parent=None):
        super().__init__(parent)
        self.setMinimumSize(800, 600)

        self.object_service = object_service

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(16)  # Update approximately every 16 milliseconds (about 60 FPS)

        self.prev_time = time.time()
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

        self.debug_count = 0  # Counter for debug text

    def initializeGL(self):
        glClearColor(1.0, 1.0, 1.0, 1.0)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_LIGHTING)
        glEnable(GL_COLOR_MATERIAL)
        glEnable(GL_LIGHT0)
        glLightfv(GL_LIGHT0, GL_DIFFUSE, [1.0, 1.0, 1.0, 1.0])
        glLightfv(GL_LIGHT0, GL_SPECULAR, [1.0, 1.0, 1.0, 1.0])
        glShadeModel(GL_SMOOTH)

    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(45.0, self.width() / self.height(), 0.1, 100.0)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        gluLookAt(
            self.camera_distance * np.sin(np.radians(self.camera_angle_y)) * np.cos(np.radians(self.camera_angle_x)),
            self.camera_distance * np.sin(np.radians(self.camera_angle_x)),
            self.camera_distance * np.cos(np.radians(self.camera_angle_y)) * np.cos(np.radians(self.camera_angle_x)),
            0.0, 0.0, 0.0,
            0.0, 1.0, 0.0
        )
        glLightfv(GL_LIGHT0, GL_POSITION, [10.0, 10.0, 10.0, 0.0])

        current_time = time.time()
        delta = current_time - self.prev_time
        if delta > 0:
            self.fps = 1.0 / delta
        self.prev_time = current_time

        window_dimensions = (self.width(), self.height())

        self.object_service.update_debug_text("FPS", self.fps, dimensions=window_dimensions)
        self.object_service.update_debug_text("Cam X", self.camera_angle_x, dimensions=window_dimensions)
        self.object_service.update_debug_text("Cam Y", self.camera_angle_y, dimensions=window_dimensions)

        self.object_service.draw_objects()

        # Draw dashed line between the first and second objects
        # start = np.array([self.objects[0].x_pos, self.objects[0].y_pos, self.objects[0].z_pos])
        # end = np.array([self.objects[1].x_pos, self.objects[1].y_pos, self.objects[1].z_pos])
        # self.draw_dashed_line(start, end, (0.855, 0.647, 0.125))  # Yellow color


        # Draw arrows in the direction of each moving object's velocity
        # for obj in self.objects:
        #     if obj.x_vel != 0.0 or obj.y_vel != 0.0 or obj.z_vel != 0.0:
        #         arrow_start = np.array([obj.x_pos, obj.y_pos, obj.z_pos])
        #         arrow_end = arrow_start + np.array([obj.x_vel, obj.y_vel, obj.z_vel]) * 10  # Scale the velocity for visibility
        #         self.draw_arrow(arrow_start, arrow_end, (1.0, 0.0, 0.0))  # Red color arrow

        # Draw two arrows pointing up at each end of the green rectangle
        # green_rect = self.objects[2]
        # half_length = (green_rect.length / 2) - 0.1 # Offset the arrows slightly from the edges of the rectangle
        # start_arrow_1 = np.array([green_rect.x_pos - half_length, green_rect.y_pos, green_rect.z_pos])
        # end_arrow_1 = start_arrow_1 + np.array([0.0, 0.5, 0.0])
        # self.draw_arrow(start_arrow_1, end_arrow_1, (0.0, 0.0, 1.0))  # Blue FORCE ARROW
        #
        # start_arrow_2 = np.array([green_rect.x_pos + half_length, green_rect.y_pos, green_rect.z_pos])
        # end_arrow_2 = start_arrow_2 + np.array([0.0, 0.5, 0.0])
        # self.draw_arrow(start_arrow_2, end_arrow_2, (0.0, 0.0, 1.0))


    def resizeGL(self, width, height):
        glViewport(0, 0, width, height)

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

    def draw_dashed_line(self, start, end, color, dash_length=0.1):
        glColor3f(*color)
        glLineWidth(4.0)  # Set line width to 3.0 for thicker lines
        glBegin(GL_LINES)
        length = np.linalg.norm(np.array(end) - np.array(start))
        num_dashes = int(length / dash_length)
        for i in range(num_dashes):
            t1 = i / num_dashes
            t2 = (i + 0.5) / num_dashes
            point1 = start * (1 - t1) + np.array(end) * t1
            point2 = start * (1 - t2) + np.array(end) * t2
            glVertex3fv(point1)
            glVertex3fv(point2)
        glEnd()
        glLineWidth(1.0)  # Set line width to 3.0 for thicker lines

    def draw_arrow(self, start, end, color, arrow_head_length=0.2, arrow_head_width=0.1):
        glColor3f(*color)
        glLineWidth(3.0)  # Set line width for the arrow

        # Draw the arrow shaft
        glBegin(GL_LINES)
        glVertex3fv(start)
        glVertex3fv(end)
        glEnd()

        # Calculate the direction of the arrow
        direction = np.array(end) - np.array(start)
        direction = direction / np.linalg.norm(direction)

        # Calculate points for the arrow head
        ortho_direction = np.array([-direction[1], direction[0], 0])  # Perpendicular in 2D
        arrow_left = np.array(end) - arrow_head_length * direction + arrow_head_width * ortho_direction
        arrow_right = np.array(end) - arrow_head_length * direction - arrow_head_width * ortho_direction

        # Draw the arrow head
        glBegin(GL_TRIANGLES)
        glVertex3fv(end)
        glVertex3fv(arrow_left)
        glVertex3fv(arrow_right)
        glEnd()

        glLineWidth(1.0)  # Reset line width


