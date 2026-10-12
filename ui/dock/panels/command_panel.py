"""
Command Panel for controlling drone/vehicle movement.

This panel provides various control modes for offboard control via mavlink commands:
- Home mode: Station keeping at a set home point with hover height (default)
- Jogging mode: Step-based position adjustment with adjustable step size
- Target mode: Specify target position or tracked object with offset
- Joystick mode: Controller/WASD/Arrow keys input

All modes manipulate the SETPOINT (held by ControlService, drawn as a red ball in
the viewport). Objects tracked by motion capture are only commanded; other objects
fly to the setpoint as simulated vehicles.

Ghost mode edits a "Next" setpoint instead (a translucent ball) until "Send
Position" commits it.
"""

import math

from PyQt5.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QComboBox,
    QGroupBox, QFormLayout, QPushButton, QDoubleSpinBox,
    QTabWidget, QCheckBox, QSizePolicy, QScrollArea, QFrame,
    QSlider
)
from PyQt5.QtCore import QTimer, Qt, pyqtSignal, pyqtSlot
from models import frames
from services.control_service import ControlService
from services.input_service import InputType
from ui import theme
from ui.widgets.compact_tabs import CompactTabWidget
from ui.widgets.drone_status import DroneStatusWidget


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
    drone_setup_requested = pyqtSignal(object)  # object to set up, or None to add a new drone
    joystick_control_enabled = pyqtSignal(bool)  # Emits whether joystick control is active
    input_type_changed = pyqtSignal(object)  # Emits InputType for joystick settings
    sensitivity_changed = pyqtSignal(float)  # Emits sensitivity value
    
    # Rotation jogs turn this many degrees per metre of step size (5° at the default 0.1 step).
    ROTATION_DEG_PER_STEP_UNIT = 50.0
    # Scene axes for rotation jogs: roll about forward (X), pitch about the side (Z), yaw about up (Y).
    ROTATION_AXES = {"Roll": (1.0, 0.0, 0.0), "Pitch": (0.0, 0.0, 1.0), "Yaw": (0.0, 1.0, 0.0)}
    
    # Mode indices
    MODE_HOME = 0
    MODE_JOGGING = 1
    MODE_TARGET = 2
    MODE_JOYSTICK = 3
    
    def __init__(self, parent=None, object_service=None, control_service=None,
                 motion_capture_service=None, mavlink_service=None):
        super().__init__(parent)
        self.object_service = object_service
        self.motion_capture_service = motion_capture_service
        self.mavlink_service = mavlink_service
        self.control = control_service or ControlService(object_service, parent=self)
        self.control.setpoints_changed.connect(self._on_setpoints_changed)
        self.home_position = (0.0, 0.0)  # Just X, Y - height is separate
        self.home_height = 1.0
        self.step_size = 0.1
        # Simulated objects move continuously, so keep the readout live.
        self._display_timer = QTimer(self)
        self._display_timer.timeout.connect(self._on_display_timer)
        self._display_timer.start(100)
        
        # Track current mode for joystick control
        self.current_mode = self.MODE_HOME
        
        self.init_ui()
        if object_service is not None:
            object_service.controlled_object_changed.connect(self._on_controlled_object_changed)
    
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
        self.mode_tabs = CompactTabWidget()
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
        self.land_btn = theme.button("Land", "danger", "plane-landing", "lg")
        self.land_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.land_btn.clicked.connect(self._on_land_clicked)
        layout.addWidget(self.land_btn)
        
        # Home button
        self.home_btn = theme.button("Home", "success", "house", "lg")
        self.home_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.home_btn.clicked.connect(self._on_home_clicked)
        layout.addWidget(self.home_btn)
        
        return group
    
    def _create_object_selection(self):
        """Create the controlled object selection dropdown and its readiness checklist."""
        group = QGroupBox("Controlled Object")
        layout = QVBoxLayout(group)
        
        self.object_combo = QComboBox()
        self.object_combo.currentIndexChanged.connect(self._on_object_selected)
        layout.addWidget(self.object_combo)
        
        # Note: Dropdown will be populated after UI is fully constructed via refresh_object_list()

        # Is it tracked / connected / streaming? With a button into the drone setup.
        self.drone_status = DroneStatusWidget(self.motion_capture_service, self.mavlink_service)
        self.drone_status.setup_requested.connect(self.drone_setup_requested)
        layout.addWidget(self.drone_status)
        
        return group

    @staticmethod
    def _is_drone(obj) -> bool:
        return bool(obj.tracked or obj.mavlink_config.enabled)

    @staticmethod
    def _object_label(obj) -> str:
        parts = []
        if obj.tracked and obj.tracking_id:
            parts.append(f"tracked: {obj.tracking_id}")
        if obj.mavlink_config.enabled and obj.mavlink_config.linked_connection_name:
            parts.append(f"vehicle: {obj.mavlink_config.linked_connection_name}")
        return f"{obj.name}  ({' · '.join(parts)})" if parts else obj.name

    def select_object(self, obj):
        """Make ``obj`` the controlled object (selects it in the dropdown)."""
        self.refresh_object_list()
        index = next((i for i in range(self.object_combo.count()) if self.object_combo.itemData(i) is obj), -1)
        if index >= 0:
            self.object_combo.setCurrentIndex(index)

    @pyqtSlot(object)
    def _on_controlled_object_changed(self, obj):
        """Keep the dropdown in step when something else changes the controlled object."""
        index = next((i for i in range(self.object_combo.count()) if self.object_combo.itemData(i) is obj), 0)
        if index != self.object_combo.currentIndex():
            self.object_combo.blockSignals(True)
            self.object_combo.setCurrentIndex(index)
            self.object_combo.blockSignals(False)
        self.drone_status.set_object(obj)
    
    def _create_ghost_mode_section(self):
        """Create the ghost mode toggle and send position button."""
        group = QGroupBox("Ghost Mode")
        layout = QVBoxLayout(group)
        
        # Ghost mode description
        desc = QLabel("Ghost mode shows 'Next Setpoint' for previewing movements before applying.")
        desc.setWordWrap(True)
        desc.setProperty("role", "hint")
        layout.addWidget(desc)
        
        # Ghost mode checkbox and send button row
        row = QHBoxLayout()
        
        self.ghost_checkbox = QCheckBox("Enable Ghost Mode")
        self.ghost_checkbox.stateChanged.connect(self._on_ghost_mode_changed)
        row.addWidget(self.ghost_checkbox)
        
        row.addStretch()
        
        self.send_position_btn = theme.button("Send Position", "primary", "play")
        self.send_position_btn.setEnabled(False)  # Disabled until there's a difference
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
        
        minus_btn = theme.tool_button("minus", "Step down")
        minus_btn.setProperty("variant", "outline")
        minus_btn.setFixedSize(30, 30)
        minus_btn.clicked.connect(lambda: self._jog_axis(axis, -1))
        row.addWidget(minus_btn)
        
        value_label = QLabel("0.0000")
        value_label.setAlignment(Qt.AlignCenter)
        value_label.setFixedWidth(70)
        value_label.setProperty("role", "value")
        row.addWidget(value_label)
        
        plus_btn = theme.tool_button("plus", "Step up")
        plus_btn.setProperty("variant", "outline")
        plus_btn.setFixedSize(30, 30)
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
        self.go_to_target_btn = theme.button("Go to Target", "primary", "target", "lg")
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
        self.home_x_label.setProperty("role", "value")
        home_layout.addRow("X:", self.home_x_label)
        
        self.home_z_label = QLabel("0.000")
        self.home_z_label.setProperty("role", "value")
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
        self.set_home_btn = theme.button("Set Current Position as Home", None, "locate-fixed")
        self.set_home_btn.clicked.connect(self._on_set_home_clicked)
        layout.addWidget(self.set_home_btn)
        
        # Go Home button
        self.go_home_btn = theme.button("Go to Home", "success", "house", "lg")
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
        info.setProperty("role", "hint")
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
        self.mapping_info.setProperty("role", "hint")
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
        group = QGroupBox("Pose Info")
        main_layout = QVBoxLayout(group)
        
        # Header row
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addWidget(QLabel(""))
        header_layout.addWidget(QLabel("<b>Current</b>"))
        header_layout.addWidget(QLabel("<b>Setpoint</b>"))
        
        self.next_setpoint_header = QLabel("<b>Next</b>")
        self.next_setpoint_header.setProperty("tone", "accent")
        self.next_setpoint_header.hide()  # Hidden by default, shown in ghost mode
        header_layout.addWidget(self.next_setpoint_header)
        main_layout.addWidget(header)
        
        
        # Create position rows with all three columns
        self.next_setpoint_labels = []  # Store references to hide/show
        
        # X row
        x_row = QWidget()
        x_layout = QHBoxLayout(x_row)
        x_layout.setContentsMargins(0, 0, 0, 0)
        x_layout.addWidget(QLabel("X:"))
        self.pos_x_label = QLabel("0.0000")
        self.pos_x_label.setProperty("role", "value")
        x_layout.addWidget(self.pos_x_label)
        self.setpoint_x_label = QLabel("0.0000")
        self.setpoint_x_label.setProperty("role", "value")
        x_layout.addWidget(self.setpoint_x_label)
        self.next_x_label = QLabel("0.0000")
        self.next_x_label.setProperty("role", "value")
        self.next_x_label.setProperty("tone", "accent")
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
        self.pos_y_label.setProperty("role", "value")
        y_layout.addWidget(self.pos_y_label)
        self.setpoint_y_label = QLabel("0.0000")
        self.setpoint_y_label.setProperty("role", "value")
        y_layout.addWidget(self.setpoint_y_label)
        self.next_y_label = QLabel("0.0000")
        self.next_y_label.setProperty("role", "value")
        self.next_y_label.setProperty("tone", "accent")
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
        self.pos_z_label.setProperty("role", "value")
        z_layout.addWidget(self.pos_z_label)
        self.setpoint_z_label = QLabel("0.0000")
        self.setpoint_z_label.setProperty("role", "value")
        z_layout.addWidget(self.setpoint_z_label)
        self.next_z_label = QLabel("0.0000")
        self.next_z_label.setProperty("role", "value")
        self.next_z_label.setProperty("tone", "accent")
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
        self.rot_qx_label.setProperty("role", "value")
        qx_layout.addWidget(self.rot_qx_label)
        self.setpoint_qx_label = QLabel("0.0000")
        self.setpoint_qx_label.setProperty("role", "value")
        qx_layout.addWidget(self.setpoint_qx_label)
        self.next_qx_label = QLabel("0.0000")
        self.next_qx_label.setProperty("role", "value")
        self.next_qx_label.setProperty("tone", "accent")
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
        self.rot_qy_label.setProperty("role", "value")
        qy_layout.addWidget(self.rot_qy_label)
        self.setpoint_qy_label = QLabel("0.0000")
        self.setpoint_qy_label.setProperty("role", "value")
        qy_layout.addWidget(self.setpoint_qy_label)
        self.next_qy_label = QLabel("0.0000")
        self.next_qy_label.setProperty("role", "value")
        self.next_qy_label.setProperty("tone", "accent")
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
        self.rot_qz_label.setProperty("role", "value")
        qz_layout.addWidget(self.rot_qz_label)
        self.setpoint_qz_label = QLabel("0.0000")
        self.setpoint_qz_label.setProperty("role", "value")
        qz_layout.addWidget(self.setpoint_qz_label)
        self.next_qz_label = QLabel("0.0000")
        self.next_qz_label.setProperty("role", "value")
        self.next_qz_label.setProperty("tone", "accent")
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
        
        This is a safety button so it IGNORES ghost mode and sets the setpoint
        directly.
        """
        self.mode_tabs.setCurrentIndex(self.MODE_HOME)
        obj = self._get_controlled_object()
        if obj is not None:
            self.control.set_setpoint_now(obj, self._home_pose(obj))
        self.go_home_requested.emit()

    def _home_pose(self, obj):
        """Home position at hover height, keeping the current target orientation."""
        current = self.control.target(obj)
        return (self.home_position[0], self.hover_height_spin.value(), self.home_position[1], *current[3:])
    
    def _on_mode_changed(self, index):
        """Handle mode tab change."""
        self.current_mode = index
        # Joystick control is enabled when in joystick mode (always live now, ghost mode just affects preview)
        is_joystick_mode = (index == self.MODE_JOYSTICK)
        self.joystick_control_enabled.emit(is_joystick_mode)
    
    def _on_object_selected(self, index):
        """Handle controlled object selection."""
        obj = self.object_combo.itemData(index)
        self.drone_status.set_object(obj)
        if obj is None:
            # "— None —" selected — clear controlled object and disable input
            if self.object_service:
                self.object_service.clear_controlled_object()
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
    
    @property
    def ghost_mode(self) -> bool:
        return self.control.ghost_mode

    @property
    def setpoint(self):
        obj = self._get_controlled_object()
        return list(self.control.setpoint(obj)) if obj is not None else list(frames.IDENTITY_POSE)

    @property
    def next_setpoint(self):
        obj = self._get_controlled_object()
        return list(self.control.ghost(obj)) if obj is not None else list(frames.IDENTITY_POSE)

    def _on_ghost_mode_changed(self, state):
        """Handle ghost mode toggle."""
        enabled = state == Qt.Checked
        self.control.set_ghost_mode(enabled)
        self.ghost_mode_changed.emit(enabled)
        
        # Show/hide next setpoint column
        self.next_setpoint_header.setVisible(enabled)
        for label in self.next_setpoint_labels:
            label.setVisible(enabled)
        self.refresh()
    
    def _on_send_position_clicked(self):
        """Ghost mode: commit the "next" setpoint so the object goes there."""
        obj = self._get_controlled_object()
        if obj is None:
            return
        self.send_position_requested.emit(tuple(self.control.commit_ghost(obj)))
    
    def _on_step_size_changed(self, value):
        """Handle step size change."""
        self.step_size = value
    
    def _jog_axis(self, axis, direction):
        """Jog the setpoint (the "next" setpoint in ghost mode) along/around an axis."""
        obj = self._get_controlled_object()
        if obj is None:
            return
        step = self.step_size * direction
        if axis in ("X", "Y", "Z"):
            delta = [0.0, 0.0, 0.0]
            delta["XYZ".index(axis)] = step
            self.control.move_target(obj, delta)
        else:
            angle = math.radians(step * self.ROTATION_DEG_PER_STEP_UNIT)
            self.control.move_target(obj, rotation=frames.quat_from_axis_angle(self.ROTATION_AXES[axis], angle))
    
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
        
        current = self.control.target(obj)
        self.control.set_target(obj, (x, y, z, *current[3:]))
    
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
        """Handle go home button click in the home tab (respects ghost mode)."""
        obj = self._get_controlled_object()
        if obj is not None:
            self.control.set_target(obj, self._home_pose(obj))
    
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
        """Start commanding the controlled object from where it is now."""
        obj = self._get_controlled_object()
        if obj is not None and self.control.state(obj) is None:
            self.control.sync_from_object(obj)

    def _on_setpoints_changed(self, obj):
        if obj is self._get_controlled_object():
            self.refresh()
    
    def _update_send_button_state(self):
        """Send Position is only enabled in ghost mode while a move is pending."""
        obj = self._get_controlled_object()
        self.send_position_btn.setEnabled(obj is not None and self.control.has_pending_ghost(obj))
    
    def _update_position_display(self):
        """Update the position display with current, setpoint, and next setpoint (ghost mode)."""
        obj = self._get_controlled_object()
        if obj is None:
            return
        setpoint, ghost = self.setpoint, self.next_setpoint
        
        # Current position (from object - updated by tracking or when setpoint applied)
        self.pos_x_label.setText(f"{obj.pose[0]:.4f}")
        self.pos_y_label.setText(f"{obj.pose[1]:.4f}")
        self.pos_z_label.setText(f"{obj.pose[2]:.4f}")
        self.rot_qx_label.setText(f"{obj.pose[4]:.4f}")
        self.rot_qy_label.setText(f"{obj.pose[5]:.4f}")
        self.rot_qz_label.setText(f"{obj.pose[6]:.4f}")
        
        # Setpoint (what we're commanding)
        self.setpoint_x_label.setText(f"{setpoint[0]:.4f}")
        self.setpoint_y_label.setText(f"{setpoint[1]:.4f}")
        self.setpoint_z_label.setText(f"{setpoint[2]:.4f}")
        self.setpoint_qx_label.setText(f"{setpoint[4]:.4f}")
        self.setpoint_qy_label.setText(f"{setpoint[5]:.4f}")
        self.setpoint_qz_label.setText(f"{setpoint[6]:.4f}")
        
        # Next setpoint (ghost mode preview)
        if self.ghost_mode:
            self.next_x_label.setText(f"{ghost[0]:.4f}")
            self.next_y_label.setText(f"{ghost[1]:.4f}")
            self.next_z_label.setText(f"{ghost[2]:.4f}")
            self.next_qx_label.setText(f"{ghost[4]:.4f}")
            self.next_qy_label.setText(f"{ghost[5]:.4f}")
            self.next_qz_label.setText(f"{ghost[6]:.4f}")
    
    def _update_jog_values(self):
        """Show the setpoint being edited (the "next" one in ghost mode); angles in degrees."""
        target = self.next_setpoint if self.ghost_mode else self.setpoint
        rx, ry, rz = frames.quat_to_euler_deg(target[3:])
        self.jog_x_value.setText(f"{target[0]:.4f}")
        self.jog_y_value.setText(f"{target[1]:.4f}")
        self.jog_z_value.setText(f"{target[2]:.4f}")
        self.jog_roll_value.setText(f"{rx:.1f}°")
        self.jog_pitch_value.setText(f"{rz:.1f}°")
        self.jog_yaw_value.setText(f"{ry:.1f}°")
    
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

        controllable = [o for o in self.object_service.get_objects() if getattr(o, 'controllable', False)]
        # Real drones (tracked or with a flight controller) first, labelled.
        for obj in sorted(controllable, key=lambda o: not self._is_drone(o)):
            self.object_combo.addItem(self._object_label(obj), obj)

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
        
        self.drone_status.set_object(self.object_combo.currentData())

        # Sync setpoints and update displays
        self._sync_setpoints_from_object()
        self._update_position_display()
        self._update_jog_values()
    
    @pyqtSlot()
    def _on_display_timer(self):
        # A bound slot (not a lambda), so Qt drops the connection if the panel is destroyed.
        if self.isVisible():
            self.refresh()

    def refresh(self):
        """Refresh the panel display (called on input updates)."""
        self._update_send_button_state()
        self._update_position_display()
        self._update_jog_values()
    
    @pyqtSlot(object)
    def update_setpoint_from_joystick(self, pose_delta):
        """Move the setpoint (or the "next" setpoint in ghost mode) by a gamepad/keyboard delta.
        
        Args:
            pose_delta: [dx, dy, dz, unused, rx, ry, rz] — position in metres and a small
                rotation (scene axes) applied as a normalised incremental quaternion.
        """
        obj = self._get_controlled_object()
        if obj is None:
            return
        rotation = None
        if any(pose_delta[4:7]):
            rotation = frames.quat_normalize((1.0, *pose_delta[4:7]))
        self.control.move_target(obj, pose_delta[:3], rotation)
    
    def is_joystick_control_allowed(self):
        """Check if joystick control should move the object.
        
        Returns True when in Joystick mode. Joystick is now always "live",
        but ghost mode affects whether it updates next_setpoint or setpoint.
        """
        return self.current_mode == self.MODE_JOYSTICK
