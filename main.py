import sys
import numpy as np
from PyQt5.QtWidgets import QDockWidget,QSplitter, QVBoxLayout, QPushButton, QMainWindow, QWidget,QScrollArea, QOpenGLWidget, QApplication, QFormLayout,QComboBox,QGroupBox,QLineEdit,QLabel
from PyQt5.QtCore import QTimer, Qt
from OpenGL.GL import *
from OpenGL.GLUT import *
from OpenGL.GLU import *
import pygame

class SceneObject:
    def __init__(self, x, y, z, x_rot, y_rot, z_rot, color, size, name, length=0.5, transparency=1.0, tracked=False):
        self.x_pos = x
        self.y_pos = y
        self.z_pos = z
        self.x_rot = x_rot
        self.y_rot = y_rot
        self.z_rot = z_rot
        self.color = color
        self.size = size
        self.length = length
        self.transparency = transparency
        self.tracked = tracked
        self.name = name

        self.x_vel = 0.0  # Adding velocity attributes
        self.y_vel = 0.0
        self.z_vel = 0.0

    def draw(self):
        # Draw solid rectangle
        glPushMatrix()
        glTranslatef(self.x_pos, self.y_pos, self.z_pos)
        glRotatef(self.x_rot, 1.0, 0.0, 0.0)
        glRotatef(self.y_rot, 0.0, 1.0, 0.0)
        glRotatef(self.z_rot, 0.0, 0.0, 1.0)
        glScalef(self.length, self.size, self.size)
        glColor4f(*self.color, self.transparency)
        glutSolidCube(1.0)
        glPopMatrix()

        # Draw wireframe rectangle
        glPushMatrix()
        glTranslatef(self.x_pos, self.y_pos, self.z_pos)
        glRotatef(self.x_rot, 1.0, 0.0, 0.0)
        glRotatef(self.y_rot, 0.0, 1.0, 0.0)
        glRotatef(self.z_rot, 0.0, 0.0, 1.0)
        glScalef(self.length, self.size, self.size)
        glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)
        glLineWidth(3.0)
        glColor3f(0.0, 0.0, 0.0)
        glutSolidCube(1.0)
        glPopMatrix()

        # Ensure OpenGL state is reset to default after rendering
        glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)  # Reset polygon mode to fill
        glLineWidth(1.0)  # Reset line width

class GLWidget(QOpenGLWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(800, 600)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update)
        self.timer.start(16)  # Update approximately every 16 milliseconds (about 60 FPS)

        self.objects = []

        # Initialize some objects
        self.objects.append(SceneObject(0.0, 0.0, 0.5, 0.0, 0.0, 0.0, (1.0, 0.0, 0.0), 0.5, name="Red Cube"))
        self.objects.append(SceneObject(1.5, 0.0, 0.5, 0.0, 0.0, 0.0, (0.0, 0.0, 1.0), 0.5, name="Blue Cube" ,transparency=0.5, tracked=True))
        self.objects.append(SceneObject(3.0, 0.0, 1.5, 0.0, 0.0, 0.0, (0.0, 1.0, 0.0), 0.25, name="Green Cube",length=3.0))  # Green rectangle

        # Camera parameters
        self.camera_distance = 10.0
        self.camera_angle_x = 30.0
        self.camera_angle_y = 45.0
        self.mouse_last_x = 0
        self.mouse_last_y = 0
        self.mouse_left_button_down = False

    def initializeGL(self):
        glClearColor(1.0, 1.0, 1.0, 1.0)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

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

        self.draw_grid()
        self.draw_axes()

        for obj in self.objects:
            obj.draw()
        
        # Draw dashed line between the first and second objects
        start = np.array([self.objects[0].x_pos, self.objects[0].y_pos, self.objects[0].z_pos])
        end = np.array([self.objects[1].x_pos, self.objects[1].y_pos, self.objects[1].z_pos])
        self.draw_dashed_line(start, end, (0.855, 0.647, 0.125))  # Yellow color


        # Draw arrows in the direction of each moving object's velocity
        for obj in self.objects:
            if obj.x_vel != 0.0 or obj.y_vel != 0.0 or obj.z_vel != 0.0:
                arrow_start = np.array([obj.x_pos, obj.y_pos, obj.z_pos])
                arrow_end = arrow_start + np.array([obj.x_vel, obj.y_vel, obj.z_vel]) * 10  # Scale the velocity for visibility
                self.draw_arrow(arrow_start, arrow_end, (1.0, 0.0, 0.0))  # Red color arrow

        # Draw two arrows pointing up at each end of the green rectangle
        green_rect = self.objects[2]
        half_length = (green_rect.length / 2) - 0.1 # Offset the arrows slightly from the edges of the rectangle
        start_arrow_1 = np.array([green_rect.x_pos - half_length, green_rect.y_pos, green_rect.z_pos])
        end_arrow_1 = start_arrow_1 + np.array([0.0, 0.5, 0.0])
        self.draw_arrow(start_arrow_1, end_arrow_1, (0.0, 0.0, 1.0))  # Blue FORCE ARROW 

        start_arrow_2 = np.array([green_rect.x_pos + half_length, green_rect.y_pos, green_rect.z_pos])
        end_arrow_2 = start_arrow_2 + np.array([0.0, 0.5, 0.0])
        self.draw_arrow(start_arrow_2, end_arrow_2, (0.0, 0.0, 1.0)) 

    def draw_grid(self):
        glColor3f(0.68, 0.68, 0.68)
        glBegin(GL_LINES)
        for i in range(-10, 11):
            glVertex3f(i, 0, -10)
            glVertex3f(i, 0, 10)
            glVertex3f(-10, 0, i)
            glVertex3f(10, 0, i)
        glEnd()

    def draw_axes(self):
        glLineWidth(2.0)
        glBegin(GL_LINES)
        glColor3f(1.0, 0.0, 0.0)
        glVertex3f(0, 0, 0)
        glVertex3f(1, 0, 0)
        glColor3f(0.0, 1.0, 0.0)
        glVertex3f(0, 0, 0)
        glVertex3f(0, 1, 0)
        glColor3f(0.0, 0.0, 1.0)
        glVertex3f(0, 0, 0)
        glVertex3f(0, 0, 1)
        glEnd()

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
            self.camera_angle_y += dx * 0.5
            self.camera_angle_x -= dy * 0.5
            self.camera_angle_x = max(-90, min(90, self.camera_angle_x))
            self.mouse_last_x = event.x()
            self.mouse_last_y = event.y()
            self.update()
    
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


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super(MainWindow, self).__init__(parent)
        self.initUI()

        # Initialize Pygame for joystick input
        pygame.init()
        pygame.joystick.init()
        self.controller = pygame.joystick.Joystick(0)
        self.controller.init()

        self.controller_object = -1 # Index of the object to control with the controller -1 is none

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_controller)
        self.timer.start(16)  # Update approximately every 16 milliseconds (about 60 FPS)
    
    def initUI(self):
        self.setWindowTitle('Collaborative Control Interface')
        self.setGeometry(50, 50, 800, 600)

        central_widget = QWidget(self)
        layout = QVBoxLayout(central_widget)
        self.setCentralWidget(central_widget)

        self.setupGLWidget(layout)
        self.setupConnectButton(layout)
        self.setupDockWidget()

    def setupGLWidget(self, layout):
        self.glWidget = GLWidget(self)
        layout.addWidget(self.glWidget)

    def setupConnectButton(self, layout):
        button = QPushButton('Connect to Drone', self)
        layout.addWidget(button)

    def setupDockWidget(self):
        dock_widget = QDockWidget(self)
        dock_widget.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        dock_widget.setMinimumWidth(300)
        dock_widget.setMinimumHeight(300)
        dock_widget.setFeatures(QDockWidget.NoDockWidgetFeatures)

        self.setupTitleBar(dock_widget)
        self.setupSplitter(dock_widget)

        self.addDockWidget(Qt.LeftDockWidgetArea, dock_widget)

    def setupTitleBar(self, dock_widget):
        title_bar = QWidget()
        title_layout = QVBoxLayout(title_bar)
        title_layout.setContentsMargins(0, 0, 0, 0)

        title_label = QLabel("Objects")
        title_layout.addWidget(title_label)

        dock_widget.setTitleBarWidget(title_bar)

    def setupSplitter(self, dock_widget):
        self.splitter = QSplitter(Qt.Vertical)
        self.setupControllerGroupBox()
        self.setupRadioAddressGroupBox()
        self.setupScrollArea()

        dock_widget.setWidget(self.splitter)

    def setupControllerGroupBox(self):
        self.combo_box = QComboBox()
        label = QLabel("Controller Object")
        controller_layout = QVBoxLayout()
        controller_layout.addWidget(label)
        controller_layout.addWidget(self.combo_box)
        controller_group_box = QGroupBox("Controller")
        controller_group_box.setLayout(controller_layout)
        self.splitter.addWidget(controller_group_box)

    def setupRadioAddressGroupBox(self):
        radio_address_group_box = QGroupBox("Radio Address")
        radio_address_layout = QFormLayout()
        atlas_input = QLineEdit()
        pbody_input = QLineEdit()
        radio_address_layout.addRow(QLabel("Atlas"), atlas_input)
        radio_address_layout.addRow(QLabel("Pbody"), pbody_input)
        radio_address_group_box.setLayout(radio_address_layout)
        self.splitter.addWidget(radio_address_group_box)

    def setupScrollArea(self):
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)

        self.setupObjectGroupBoxes()

        self.scroll_content.setLayout(self.scroll_layout)
        self.scroll_area.setWidget(self.scroll_content)
        self.splitter.addWidget(self.scroll_area)

    def setupObjectGroupBoxes(self):
        self.input_fields = []

        for i, obj in enumerate(self.glWidget.objects):
            group_box = QGroupBox(f"Object {i}")
            form_layout = QFormLayout()
            if not obj.tracked:
                self.combo_box.addItem(f"{obj.name}")
                self.combo_box.setItemData(self.combo_box.count() - 1, i)

            x_pos_input = QLineEdit(f"{obj.x_pos:.4f}")
            y_pos_input = QLineEdit(f"{obj.y_pos:.4f}")
            z_pos_input = QLineEdit(f"{obj.z_pos:.4f}")
            x_rot_input = QLineEdit(f"{obj.x_rot:.4f}")
            y_rot_input = QLineEdit(f"{obj.y_rot:.4f}")
            z_rot_input = QLineEdit(f"{obj.z_rot:.4f}")
            color_input = QLineEdit(f"({obj.color[0]:.4f}, {obj.color[1]:.4f}, {obj.color[2]:.4f})")
            size_input = QLineEdit(f"{obj.size:.4f}")
            length_input = QLineEdit(f"{obj.length:.4f}")
            transparency_input = QLineEdit(f"{obj.transparency:.4f}")

            self.connectInputFields(i, x_pos_input, y_pos_input, z_pos_input, x_rot_input, y_rot_input, z_rot_input, color_input, size_input, length_input, transparency_input)

            form_layout.addRow(QLabel("X Position"), x_pos_input)
            form_layout.addRow(QLabel("Y Position"), y_pos_input)
            form_layout.addRow(QLabel("Z Position"), z_pos_input)
            form_layout.addRow(QLabel("X Rotation"), x_rot_input)
            form_layout.addRow(QLabel("Y Rotation"), y_rot_input)
            form_layout.addRow(QLabel("Z Rotation"), z_rot_input)
            form_layout.addRow(QLabel("Color"), color_input)
            form_layout.addRow(QLabel("Size"), size_input)
            form_layout.addRow(QLabel("Length"), length_input)
            form_layout.addRow(QLabel("Transparency"), transparency_input)

            group_box.setLayout(form_layout)
            self.scroll_layout.addWidget(group_box)

            self.input_fields.append({
                'x_pos': x_pos_input,
                'y_pos': y_pos_input,
                'z_pos': z_pos_input,
                'x_rot': x_rot_input,
                'y_rot': y_rot_input,
                'z_rot': z_rot_input,
                'color': color_input,
                'size': size_input,
                'length': length_input,
                'transparency': transparency_input
            })

    def connectInputFields(self, index, x_pos_input, y_pos_input, z_pos_input, x_rot_input, y_rot_input, z_rot_input, color_input, size_input, length_input, transparency_input):
        x_pos_input.textChanged.connect(lambda text, index=index: self.updateObject(index, 'x_pos', text))
        y_pos_input.textChanged.connect(lambda text, index=index: self.updateObject(index, 'y_pos', text))
        z_pos_input.textChanged.connect(lambda text, index=index: self.updateObject(index, 'z_pos', text))
        x_rot_input.textChanged.connect(lambda text, index=index: self.updateObject(index, 'x_rot', text))
        y_rot_input.textChanged.connect(lambda text, index=index: self.updateObject(index, 'y_rot', text))
        z_rot_input.textChanged.connect(lambda text, index=index: self.updateObject(index, 'z_rot', text))
        color_input.textChanged.connect(lambda text, index=index: self.updateObject(index, 'color', text))
        size_input.textChanged.connect(lambda text, index=index: self.updateObject(index, 'size', text))
        length_input.textChanged.connect(lambda text, index=index: self.updateObject(index, 'length', text))
        transparency_input.textChanged.connect(lambda text, index=index: self.updateObject(index, 'transparency', text))

    def update_controller(self):
        def apply_deadzone(value, threshold):
            return value if abs(value) > threshold else 0

        pygame.event.pump()
        
        DEADZONE = 0.1
        
        left_stick_x = apply_deadzone(self.controller.get_axis(0), DEADZONE)
        left_stick_y = apply_deadzone(self.controller.get_axis(1), DEADZONE)
        right_stick_x = apply_deadzone(self.controller.get_axis(3), DEADZONE)
        right_stick_y = apply_deadzone(self.controller.get_axis(4), DEADZONE)
        
        left_bumper = self.controller.get_button(4)
        right_bumper = self.controller.get_button(5)
        
        self.controller_object = self.combo_box.itemData(self.combo_box.currentIndex())


        if self.controller_object != -1:
            # Update velocities
            self.glWidget.objects[self.controller_object].x_vel = left_stick_x * 0.1
            self.glWidget.objects[self.controller_object].z_vel = left_stick_y * 0.1
            self.glWidget.objects[self.controller_object].y_vel = (right_bumper - left_bumper) * 0.1
            
            # Update positions based on velocities
            self.glWidget.objects[self.controller_object].x_pos += self.glWidget.objects[self.controller_object].x_vel
            self.glWidget.objects[self.controller_object].z_pos += self.glWidget.objects[self.controller_object].z_vel
            self.glWidget.objects[self.controller_object].y_pos += self.glWidget.objects[self.controller_object].y_vel
            
            self.glWidget.objects[self.controller_object].x_rot += right_stick_y * 2.0
            self.glWidget.objects[self.controller_object].z_rot -= right_stick_x * 2.0

        # Refresh the UI fields
        self.refreshUI()

    def refreshUI(self):
        for i, obj in enumerate(self.glWidget.objects):
            fields = self.input_fields[i]
            fields['x_pos'].setText(f"{obj.x_pos:.4f}")
            fields['y_pos'].setText(f"{obj.y_pos:.4f}")
            fields['z_pos'].setText(f"{obj.z_pos:.4f}")
            fields['x_rot'].setText(f"{obj.x_rot:.4f}")
            fields['y_rot'].setText(f"{obj.y_rot:.4f}")
            fields['z_rot'].setText(f"{obj.z_rot:.4f}")
            fields['color'].setText(f"({obj.color[0]:.4f}, {obj.color[1]:.4f}, {obj.color[2]:.4f})")
            fields['size'].setText(f"{obj.size:.4f}")
            fields['length'].setText(f"{obj.length:.4f}")
            fields['transparency'].setText(f"{obj.transparency:.4f}")

    def updateObject(self, index, attribute, value):
        try:
            # Convert value to appropriate type
            if attribute in ['x_pos', 'y_pos', 'z_pos', 'x_rot', 'y_rot', 'z_rot', 'size', 'length']:
                value = float(value)
            elif attribute == 'transparency':
                value = float(value)
            elif attribute == 'color':
                value = tuple(map(float, value.strip('()').split(',')))
            
            # Update the SceneObject
            obj = self.glWidget.objects[index]
            setattr(obj, attribute, value)
        except ValueError:
            # Handle invalid input (e.g., non-numeric values)
            pass

def main():
    glutInit(sys.argv)  # Initialize GLUT before starting the QApplication
    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
