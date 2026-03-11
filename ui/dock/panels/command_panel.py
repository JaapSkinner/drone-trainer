"""
Command Panel for controlling drone/vehicle movement.

This panel provides various control modes for offboard control via mavlink commands:
- Home mode: Station keeping at a set home point with hover height (default)
- Jogging mode: Step-based position adjustment with adjustable step size
- Target mode: Specify target position or tracked object with offset
- Joystick mode: Controller/WASD/Arrow keys input

All modes manipulate the SETPOINT position. Current position is updated from tracking
or when setpoint is applied via "Send Position".

Ghost mode shows a "Next Setpoint" column for visualizing planned movements.
"""

from PyQt5.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QComboBox,
    QGroupBox, QFormLayout, QPushButton, QDoubleSpinBox,
    QTabWidget, QCheckBox, QSizePolicy, QScrollArea, QFrame,
    QSlider
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from models.debug_text import DebugText
from services.input_service import InputType


class CommandPanel(QWidget):
    """Command Panel for controlling drone/vehicle movement."""
    NavTag = "command"
    
    # Signals for external communication
    land_requested = pyqtSignal()
    go_home_requested = pyqtSignal()
    send_position_requested = pyqtSignal(tuple)  # Emits (x, y, z, qw, qx, qy, qz)
    set_home_requested = pyqtSignal(tuple)  # Emits (x, y, height)
    ghost_mode_changed = pyqtSignal(bool)
    controlled_object_changed = pyqtSignal(object)  # Emits SceneObject
    joystick_control_enabled = pyqtSignal(bool)  # Emits whether joystick control is active
    input_type_changed = pyqtSignal(object)  # Emits InputType for joystick settings
    sensitivity_changed = pyqtSignal(float)  # Emits sensitivity value
    
    # Constants for step scaling
    ROTATION_STEP_SCALE = 0.1  # Scale factor for rotation steps (radians per step)
    
    # Mode indices
    MODE_HOME = 0
    MODE_JOGGING = 1
    MODE_TARGET = 2
    MODE_JOYSTICK = 3
    
    def __init__(self, parent=None, object_service=None):
        super().__init__(parent)
        self.object_service = object_service
        self.ghost_mode = False
        self.home_position = (0.0, 0.0)  # Just X, Y - height is separate
        self.home_height = 1.0
        self.step_size = 0.1
        
        # Setpoint position (what we're commanding)
        self.setpoint = [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]
        
        # Next setpoint (ghost mode preview - only used when ghost mode is on)
        self.next_setpoint = [0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0]
        
        # Track current mode for joystick control
        self.current_mode = self.MODE_HOME
        
        self.init_ui()
    
    def init_ui(self):
        """Initialize the user interface."""
        main_layout = QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignTop)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(8, 8, 8, 8)
        
        # Create scrollable content
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(8)
        layout.setContentsMargins(0, 0, 12, 0)  # Right margin for scroll bar space
        
        # === Top Controls Section (always visible) ===
        top_controls = self._create_top_controls()
        layout.addWidget(top_controls)
        
        # === Controlled Object Selection ===
        object_group = self._create_object_selection()
        layout.addWidget(object_group)
        
        # === Ghost Mode Toggle ===
        ghost_group = self._create_ghost_mode_section()
        layout.addWidget(ghost_group)
        
        # === Mode Tabs (Home first as default offboard mode) ===
        self.mode_tabs = QTabWidget()
        self.mode_tabs.addTab(self._create_home_tab(), "Home")
        self.mode_tabs.addTab(self._create_jogging_tab(), "Jogging")
        self.mode_tabs.addTab(self._create_target_tab(), "Target")
        self.mode_tabs.addTab(self._create_joystick_tab(), "Joystick")
        self.mode_tabs.currentChanged.connect(self._on_mode_changed)
        layout.addWidget(self.mode_tabs)
        
        # === Position Display (Current, Setpoint, Delta) ===
        position_group = self._create_position_display()
        layout.addWidget(position_group)
        
        layout.addStretch()
        
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)
        
        # Populate the object dropdown after UI is fully constructed
        self.refresh_object_list()
    
    def _create_top_controls(self):
        """Create the top emergency and home controls."""
        group = QWidget()
        layout = QHBoxLayout(group)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        # Emergency LAND button - RED and prominent
        self.land_btn = QPushButton("LAND")
        self.land_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                font-weight: bold;
                font-size: 14px;
                padding: 12px 20px;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
            QPushButton:pressed {
                background-color: #bd2130;
            }
        """)
        self.land_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.land_btn.clicked.connect(self._on_land_clicked)
        layout.addWidget(self.land_btn)
        
        # Home button
        self.home_btn = QPushButton("HOME")
        self.home_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                font-weight: bold;
                font-size: 14px;
                padding: 12px 20px;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
            QPushButton:pressed {
                background-color: #1e7e34;
            }
        """)
        self.home_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.home_btn.clicked.connect(self._on_home_clicked)
        layout.addWidget(self.home_btn)
        
        return group
    
    def _create_object_selection(self):
        """Create the controlled object selection dropdown."""
        group = QGroupBox("Controlled Object")
        layout = QVBoxLayout(group)
        
        self.object_combo = QComboBox()
        self.object_combo.currentIndexChanged.connect(self._on_object_selected)
        layout.addWidget(self.object_combo)
        
        # Note: Dropdown will be populated after UI is fully constructed via refresh_object_list()
        
        return group
    
    def _create_ghost_mode_section(self):
        """Create the ghost mode toggle and send position button."""
        group = QGroupBox("Ghost Mode")
        layout = QVBoxLayout(group)
        
        # Ghost mode description
        desc = QLabel("Ghost mode shows 'Next Setpoint' for previewing movements before applying.")
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #666; font-size: 11px;")
        layout.addWidget(desc)
        
        # Ghost mode checkbox and send button row
        row = QHBoxLayout()
        
        self.ghost_checkbox = QCheckBox("Enable Ghost Mode")
        self.ghost_checkbox.stateChanged.connect(self._on_ghost_mode_changed)
        row.addWidget(self.ghost_checkbox)
        
        row.addStretch()
        
        self.send_position_btn = QPushButton("Send Position")
        self.send_position_btn.setEnabled(False)  # Disabled until there's a difference
        self.send_position_btn.setStyleSheet("""
            QPushButton {
                background-color: #007bff;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #0069d9;
            }
            QPushButton:pressed {
                background-color: #0062cc;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        self.send_position_btn.clicked.connect(self._on_send_position_clicked)
        row.addWidget(self.send_position_btn)
        
        layout.addLayout(row)
        
        return group
    
    def _create_jogging_tab(self):
        """Create the jogging mode tab for step-based position adjustment."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setAlignment(Qt.AlignTop)
        
        # Step size control
        step_row = QHBoxLayout()
        step_row.addWidget(QLabel("Step Size:"))
        
        self.step_size_spin = QDoubleSpinBox()
        self.step_size_spin.setRange(0.01, 10.0)
        self.step_size_spin.setValue(0.1)
        self.step_size_spin.setSingleStep(0.01)
        self.step_size_spin.setDecimals(2)
        self.step_size_spin.setSuffix(" m")
        self.step_size_spin.valueChanged.connect(self._on_step_size_changed)
        step_row.addWidget(self.step_size_spin)
        step_row.addStretch()
        layout.addLayout(step_row)
        
        # Position controls
        pos_group = QGroupBox("Position (X, Y, Z)")
        pos_layout = QFormLayout(pos_group)
        
        # X position
        x_row = self._create_jog_row("X")
        self.jog_x_value = x_row["value"]
        self.jog_x_minus = x_row["minus"]
        self.jog_x_plus = x_row["plus"]
        pos_layout.addRow("X:", x_row["widget"])
        
        # Y position
        y_row = self._create_jog_row("Y")
        self.jog_y_value = y_row["value"]
        self.jog_y_minus = y_row["minus"]
        self.jog_y_plus = y_row["plus"]
        pos_layout.addRow("Y:", y_row["widget"])
        
        # Z position
        z_row = self._create_jog_row("Z")
        self.jog_z_value = z_row["value"]
        self.jog_z_minus = z_row["minus"]
        self.jog_z_plus = z_row["plus"]
        pos_layout.addRow("Z:", z_row["widget"])
        
        layout.addWidget(pos_group)
        
        # Rotation controls
        rot_group = QGroupBox("Rotation (Roll, Pitch, Yaw)")
        rot_layout = QFormLayout(rot_group)
        
        # Roll
        roll_row = self._create_jog_row("Roll")
        self.jog_roll_value = roll_row["value"]
        self.jog_roll_minus = roll_row["minus"]
        self.jog_roll_plus = roll_row["plus"]
        rot_layout.addRow("Roll:", roll_row["widget"])
        
        # Pitch
        pitch_row = self._create_jog_row("Pitch")
        self.jog_pitch_value = pitch_row["value"]
        self.jog_pitch_minus = pitch_row["minus"]
        self.jog_pitch_plus = pitch_row["plus"]
        rot_layout.addRow("Pitch:", pitch_row["widget"])
        
        # Yaw
        yaw_row = self._create_jog_row("Yaw")
        self.jog_yaw_value = yaw_row["value"]
        self.jog_yaw_minus = yaw_row["minus"]
        self.jog_yaw_plus = yaw_row["plus"]
        rot_layout.addRow("Yaw:", yaw_row["widget"])
        
        layout.addWidget(rot_group)
        
        return tab
    
    def _create_jog_row(self, axis):
        """Create a jogging row with minus button, value label, and plus button."""
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        
        minus_btn = QPushButton("-")
        minus_btn.setFixedSize(28, 28)
        minus_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        minus_btn.clicked.connect(lambda: self._jog_axis(axis, -1))
        row.addWidget(minus_btn)
        
        value_label = QLabel("0.0000")
        value_label.setAlignment(Qt.AlignCenter)
        value_label.setFixedWidth(70)
        value_label.setStyleSheet("font-family: monospace;")
        row.addWidget(value_label)
        
        plus_btn = QPushButton("+")
        plus_btn.setFixedSize(28, 28)
        plus_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                font-weight: bold;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        plus_btn.clicked.connect(lambda: self._jog_axis(axis, 1))
        row.addWidget(plus_btn)
        
        # Add stretch at end to push controls to the left within row
        row.addStretch()
        
        return {"widget": widget, "minus": minus_btn, "value": value_label, "plus": plus_btn}
    
    def _create_target_tab(self):
        """Create the target mode tab for specifying target positions."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setAlignment(Qt.AlignTop)
        
        # Target type selection
        type_row = QHBoxLayout()
        type_row.addWidget(QLabel("Target Type:"))
        
        self.target_type_combo = QComboBox()
        self.target_type_combo.addItem("Point in Space", "point")
        self.target_type_combo.addItem("Tracked Object", "tracked")
        self.target_type_combo.currentIndexChanged.connect(self._on_target_type_changed)
        type_row.addWidget(self.target_type_combo)
        type_row.addStretch()
        layout.addLayout(type_row)
        
        # Point in space inputs
        self.point_group = QGroupBox("Target Position")
        point_layout = QFormLayout(self.point_group)
        
        self.target_x_spin = QDoubleSpinBox()
        self.target_x_spin.setRange(-100.0, 100.0)
        self.target_x_spin.setDecimals(3)
        self.target_x_spin.setSuffix(" m")
        point_layout.addRow("X:", self.target_x_spin)
        
        self.target_y_spin = QDoubleSpinBox()
        self.target_y_spin.setRange(-100.0, 100.0)
        self.target_y_spin.setDecimals(3)
        self.target_y_spin.setSuffix(" m")
        point_layout.addRow("Y:", self.target_y_spin)
        
        self.target_z_spin = QDoubleSpinBox()
        self.target_z_spin.setRange(-100.0, 100.0)
        self.target_z_spin.setDecimals(3)
        self.target_z_spin.setSuffix(" m")
        point_layout.addRow("Z:", self.target_z_spin)
        
        layout.addWidget(self.point_group)
        
        # Tracked object selection
        self.tracked_group = QGroupBox("Tracked Object")
        tracked_layout = QFormLayout(self.tracked_group)
        
        self.tracked_object_combo = QComboBox()
        tracked_layout.addRow("Object:", self.tracked_object_combo)
        
        layout.addWidget(self.tracked_group)
        self.tracked_group.hide()  # Hidden by default
        
        # Offset controls (for approaching target)
        offset_group = QGroupBox("Offset from Target")
        offset_layout = QFormLayout(offset_group)
        
        self.offset_x_spin = QDoubleSpinBox()
        self.offset_x_spin.setRange(-50.0, 50.0)
        self.offset_x_spin.setDecimals(3)
        self.offset_x_spin.setSuffix(" m")
        offset_layout.addRow("X Offset:", self.offset_x_spin)
        
        self.offset_y_spin = QDoubleSpinBox()
        self.offset_y_spin.setRange(-50.0, 50.0)
        self.offset_y_spin.setDecimals(3)
        self.offset_y_spin.setSuffix(" m")
        offset_layout.addRow("Y Offset:", self.offset_y_spin)
        
        self.offset_z_spin = QDoubleSpinBox()
        self.offset_z_spin.setRange(-50.0, 50.0)
        self.offset_z_spin.setDecimals(3)
        self.offset_z_spin.setSuffix(" m")
        offset_layout.addRow("Z Offset:", self.offset_z_spin)
        
        layout.addWidget(offset_group)
        
        # Go to target button
        self.go_to_target_btn = QPushButton("Go to Target")
        self.go_to_target_btn.setStyleSheet("""
            QPushButton {
                background-color: #17a2b8;
                color: white;
                font-weight: bold;
                padding: 10px 20px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #138496;
            }
        """)
        self.go_to_target_btn.clicked.connect(self._on_go_to_target_clicked)
        layout.addWidget(self.go_to_target_btn)
        
        return tab
    
    def _create_home_tab(self):
        """Create the home mode tab for station keeping."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setAlignment(Qt.AlignTop)
        
        # Home position display (X, Z ground position - height/Y is separate)
        home_group = QGroupBox("Home Position (Ground)")
        home_layout = QFormLayout(home_group)
        
        self.home_x_label = QLabel("0.000")
        self.home_x_label.setStyleSheet("font-family: monospace;")
        home_layout.addRow("X:", self.home_x_label)
        
        self.home_z_label = QLabel("0.000")
        self.home_z_label.setStyleSheet("font-family: monospace;")
        home_layout.addRow("Z:", self.home_z_label)
        
        self.hover_height_spin = QDoubleSpinBox()
        self.hover_height_spin.setRange(0.1, 50.0)
        self.hover_height_spin.setValue(1.0)
        self.hover_height_spin.setDecimals(2)
        self.hover_height_spin.setSuffix(" m")
        self.hover_height_spin.valueChanged.connect(self._on_hover_height_changed)
        home_layout.addRow("Height (Y):", self.hover_height_spin)
        
        layout.addWidget(home_group)
        
        # Set Home button
        self.set_home_btn = QPushButton("Set Current Position as Home")
        self.set_home_btn.setStyleSheet("""
            QPushButton {
                background-color: #ffc107;
                color: #212529;
                font-weight: bold;
                padding: 10px 20px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #e0a800;
            }
        """)
        self.set_home_btn.clicked.connect(self._on_set_home_clicked)
        layout.addWidget(self.set_home_btn)
        
        # Go Home button
        self.go_home_btn = QPushButton("Go to Home")
        self.go_home_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                font-weight: bold;
                padding: 10px 20px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)
        self.go_home_btn.clicked.connect(self._on_go_home_tab_clicked)
        layout.addWidget(self.go_home_btn)
        
        return tab
    
    def _create_joystick_tab(self):
        """Create the joystick mode tab for controller input with input settings."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setAlignment(Qt.AlignTop)
        
        # Info text
        info = QLabel("""
        <b>Joystick Mode</b><br><br>
        Use controller input (WASD, Arrow Keys, or Joystick) to move the controlled object.<br><br>
        In Ghost Mode, movements update "Next Setpoint" until you click "Send Position".
        """)
        info.setWordWrap(True)
        info.setStyleSheet("color: #555; padding: 10px;")
        layout.addWidget(info)
        
        # Input Device Settings Group (moved from Config panel)
        input_group = QGroupBox("Input Settings")
        input_layout = QFormLayout(input_group)
        
        # Input Type Selection
        self.input_type_combo = QComboBox()
        self.input_type_combo.addItem("Controller", InputType.CONTROLLER)
        self.input_type_combo.addItem("WASD Keys", InputType.WASD)
        self.input_type_combo.addItem("Arrow Keys", InputType.ARROW_KEYS)
        self.input_type_combo.currentIndexChanged.connect(self._on_input_type_changed)
        input_layout.addRow("Input Type:", self.input_type_combo)
        
        # Sensitivity Slider
        self.sensitivity_slider = QSlider(Qt.Horizontal)
        self.sensitivity_slider.setMinimum(10)  # 0.1 * 100
        self.sensitivity_slider.setMaximum(500)  # 5.0 * 100
        self.sensitivity_slider.setValue(100)  # 1.0 * 100 (default)
        self.sensitivity_slider.setTickPosition(QSlider.TicksBelow)
        self.sensitivity_slider.setTickInterval(50)
        self.sensitivity_slider.valueChanged.connect(self._on_sensitivity_changed)
        
        self.sensitivity_label = QLabel("1.0x")
        sensitivity_container = QWidget()
        sensitivity_layout = QVBoxLayout(sensitivity_container)
        sensitivity_layout.setContentsMargins(0, 0, 0, 0)
        sensitivity_layout.addWidget(self.sensitivity_slider)
        sensitivity_layout.addWidget(self.sensitivity_label)
        
        input_layout.addRow("Sensitivity:", sensitivity_container)
        
        layout.addWidget(input_group)
        
        # Input Mapping Info Group
        mapping_group = QGroupBox("Input Mapping")
        mapping_layout = QVBoxLayout(mapping_group)
        
        self.mapping_info = QLabel()
        self.mapping_info.setWordWrap(True)
        self.mapping_info.setStyleSheet("font-size: 11px; color: #555;")
        mapping_layout.addWidget(self.mapping_info)
        
        layout.addWidget(mapping_group)
        
        # Update mapping info for default selection
        self._update_mapping_info(InputType.CONTROLLER)
        
        return tab
    
    def _on_input_type_changed(self, index):
        """Handle input type selection change in joystick tab."""
        input_type = self.input_type_combo.itemData(index)
        self._update_mapping_info(input_type)
        self.input_type_changed.emit(input_type)
    
    def _on_sensitivity_changed(self, value):
        """Handle sensitivity slider change."""
        sensitivity = value / 100.0
        self.sensitivity_label.setText(f"{sensitivity:.1f}x")
        self.sensitivity_changed.emit(sensitivity)
    
    def _update_mapping_info(self, input_type):
        """Update the mapping information display based on input type."""
        if input_type == InputType.CONTROLLER:
            info = """<b>Controller Mapping:</b><br>
            • Left Stick: Move (X/Z)<br>
            • Right Stick: Rotate<br>
            • LB/RB: Move Up/Down<br>
            • LT/RT: Rotate Z-axis"""
        elif input_type == InputType.WASD:
            info = """<b>WASD Mapping:</b><br>
            • W/S: Forward/Backward<br>
            • A/D: Strafe Left/Right<br>
            • Q/E: Move Up/Down<br>
            • R/F: Rotate"""
        elif input_type == InputType.ARROW_KEYS:
            info = """<b>Arrow Keys Mapping:</b><br>
            • Up/Down: Forward/Backward<br>
            • Left/Right: Strafe Left/Right<br>
            • Page Up/Down: Move Up/Down<br>
            • Home/End: Rotate"""
        else:
            info = "Unknown input type"
        
        self.mapping_info.setText(info)
    
    def _create_position_display(self):
        """Create the position display section with Current, Setpoint, and Next Setpoint (ghost mode).
        
        Note: Rotation values displayed are quaternion components (qx, qy, qz),
        not Euler angles. The pose format is (x, y, z, qw, qx, qy, qz).
        """
        group = QGroupBox("Position Info (m)")
        main_layout = QVBoxLayout(group)
        
        # Header row
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addWidget(QLabel(""))
        header_layout.addWidget(QLabel("<b>Current</b>"))
        header_layout.addWidget(QLabel("<b>Setpoint</b>"))
        
        self.next_setpoint_header = QLabel("<b>Next</b>")
        self.next_setpoint_header.setStyleSheet("color: #17a2b8;")
        self.next_setpoint_header.hide()  # Hidden by default, shown in ghost mode
        header_layout.addWidget(self.next_setpoint_header)
        main_layout.addWidget(header)
        
        # Style for labels
        mono_style = "font-family: monospace;"
        next_style = "font-family: monospace; color: #17a2b8;"
        
        # Create position rows with all three columns
        self.next_setpoint_labels = []  # Store references to hide/show
        
        # X row
        x_row = QWidget()
        x_layout = QHBoxLayout(x_row)
        x_layout.setContentsMargins(0, 0, 0, 0)
        x_layout.addWidget(QLabel("X:"))
        self.pos_x_label = QLabel("0.0000")
        self.pos_x_label.setStyleSheet(mono_style)
        x_layout.addWidget(self.pos_x_label)
        self.setpoint_x_label = QLabel("0.0000")
        self.setpoint_x_label.setStyleSheet(mono_style)
        x_layout.addWidget(self.setpoint_x_label)
        self.next_x_label = QLabel("0.0000")
        self.next_x_label.setStyleSheet(next_style)
        self.next_x_label.hide()
        self.next_setpoint_labels.append(self.next_x_label)
        x_layout.addWidget(self.next_x_label)
        main_layout.addWidget(x_row)
        
        # Y row
        y_row = QWidget()
        y_layout = QHBoxLayout(y_row)
        y_layout.setContentsMargins(0, 0, 0, 0)
        y_layout.addWidget(QLabel("Y:"))
        self.pos_y_label = QLabel("0.0000")
        self.pos_y_label.setStyleSheet(mono_style)
        y_layout.addWidget(self.pos_y_label)
        self.setpoint_y_label = QLabel("0.0000")
        self.setpoint_y_label.setStyleSheet(mono_style)
        y_layout.addWidget(self.setpoint_y_label)
        self.next_y_label = QLabel("0.0000")
        self.next_y_label.setStyleSheet(next_style)
        self.next_y_label.hide()
        self.next_setpoint_labels.append(self.next_y_label)
        y_layout.addWidget(self.next_y_label)
        main_layout.addWidget(y_row)
        
        # Z row
        z_row = QWidget()
        z_layout = QHBoxLayout(z_row)
        z_layout.setContentsMargins(0, 0, 0, 0)
        z_layout.addWidget(QLabel("Z:"))
        self.pos_z_label = QLabel("0.0000")
        self.pos_z_label.setStyleSheet(mono_style)
        z_layout.addWidget(self.pos_z_label)
        self.setpoint_z_label = QLabel("0.0000")
        self.setpoint_z_label.setStyleSheet(mono_style)
        z_layout.addWidget(self.setpoint_z_label)
        self.next_z_label = QLabel("0.0000")
        self.next_z_label.setStyleSheet(next_style)
        self.next_z_label.hide()
        self.next_setpoint_labels.append(self.next_z_label)
        z_layout.addWidget(self.next_z_label)
        main_layout.addWidget(z_row)
        
        # qX row
        qx_row = QWidget()
        qx_layout = QHBoxLayout(qx_row)
        qx_layout.setContentsMargins(0, 0, 0, 0)
        qx_layout.addWidget(QLabel("qX:"))
        self.rot_qx_label = QLabel("0.0000")
        self.rot_qx_label.setStyleSheet(mono_style)
        qx_layout.addWidget(self.rot_qx_label)
        self.setpoint_qx_label = QLabel("0.0000")
        self.setpoint_qx_label.setStyleSheet(mono_style)
        qx_layout.addWidget(self.setpoint_qx_label)
        self.next_qx_label = QLabel("0.0000")
        self.next_qx_label.setStyleSheet(next_style)
        self.next_qx_label.hide()
        self.next_setpoint_labels.append(self.next_qx_label)
        qx_layout.addWidget(self.next_qx_label)
        main_layout.addWidget(qx_row)
        
        # qY row
        qy_row = QWidget()
        qy_layout = QHBoxLayout(qy_row)
        qy_layout.setContentsMargins(0, 0, 0, 0)
        qy_layout.addWidget(QLabel("qY:"))
        self.rot_qy_label = QLabel("0.0000")
        self.rot_qy_label.setStyleSheet(mono_style)
        qy_layout.addWidget(self.rot_qy_label)
        self.setpoint_qy_label = QLabel("0.0000")
        self.setpoint_qy_label.setStyleSheet(mono_style)
        qy_layout.addWidget(self.setpoint_qy_label)
        self.next_qy_label = QLabel("0.0000")
        self.next_qy_label.setStyleSheet(next_style)
        self.next_qy_label.hide()
        self.next_setpoint_labels.append(self.next_qy_label)
        qy_layout.addWidget(self.next_qy_label)
        main_layout.addWidget(qy_row)
        
        # qZ row
        qz_row = QWidget()
        qz_layout = QHBoxLayout(qz_row)
        qz_layout.setContentsMargins(0, 0, 0, 0)
        qz_layout.addWidget(QLabel("qZ:"))
        self.rot_qz_label = QLabel("0.0000")
        self.rot_qz_label.setStyleSheet(mono_style)
        qz_layout.addWidget(self.rot_qz_label)
        self.setpoint_qz_label = QLabel("0.0000")
        self.setpoint_qz_label.setStyleSheet(mono_style)
        qz_layout.addWidget(self.setpoint_qz_label)
        self.next_qz_label = QLabel("0.0000")
        self.next_qz_label.setStyleSheet(next_style)
        self.next_qz_label.hide()
        self.next_setpoint_labels.append(self.next_qz_label)
        qz_layout.addWidget(self.next_qz_label)
        main_layout.addWidget(qz_row)
        
        return group
    
    # === Event Handlers ===
    
    def _on_land_clicked(self):
        """Handle LAND button click."""
        self.land_requested.emit()
    
    def _on_home_clicked(self):
        """Handle HOME button click - enables Home mode AND executes Go to Home.
        
        This is a safety button so it IGNORES ghost mode and immediately updates
        both setpoint and object position.
        """
        self.mode_tabs.setCurrentIndex(self.MODE_HOME)
        
        # Safety button - ignore ghost mode and immediately update setpoint AND object
        obj = self._get_controlled_object()
        if obj is not None:
            # Update setpoint to home position with hover height
            self.setpoint[0] = self.home_position[0]  # X
            self.setpoint[1] = self.hover_height_spin.value()  # Y (height)
            self.setpoint[2] = self.home_position[1]  # Z (stored as home_position[1])
            
            # Also sync next_setpoint if in ghost mode
            if self.ghost_mode:
                self.next_setpoint = list(self.setpoint)
            
            # Immediately update object position (safety - ignore ghost mode)
            obj.set_pose(self.setpoint)
            
            self._update_send_button_state()
            self._update_position_display()
            self._update_jog_values()
        
        self.go_home_requested.emit()
    
    def _on_mode_changed(self, index):
        """Handle mode tab change."""
        self.current_mode = index
        # Joystick control is enabled when in joystick mode (always live now, ghost mode just affects preview)
        is_joystick_mode = (index == self.MODE_JOYSTICK)
        self.joystick_control_enabled.emit(is_joystick_mode)
    
    def _on_object_selected(self, index):
        """Handle controlled object selection."""
        obj = self.object_combo.itemData(index)
        if obj is None:
            # "— None —" selected — clear controlled object and disable input
            if self.object_service:
                self.object_service.set_controlled_object(obj=None)
            self.controlled_object_changed.emit(None)
            self.joystick_control_enabled.emit(False)
            return
        if self.object_service:
            self.object_service.set_controlled_object(obj=obj)
            self.controlled_object_changed.emit(obj)
            # Sync setpoints with new object
            self._sync_setpoints_from_object()
            self._update_position_display()
            self._update_jog_values()
            # Emit joystick control enabled if in joystick mode
            if self.current_mode == self.MODE_JOYSTICK:
                self.joystick_control_enabled.emit(True)
    
    def _on_ghost_mode_changed(self, state):
        """Handle ghost mode toggle."""
        self.ghost_mode = state == Qt.Checked
        self.ghost_mode_changed.emit(self.ghost_mode)
        
        # Show/hide next setpoint column
        self.next_setpoint_header.setVisible(self.ghost_mode)
        for label in self.next_setpoint_labels:
            label.setVisible(self.ghost_mode)
        
        if self.ghost_mode:
            # Sync next_setpoint with current setpoint when enabling ghost mode
            self.next_setpoint = list(self.setpoint)
        
        self._update_send_button_state()
        self._update_position_display()
    
    def _on_send_position_clicked(self):
        """Handle send position button click.
        
        In ghost mode, this applies next_setpoint to setpoint and updates the object.
        """
        obj = self._get_controlled_object()
        if obj is None:
            return
        
        if self.ghost_mode:
            # Apply next_setpoint to setpoint
            self.setpoint = list(self.next_setpoint)
        
        # Update object position to match setpoint
        obj.set_pose(self.setpoint)
        
        # Emit the position
        x, y, z = self.setpoint[0], self.setpoint[1], self.setpoint[2]
        qw, qx, qy, qz = self.setpoint[3], self.setpoint[4], self.setpoint[5], self.setpoint[6]
        self.send_position_requested.emit((x, y, z, qw, qx, qy, qz))
        
        self._update_send_button_state()
        self._update_position_display()
        self._update_jog_values()
    
    def _on_step_size_changed(self, value):
        """Handle step size change."""
        self.step_size = value
    
    def _jog_axis(self, axis, direction):
        """Jog the setpoint along the specified axis.
        
        Always updates setpoint (or next_setpoint in ghost mode).
        The object position is updated from setpoint when not in ghost mode.
        """
        obj = self._get_controlled_object()
        if obj is None:
            return
        
        step = self.step_size * direction
        
        # Determine which setpoint to update
        target = self.next_setpoint if self.ghost_mode else self.setpoint
        
        if axis == "X":
            target[0] += step
        elif axis == "Y":
            target[1] += step
        elif axis == "Z":
            target[2] += step
        elif axis == "Roll":
            target[4] += step * self.ROTATION_STEP_SCALE
        elif axis == "Pitch":
            target[5] += step * self.ROTATION_STEP_SCALE
        elif axis == "Yaw":
            target[6] += step * self.ROTATION_STEP_SCALE
        
        # If not in ghost mode, also update the object position
        if not self.ghost_mode:
            obj.set_pose(self.setpoint)
        
        self._update_send_button_state()
        self._update_position_display()
        self._update_jog_values()
    
    def _on_target_type_changed(self, index):
        """Handle target type change."""
        target_type = self.target_type_combo.itemData(index)
        if target_type == "point":
            self.point_group.show()
            self.tracked_group.hide()
        else:
            self.point_group.hide()
            self.tracked_group.show()
            self._refresh_tracked_objects()
    
    def _refresh_tracked_objects(self):
        """Refresh the tracked objects dropdown."""
        self.tracked_object_combo.clear()
        if self.object_service:
            for obj in self.object_service.get_objects():
                if getattr(obj, 'tracked', False):
                    self.tracked_object_combo.addItem(obj.name, obj)
    
    def _on_go_to_target_clicked(self):
        """Handle go to target button click."""
        obj = self._get_controlled_object()
        if obj is None:
            return
        
        target_type = self.target_type_combo.currentData()
        
        if target_type == "point":
            x = self.target_x_spin.value() + self.offset_x_spin.value()
            y = self.target_y_spin.value() + self.offset_y_spin.value()
            z = self.target_z_spin.value() + self.offset_z_spin.value()
        else:
            tracked_obj = self.tracked_object_combo.currentData()
            if tracked_obj is None:
                return
            x = tracked_obj.pose[0] + self.offset_x_spin.value()
            y = tracked_obj.pose[1] + self.offset_y_spin.value()
            z = tracked_obj.pose[2] + self.offset_z_spin.value()
        
        # Update setpoint (or next_setpoint in ghost mode)
        target = self.next_setpoint if self.ghost_mode else self.setpoint
        target[0] = x
        target[1] = y
        target[2] = z
        
        # If not in ghost mode, update object position
        if not self.ghost_mode:
            obj.set_pose(self.setpoint)
        
        self._update_send_button_state()
        self._update_position_display()
        self._update_jog_values()
    
    def _on_set_home_clicked(self):
        """Handle set home button click."""
        obj = self._get_controlled_object()
        if obj is not None:
            # Home stores X and Z coordinates (horizontal plane), height (Y) is separate
            self.home_position = (obj.pose[0], obj.pose[2])  # (X, Z)
            self._update_home_display()
            height = self.hover_height_spin.value()
            self.set_home_requested.emit((self.home_position[0], self.home_position[1], height))
    
    def _on_go_home_tab_clicked(self):
        """Handle go home button click in the home tab."""
        obj = self._get_controlled_object()
        if obj is None:
            return
        
        # Update setpoint to home position with hover height
        # home_position = (X, Z), height is Y
        target = self.next_setpoint if self.ghost_mode else self.setpoint
        target[0] = self.home_position[0]  # X
        target[1] = self.hover_height_spin.value()  # Y (height)
        target[2] = self.home_position[1]  # Z (stored as home_position[1])
        
        # If not in ghost mode, update object position
        if not self.ghost_mode:
            obj.set_pose(self.setpoint)
        
        self._update_send_button_state()
        self._update_position_display()
        self._update_jog_values()
    
    def _on_hover_height_changed(self, value):
        """Handle hover height change."""
        self.home_height = value
    
    # === Helper Methods ===
    
    def _get_controlled_object(self):
        """Get the currently controlled object."""
        if self.object_service:
            return self.object_service.get_controlled_object()
        return None
    
    def _sync_setpoints_from_object(self):
        """Sync setpoint and next_setpoint from current object position."""
        obj = self._get_controlled_object()
        if obj is not None:
            self.setpoint = list(obj.pose)
            self.next_setpoint = list(obj.pose)
    
    def _update_send_button_state(self):
        """Update send position button enabled state.
        
        Button is enabled only in ghost mode when next_setpoint differs from setpoint.
        """
        if not self.ghost_mode:
            self.send_position_btn.setEnabled(False)
            return
        
        # Check if next_setpoint differs from setpoint
        differs = False
        for i in range(7):
            if abs(self.next_setpoint[i] - self.setpoint[i]) > 0.0001:
                differs = True
                break
        
        self.send_position_btn.setEnabled(differs)
    
    def _update_position_display(self):
        """Update the position display with current, setpoint, and next setpoint (ghost mode)."""
        obj = self._get_controlled_object()
        if obj is None:
            return
        
        # Current position (from object - updated by tracking or when setpoint applied)
        self.pos_x_label.setText(f"{obj.pose[0]:.4f}")
        self.pos_y_label.setText(f"{obj.pose[1]:.4f}")
        self.pos_z_label.setText(f"{obj.pose[2]:.4f}")
        self.rot_qx_label.setText(f"{obj.pose[4]:.4f}")
        self.rot_qy_label.setText(f"{obj.pose[5]:.4f}")
        self.rot_qz_label.setText(f"{obj.pose[6]:.4f}")
        
        # Setpoint (what we're commanding)
        self.setpoint_x_label.setText(f"{self.setpoint[0]:.4f}")
        self.setpoint_y_label.setText(f"{self.setpoint[1]:.4f}")
        self.setpoint_z_label.setText(f"{self.setpoint[2]:.4f}")
        self.setpoint_qx_label.setText(f"{self.setpoint[4]:.4f}")
        self.setpoint_qy_label.setText(f"{self.setpoint[5]:.4f}")
        self.setpoint_qz_label.setText(f"{self.setpoint[6]:.4f}")
        
        # Next setpoint (ghost mode preview)
        if self.ghost_mode:
            self.next_x_label.setText(f"{self.next_setpoint[0]:.4f}")
            self.next_y_label.setText(f"{self.next_setpoint[1]:.4f}")
            self.next_z_label.setText(f"{self.next_setpoint[2]:.4f}")
            self.next_qx_label.setText(f"{self.next_setpoint[4]:.4f}")
            self.next_qy_label.setText(f"{self.next_setpoint[5]:.4f}")
            self.next_qz_label.setText(f"{self.next_setpoint[6]:.4f}")
    
    def _update_jog_values(self):
        """Update the jog value labels - shows setpoint (or next_setpoint in ghost mode)."""
        # In ghost mode, show next_setpoint; otherwise show setpoint
        target = self.next_setpoint if self.ghost_mode else self.setpoint
        
        self.jog_x_value.setText(f"{target[0]:.4f}")
        self.jog_y_value.setText(f"{target[1]:.4f}")
        self.jog_z_value.setText(f"{target[2]:.4f}")
        self.jog_roll_value.setText(f"{target[4]:.4f}")
        self.jog_pitch_value.setText(f"{target[5]:.4f}")
        self.jog_yaw_value.setText(f"{target[6]:.4f}")
    
    def _update_home_display(self):
        """Update the home position display.
        
        home_position stores (X, Z) ground coordinates. Height (Y) is in the spinner.
        """
        self.home_x_label.setText(f"{self.home_position[0]:.3f}")
        self.home_z_label.setText(f"{self.home_position[1]:.3f}")
    
    def refresh_object_list(self):
        """Refresh the controlled object dropdown with only controllable objects."""
        if self.object_service is None:
            return
        
        # Store current selection
        current_obj = self.object_combo.currentData()
        
        # Clear and repopulate
        self.object_combo.blockSignals(True)
        self.object_combo.clear()

        # First item is always the "no object" sentinel
        self.object_combo.addItem("— None —", None)

        for obj in self.object_service.get_objects():
            # Only include controllable objects, exclude debug/utility objects
            is_controllable = getattr(obj, 'controllable', False)
            is_debug_text = isinstance(obj, DebugText)
            if is_controllable and not is_debug_text:
                self.object_combo.addItem(obj.name, obj)

        # Restore previous selection if still present; otherwise stay on None
        restored = False
        if current_obj is not None:
            for i in range(self.object_combo.count()):
                if self.object_combo.itemData(i) == current_obj:
                    self.object_combo.setCurrentIndex(i)
                    restored = True
                    break
        if not restored:
            self.object_combo.setCurrentIndex(0)  # Select "— None —"

        self.object_combo.blockSignals(False)
        
        # Sync setpoints and update displays
        self._sync_setpoints_from_object()
        self._update_position_display()
        self._update_jog_values()
    
    def refresh(self):
        """Refresh the panel display (called on input updates)."""
        self._update_position_display()
        self._update_jog_values()
    
    def update_setpoint_from_joystick(self, pose_delta):
        """Update setpoint (or next_setpoint in ghost mode) from joystick input.
        
        This is the primary method for joystick mode to update positions.
        Joystick should ALWAYS update setpoint/next_setpoint, never the object directly.
        
        Args:
            pose_delta: The delta to apply [dx, dy, dz, dqw, dqx, dqy, dqz]
        """
        obj = self._get_controlled_object()
        if obj is None:
            return
        
        # Determine which setpoint to update
        target = self.next_setpoint if self.ghost_mode else self.setpoint
        
        # Apply delta to target setpoint
        for i in range(7):
            target[i] += pose_delta[i]
        
        # If not in ghost mode, also update the object position
        if not self.ghost_mode:
            obj.set_pose(self.setpoint)
        
        self._update_send_button_state()
        self._update_position_display()
        self._update_jog_values()
    
    def is_joystick_control_allowed(self):
        """Check if joystick control should move the object.
        
        Returns True when in Joystick mode. Joystick is now always "live",
        but ghost mode affects whether it updates next_setpoint or setpoint.
        """
        return self.current_mode == self.MODE_JOYSTICK
