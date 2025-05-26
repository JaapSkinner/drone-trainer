import pygame
from PyQt5.QtCore import QTimer, Qt, pyqtSlot
from PyQt5.QtWidgets import QDockWidget,QSplitter, QVBoxLayout, QPushButton, QMainWindow, QWidget,QScrollArea, QOpenGLWidget, QApplication, QFormLayout,QComboBox,QGroupBox,QLineEdit,QLabel
from gl_widget import GLWidget
from vicon_connection import ViconConnection
from structs import PositionData
class MainWindow(QMainWindow):
    def __init__(self, vicon:ViconConnection, parent=None):
        super(MainWindow, self).__init__(parent)
        self.vicon = vicon
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
        
        # Connect Vicon signals to slots
        self.vicon.position_updated.connect(self.update_vicon_position)
    
    def initUI(self):
        self.setWindowTitle('Collaborative Control Interface')
        self.setGeometry(50, 50, 800, 600)

        central_widget = QWidget(self)
        layout = QVBoxLayout(central_widget)
        self.setCentralWidget(central_widget)

        self.setupGLWidget(layout)
        self.setupDroneConnectButton(layout)
        self.setupViconConnectButton(layout)
        self.setupStartTrackingButton(layout)
        self.setupDockWidget()

    def setupGLWidget(self, layout):
        self.glWidget = GLWidget(self)
        layout.addWidget(self.glWidget)

    def setupDroneConnectButton(self, layout):
        button = QPushButton('Connect to Drone', self)
        layout.addWidget(button)
        
    @pyqtSlot()
    def connect_to_vicon(self):
        if self.vicon.connect():
            self.update_vicon_button(True)
        else:
            self.update_vicon_button(False)

    def update_vicon_button(self, connected):
        if connected:
            self.vicon_button.setEnabled(False)
            self.vicon_button.setText('Connected to Vicon')
            self.vicon_button.setStyleSheet("background-color : green")
        else:
            self.vicon_button.setEnabled(True)
            self.vicon_button.setText('Connect to Vicon')
            self.vicon_button.setStyleSheet("")

    def setupViconConnectButton(self, layout):
        self.vicon_button = QPushButton('Connect to Vicon', self)
        layout.addWidget(self.vicon_button)
        self.vicon_button.clicked.connect(self.connect_to_vicon)
    
    @pyqtSlot()
    def start_stop_tracking(self):
        if self.vicon.tracking:
            self.vicon.stop_tracking()
            self.update_tracking_button(False)
        else:
            if self.vicon.start_tracking():
                self.update_tracking_button(True)

    def update_tracking_button(self, tracking):
        if tracking:
            self.tracking_button.setText('Stop Tracking')
            self.tracking_button.setStyleSheet("background-color : red")
        else:
            self.tracking_button.setText('Start Tracking')
            self.tracking_button.setStyleSheet("")

    def setupStartTrackingButton(self, layout):
        self.tracking_button = QPushButton('Start Tracking', self)
        layout.addWidget(self.tracking_button)
        self.tracking_button.clicked.connect(self.start_stop_tracking)

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

    @pyqtSlot(PositionData)
    def update_vicon_position(self, pos_data: PositionData):
        for obj in self.glWidget.objects:
            if obj.tracked and obj.name == pos_data.name:
                obj.x_pos = pos_data.x
                obj.y_pos = pos_data.y
                obj.z_pos = pos_data.z
                obj.x_rot = pos_data.x_rot
                obj.y_rot = pos_data.y_rot
                obj.z_rot = pos_data.z_rot
                self.refreshUI()
