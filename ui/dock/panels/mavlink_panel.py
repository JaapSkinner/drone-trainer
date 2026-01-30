"""
MAVLink Panel for displaying telemetry data and connection status.

This panel provides:
- Connection management UI with naming and object linking
- Device discovery for finding MAVLink devices on the network
- Real-time telemetry display with organized compact layout
- Connection health monitoring and testing
"""
from PyQt5.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QGroupBox, 
    QFormLayout, QPushButton, QLineEdit, QScrollArea, QFrame,
    QSpinBox, QTabWidget, QGridLayout, QComboBox, QMessageBox,
    QProgressBar, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSlot, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QPainter, QColor, QPen
import math

from models.structs import MavlinkConnectionConfig, MavlinkTelemetryData


class MiniPlot(QWidget):
    """Simple mini plot widget for telemetry visualization."""
    
    def __init__(self, parent=None, max_points: int = 50, 
                 min_val: float = -1.0, max_val: float = 1.0,
                 color: QColor = None):
        super().__init__(parent)
        self.max_points = max_points
        self.min_val = min_val
        self.max_val = max_val
        self.color = color or QColor(0, 150, 0)
        self.values = []
        self.setMinimumHeight(40)
        self.setMaximumHeight(50)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    
    def add_value(self, value: float):
        """Add a new value to the plot."""
        self.values.append(value)
        if len(self.values) > self.max_points:
            self.values.pop(0)
        self.update()
    
    def clear(self):
        """Clear all values."""
        self.values = []
        self.update()
    
    def paintEvent(self, event):
        """Draw the plot."""
        if not self.values:
            return
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Background
        painter.fillRect(self.rect(), QColor(40, 40, 40))
        
        # Draw zero line
        painter.setPen(QPen(QColor(80, 80, 80), 1))
        zero_y = self._value_to_y(0)
        painter.drawLine(0, zero_y, self.width(), zero_y)
        
        # Draw data
        painter.setPen(QPen(self.color, 2))
        
        w = self.width()
        h = self.height()
        
        if len(self.values) > 1:
            step = w / (self.max_points - 1)
            for i in range(1, len(self.values)):
                x1 = int((i - 1) * step + (self.max_points - len(self.values)) * step)
                x2 = int(i * step + (self.max_points - len(self.values)) * step)
                y1 = self._value_to_y(self.values[i - 1])
                y2 = self._value_to_y(self.values[i])
                painter.drawLine(x1, y1, x2, y2)
    
    def _value_to_y(self, value: float) -> int:
        """Convert value to Y coordinate."""
        h = self.height()
        # Clamp value
        value = max(self.min_val, min(self.max_val, value))
        # Normalize to 0-1 range (inverted for screen coords)
        # Handle case where min == max to avoid division by zero
        range_val = self.max_val - self.min_val
        if range_val == 0:
            normalized = 0.5
        else:
            normalized = 1.0 - (value - self.min_val) / range_val
        return int(normalized * h)


class ConnectionCard(QFrame):
    """Widget representing a single MAVLink connection."""
    
    # Signals for connection actions
    action_clicked = pyqtSignal(str)  # connection_name - for connect/disconnect
    link_object_clicked = pyqtSignal(str)  # connection_name
    test_clicked = pyqtSignal(str)  # connection_name
    
    def __init__(self, config: MavlinkConnectionConfig, is_active: bool = True, parent=None):
        super().__init__(parent)
        self.config = config
        self.is_active = is_active
        self._init_ui()
    
    def _init_ui(self):
        """Initialize the connection card UI."""
        self.setFrameStyle(QFrame.Box | QFrame.Raised)
        self.setLineWidth(1)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(8, 8, 8, 8)
        
        # Header row with name and status
        header = QHBoxLayout()
        
        # Connection name (editable)
        name = self.config.name or f"Connection-{self.config.system_id}"
        self.name_label = QLabel(f"<b>{name}</b>")
        self.name_label.setStyleSheet("font-size: 12px;")
        header.addWidget(self.name_label)
        
        header.addStretch()
        
        # Status indicator
        if self.is_active:
            status_text = "●"
            status_color = "green"
        else:
            status_text = "○"
            status_color = "gray"
        
        self.status_label = QLabel(status_text)
        self.status_label.setStyleSheet(f"color: {status_color}; font-size: 14px;")
        header.addWidget(self.status_label)
        
        layout.addLayout(header)
        
        # Connection details
        details = QLabel(f"{self.config.connection_string} | ID: {self.config.system_id}")
        details.setStyleSheet("color: #666; font-size: 10px;")
        layout.addWidget(details)
        
        # Linked object
        linked = self.config.linked_object_name
        if linked:
            self.linked_label = QLabel(f"Linked: <b>{linked}</b>")
        else:
            self.linked_label = QLabel("Not linked to object")
        self.linked_label.setStyleSheet("color: #888; font-size: 10px;")
        layout.addWidget(self.linked_label)
        
        # Button row
        buttons = QHBoxLayout()
        buttons.setSpacing(4)
        
        # Link/Unlink object button
        link_text = "Change Object" if linked else "Link Object"
        self.link_btn = QPushButton(link_text)
        self.link_btn.setFixedHeight(24)
        self.link_btn.clicked.connect(lambda: self.link_object_clicked.emit(self.config.name))
        buttons.addWidget(self.link_btn)
        
        if self.is_active:
            # Test button
            test_btn = QPushButton("Test")
            test_btn.setFixedHeight(24)
            test_btn.clicked.connect(lambda: self.test_clicked.emit(self.config.name))
            buttons.addWidget(test_btn)
            
            # Disconnect button
            disconnect_btn = QPushButton("Disconnect")
            disconnect_btn.setFixedHeight(24)
            disconnect_btn.setStyleSheet("color: #c00;")
            disconnect_btn.clicked.connect(lambda: self.action_clicked.emit(self.config.name))
            buttons.addWidget(disconnect_btn)
        else:
            # Connect button for inactive connections
            connect_btn = QPushButton("Connect")
            connect_btn.setFixedHeight(24)
            connect_btn.setStyleSheet("color: #0a0;")
            connect_btn.clicked.connect(lambda: self.action_clicked.emit(self.config.name))
            buttons.addWidget(connect_btn)
        
        layout.addLayout(buttons)
        
        # Style the frame
        bg_color = "#f5f5f5" if self.is_active else "#e0e0e0"
        self.setStyleSheet(f"""
            ConnectionCard {{
                background-color: {bg_color};
                border-radius: 4px;
            }}
        """)
    
    def update_linked_object(self, object_name: str):
        """Update the linked object display."""
        self.config.linked_object_name = object_name
        if object_name:
            self.linked_label.setText(f"Linked: <b>{object_name}</b>")
            self.link_btn.setText("Change Object")
        else:
            self.linked_label.setText("Not linked to object")
            self.link_btn.setText("Link Object")


class MavlinkPanel(QWidget):
    """Panel for MAVLink connection management and telemetry display.
    
    Provides UI for:
    - Adding/removing drone connections with naming
    - Linking connections to scene objects
    - Device discovery on the network
    - Viewing real-time telemetry data with plots
    - Monitoring connection health
    
    Signals:
        object_link_requested: Emitted when linking connection to object
    """
    NavTag = "mavlink"
    
    # Signal emitted when a connection-object link is requested
    object_link_requested = pyqtSignal(str, str)  # connection_name, object_name
    
    # Connection quality thresholds for test results
    GOOD_RATE_HZ = 50       # Minimum Hz for 'good' rating
    GOOD_LATENCY_MS = 50    # Maximum latency for 'good' rating
    FAIR_RATE_HZ = 20       # Minimum Hz for 'fair' rating
    FAIR_LATENCY_MS = 100   # Maximum latency for 'fair' rating
    
    def __init__(self, parent=None, mavlink_service=None, object_service=None):
        """Initialize the MAVLink panel.
        
        Args:
            parent: Parent widget
            mavlink_service: MAVLink service instance
            object_service: Object service for linking
        """
        super().__init__(parent)
        self.mavlink_service = mavlink_service
        self.object_service = object_service
        self._telemetry_data: dict = {}  # system_id -> TelemetryData
        self._connection_cards: dict = {}  # connection_name -> ConnectionCard
        self._mini_plots: dict = {}  # system_id -> {field_name: MiniPlot}
        self._telemetry_labels: dict = {}
        
        self.init_ui()
        
        # Connect to mavlink service signals if available
        if self.mavlink_service is not None:
            self.mavlink_service.telemetry_updated.connect(self.on_telemetry_updated)
            self.mavlink_service.connection_changed.connect(self.on_connection_changed)
            self.mavlink_service.health_updated.connect(self.on_health_updated)
    
    def init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignTop)
        
        # Title
        title = QLabel("MAVLink Control")
        title.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title)
        
        # Tab widget for different sections
        tabs = QTabWidget()
        
        # Connection tab
        connection_tab = self._create_connection_tab()
        tabs.addTab(connection_tab, "Connections")
        
        # Telemetry tab
        telemetry_tab = self._create_telemetry_tab()
        tabs.addTab(telemetry_tab, "Telemetry")
        
        # Status tab
        status_tab = self._create_status_tab()
        tabs.addTab(status_tab, "Status")
        
        layout.addWidget(tabs)
    
    def _create_connection_tab(self) -> QWidget:
        """Create the connection management tab with discovery and object linking."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(8)
        
        # === Add Connection Section ===
        form_group = QGroupBox("Add Connection")
        form_layout = QFormLayout()
        form_layout.setSpacing(6)
        
        # Connection name input
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Auto-generated if empty")
        form_layout.addRow("Name:", self.name_input)
        
        # Connection string input (updated default)
        self.connection_input = QLineEdit()
        self.connection_input.setPlaceholderText("udpin:0.0.0.0:14550")
        self.connection_input.setText("udpin:0.0.0.0:14550")
        form_layout.addRow("Address:", self.connection_input)
        
        # System ID input
        self.system_id_input = QSpinBox()
        self.system_id_input.setRange(1, 255)
        self.system_id_input.setValue(1)
        form_layout.addRow("System ID:", self.system_id_input)
        
        # Button row
        btn_row = QHBoxLayout()
        
        # Discover devices button
        self.discover_btn = QPushButton("Discover Devices")
        self.discover_btn.clicked.connect(self.on_discover_clicked)
        btn_row.addWidget(self.discover_btn)
        
        # Connect button
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.on_connect_clicked)
        btn_row.addWidget(self.connect_btn)
        
        form_layout.addRow("", btn_row)
        
        form_group.setLayout(form_layout)
        layout.addWidget(form_group)
        
        # === Discovered Devices Section (initially hidden) ===
        self.discovered_group = QGroupBox("Discovered Devices")
        self.discovered_layout = QVBoxLayout()
        self.discovered_label = QLabel("Click 'Discover Devices' to scan network")
        self.discovered_label.setStyleSheet("color: #666; font-style: italic;")
        self.discovered_layout.addWidget(self.discovered_label)
        self.discovered_group.setLayout(self.discovered_layout)
        self.discovered_group.setVisible(False)  # Hidden until discovery is run
        layout.addWidget(self.discovered_group)
        
        # === Connections List Section ===
        connections_group = QGroupBox("Connections")
        connections_scroll = QScrollArea()
        connections_scroll.setWidgetResizable(True)
        connections_scroll.setFrameShape(QFrame.NoFrame)
        connections_scroll.setMaximumHeight(250)
        
        self.connections_container = QWidget()
        self.connections_layout = QVBoxLayout(self.connections_container)
        self.connections_layout.setSpacing(6)
        self.connections_layout.setContentsMargins(0, 0, 0, 0)
        
        self.no_connections_label = QLabel("No connections configured")
        self.no_connections_label.setStyleSheet("color: #666; font-style: italic;")
        self.connections_layout.addWidget(self.no_connections_label)
        self.connections_layout.addStretch()
        
        connections_scroll.setWidget(self.connections_container)
        
        group_layout = QVBoxLayout(connections_group)
        group_layout.addWidget(connections_scroll)
        
        layout.addWidget(connections_group)
        
        # === Connection Test Section ===
        test_group = QGroupBox("Connection Quality")
        test_layout = QVBoxLayout()
        
        test_btn_row = QHBoxLayout()
        self.test_connection_btn = QPushButton("Test All Connections")
        self.test_connection_btn.clicked.connect(self.on_test_connection_clicked)
        self.test_connection_btn.setEnabled(False)
        test_btn_row.addWidget(self.test_connection_btn)
        test_layout.addLayout(test_btn_row)
        
        self.test_results_label = QLabel("")
        self.test_results_label.setWordWrap(True)
        self.test_results_label.setStyleSheet("font-size: 11px; padding: 5px;")
        test_layout.addWidget(self.test_results_label)
        
        test_group.setLayout(test_layout)
        layout.addWidget(test_group)
        
        layout.addStretch()
        return widget
    
    def on_discover_clicked(self):
        """Handle discover devices button click."""
        self.discovered_group.setVisible(True)
        self.discover_btn.setEnabled(False)
        self.discover_btn.setText("Discovering...")
        
        # Clear previous results
        while self.discovered_layout.count() > 0:
            child = self.discovered_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        progress = QLabel("Scanning network for MAVLink devices...")
        progress.setStyleSheet("color: #666;")
        self.discovered_layout.addWidget(progress)
        
        # Use a timer to make UI responsive
        QTimer.singleShot(100, self._run_discovery)
    
    def _run_discovery(self):
        """Run device discovery in background."""
        if self.mavlink_service is None:
            self._show_discovery_error("MAVLink service not available")
            return
        
        try:
            devices = self.mavlink_service.discover_devices(timeout_secs=2.0)
            
            # Clear layout
            while self.discovered_layout.count() > 0:
                child = self.discovered_layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
            
            if not devices:
                no_devices = QLabel("No devices found. Make sure drones are powered on.")
                no_devices.setStyleSheet("color: #888;")
                self.discovered_layout.addWidget(no_devices)
            else:
                for device in devices:
                    row = QHBoxLayout()
                    label = QLabel(f"{device.connection_string}")
                    row.addWidget(label)
                    row.addStretch()
                    
                    use_btn = QPushButton("Use")
                    use_btn.clicked.connect(
                        lambda checked, d=device: self._use_discovered_device(d)
                    )
                    row.addWidget(use_btn)
                    
                    row_widget = QWidget()
                    row_widget.setLayout(row)
                    self.discovered_layout.addWidget(row_widget)
            
        except Exception as e:
            self._show_discovery_error(str(e))
        finally:
            self.discover_btn.setEnabled(True)
            self.discover_btn.setText("Discover Devices")
    
    def _show_discovery_error(self, message: str):
        """Show discovery error message."""
        while self.discovered_layout.count() > 0:
            child = self.discovered_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        error = QLabel(f"Discovery failed: {message}")
        error.setStyleSheet("color: red;")
        self.discovered_layout.addWidget(error)
        
        self.discover_btn.setEnabled(True)
        self.discover_btn.setText("Discover Devices")
    
    def _use_discovered_device(self, device):
        """Use a discovered device's connection string."""
        self.connection_input.setText(device.connection_string)
        if device.system_id > 0:
            self.system_id_input.setValue(device.system_id)
    
    def on_test_connection_clicked(self):
        """Run a connection quality test.
        
        Tests packet rate by sending a burst of messages and measuring response times.
        """
        if self.mavlink_service is None:
            return
        
        active_conns = self.mavlink_service.get_connection_count()
        if active_conns == 0:
            self.test_results_label.setText("<span style='color: red;'>No active connections to test</span>")
            return
        
        self.test_results_label.setText("<span style='color: orange;'>Testing connection quality...</span>")
        self.test_connection_btn.setEnabled(False)
        
        # Get test results from service
        try:
            test_results = self.mavlink_service.run_connection_test()
            
            result_text = "<b>Test Results:</b><br>"
            for sys_id, result in test_results.items():
                rate_hz = result.get('rate_hz', 0)
                latency_ms = result.get('latency_ms', 0)
                lost_packets = result.get('lost_packets', 0)
                
                # Color code based on quality thresholds
                if rate_hz >= self.GOOD_RATE_HZ and latency_ms < self.GOOD_LATENCY_MS and lost_packets == 0:
                    color = 'green'
                    status = '✓ Good'
                elif rate_hz >= self.FAIR_RATE_HZ and latency_ms < self.FAIR_LATENCY_MS:
                    color = 'orange'
                    status = '◐ Fair'
                else:
                    color = 'red'
                    status = '✗ Poor'
                
                result_text += f"<span style='color: {color};'><b>ID {sys_id}:</b> {status}</span> "
                result_text += f"({rate_hz:.0f}Hz, {latency_ms:.0f}ms)<br>"
            
            self.test_results_label.setText(result_text)
            
        except Exception as e:
            self.test_results_label.setText(f"<span style='color: red;'>Test failed: {str(e)}</span>")
        finally:
            self.test_connection_btn.setEnabled(True)
    
    def _create_telemetry_tab(self) -> QWidget:
        """Create the telemetry display tab with compact organized layout and plots."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(6)
        
        # Scroll area for telemetry data
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        
        content = QWidget()
        self.telemetry_layout = QVBoxLayout(content)
        self.telemetry_layout.setSpacing(8)
        
        # Placeholder for telemetry display
        self.telemetry_placeholder = QLabel("Connect to a drone to view telemetry")
        self.telemetry_placeholder.setStyleSheet("color: #666; font-style: italic;")
        self.telemetry_placeholder.setAlignment(Qt.AlignCenter)
        self.telemetry_layout.addWidget(self.telemetry_placeholder)
        
        self.telemetry_layout.addStretch()
        
        scroll.setWidget(content)
        layout.addWidget(scroll)
        
        return widget
    
    def _create_telemetry_widget(self, system_id: int) -> QGroupBox:
        """Create an improved telemetry display widget with plots for a drone."""
        group = QGroupBox(f"Drone {system_id}")
        main_layout = QVBoxLayout()
        main_layout.setSpacing(4)
        
        labels = {}
        plots = {}
        
        # === Attitude Section with Plots ===
        attitude_layout = QHBoxLayout()
        
        # Attitude values (compact)
        att_values = QGridLayout()
        att_values.setSpacing(2)
        
        att_values.addWidget(QLabel("R:"), 0, 0)
        labels['roll'] = QLabel("0°")
        labels['roll'].setStyleSheet("font-weight: bold; min-width: 45px;")
        att_values.addWidget(labels['roll'], 0, 1)
        
        att_values.addWidget(QLabel("P:"), 0, 2)
        labels['pitch'] = QLabel("0°")
        labels['pitch'].setStyleSheet("font-weight: bold; min-width: 45px;")
        att_values.addWidget(labels['pitch'], 0, 3)
        
        att_values.addWidget(QLabel("Y:"), 0, 4)
        labels['yaw'] = QLabel("0°")
        labels['yaw'].setStyleSheet("font-weight: bold; min-width: 45px;")
        att_values.addWidget(labels['yaw'], 0, 5)
        
        attitude_layout.addLayout(att_values)
        
        # Attitude mini plot (roll/pitch)
        plots['attitude'] = MiniPlot(min_val=-45, max_val=45, color=QColor(0, 150, 200))
        attitude_layout.addWidget(plots['attitude'], stretch=1)
        
        main_layout.addLayout(attitude_layout)
        
        # === Position Section ===
        pos_layout = QHBoxLayout()
        
        pos_values = QGridLayout()
        pos_values.setSpacing(2)
        
        pos_values.addWidget(QLabel("X:"), 0, 0)
        labels['x'] = QLabel("0.0m")
        labels['x'].setStyleSheet("font-weight: bold; min-width: 50px;")
        pos_values.addWidget(labels['x'], 0, 1)
        
        pos_values.addWidget(QLabel("Y:"), 0, 2)
        labels['y'] = QLabel("0.0m")
        labels['y'].setStyleSheet("font-weight: bold; min-width: 50px;")
        pos_values.addWidget(labels['y'], 0, 3)
        
        pos_values.addWidget(QLabel("Z:"), 0, 4)
        labels['z'] = QLabel("0.0m")
        labels['z'].setStyleSheet("font-weight: bold; min-width: 50px;")
        pos_values.addWidget(labels['z'], 0, 5)
        
        pos_layout.addLayout(pos_values)
        
        # Altitude mini plot
        plots['altitude'] = MiniPlot(min_val=-10, max_val=10, color=QColor(200, 100, 0))
        pos_layout.addWidget(plots['altitude'], stretch=1)
        
        main_layout.addLayout(pos_layout)
        
        # === Velocity Section (compact single row) ===
        vel_layout = QHBoxLayout()
        vel_layout.addWidget(QLabel("Vel:"))
        
        labels['vx'] = QLabel("0.0")
        labels['vx'].setStyleSheet("min-width: 35px;")
        vel_layout.addWidget(labels['vx'])
        
        labels['vy'] = QLabel("0.0")
        labels['vy'].setStyleSheet("min-width: 35px;")
        vel_layout.addWidget(labels['vy'])
        
        labels['vz'] = QLabel("0.0")
        labels['vz'].setStyleSheet("min-width: 35px;")
        vel_layout.addWidget(labels['vz'])
        
        vel_layout.addWidget(QLabel("m/s"))
        vel_layout.addStretch()
        
        main_layout.addLayout(vel_layout)
        
        # === Status Row (compact) ===
        status_layout = QHBoxLayout()
        status_layout.setSpacing(10)
        
        # Armed status
        labels['armed'] = QLabel("⬡ Disarmed")
        labels['armed'].setStyleSheet("color: green;")
        status_layout.addWidget(labels['armed'])
        
        # Battery
        labels['battery'] = QLabel("🔋 --V")
        status_layout.addWidget(labels['battery'])
        
        # GPS
        labels['gps'] = QLabel("📡 --")
        status_layout.addWidget(labels['gps'])
        
        # Mode
        labels['mode'] = QLabel("Mode: --")
        labels['mode'].setStyleSheet("color: #666;")
        status_layout.addWidget(labels['mode'])
        
        status_layout.addStretch()
        
        main_layout.addLayout(status_layout)
        
        # === Rates Row (additional data) ===
        rates_layout = QHBoxLayout()
        rates_layout.setSpacing(10)
        
        rates_layout.addWidget(QLabel("Rates:"))
        labels['rollspeed'] = QLabel("R: 0°/s")
        labels['rollspeed'].setStyleSheet("color: #666; font-size: 10px;")
        rates_layout.addWidget(labels['rollspeed'])
        
        labels['pitchspeed'] = QLabel("P: 0°/s")
        labels['pitchspeed'].setStyleSheet("color: #666; font-size: 10px;")
        rates_layout.addWidget(labels['pitchspeed'])
        
        labels['yawspeed'] = QLabel("Y: 0°/s")
        labels['yawspeed'].setStyleSheet("color: #666; font-size: 10px;")
        rates_layout.addWidget(labels['yawspeed'])
        
        rates_layout.addStretch()
        main_layout.addLayout(rates_layout)
        
        group.setLayout(main_layout)
        
        # Store labels and plots for updates
        labels['widget'] = group
        self._telemetry_labels[system_id] = labels
        self._mini_plots[system_id] = plots
        
        return group
    
    def _update_telemetry_display(self, system_id: int, telemetry: MavlinkTelemetryData):
        """Update the telemetry display for a specific drone."""
        if system_id not in self._telemetry_labels:
            # Create new widget
            widget = self._create_telemetry_widget(system_id)
            self.telemetry_layout.insertWidget(0, widget)
            self.telemetry_placeholder.hide()
        
        labels = self._telemetry_labels[system_id]
        plots = self._mini_plots.get(system_id, {})
        
        # Convert radians to degrees for display
        roll_deg = math.degrees(telemetry.roll)
        pitch_deg = math.degrees(telemetry.pitch)
        yaw_deg = math.degrees(telemetry.yaw)
        
        # Update attitude
        labels['roll'].setText(f"{roll_deg:.1f}°")
        labels['pitch'].setText(f"{pitch_deg:.1f}°")
        labels['yaw'].setText(f"{yaw_deg:.1f}°")
        
        # Update attitude plot with roll value
        if 'attitude' in plots:
            plots['attitude'].add_value(roll_deg)
        
        # Update position
        labels['x'].setText(f"{telemetry.x:.1f}m")
        labels['y'].setText(f"{telemetry.y:.1f}m")
        labels['z'].setText(f"{telemetry.z:.1f}m")
        
        # Update altitude plot (negative Z in NED = altitude)
        if 'altitude' in plots:
            plots['altitude'].add_value(-telemetry.z)
        
        # Update velocity
        labels['vx'].setText(f"{telemetry.vx:.1f}")
        labels['vy'].setText(f"{telemetry.vy:.1f}")
        labels['vz'].setText(f"{telemetry.vz:.1f}")
        
        # Update angular rates
        labels['rollspeed'].setText(f"R: {math.degrees(telemetry.rollspeed):.1f}°/s")
        labels['pitchspeed'].setText(f"P: {math.degrees(telemetry.pitchspeed):.1f}°/s")
        labels['yawspeed'].setText(f"Y: {math.degrees(telemetry.yawspeed):.1f}°/s")
        
        # Update status
        if telemetry.armed:
            labels['armed'].setText("⬢ ARMED")
            labels['armed'].setStyleSheet("color: red; font-weight: bold;")
        else:
            labels['armed'].setText("⬡ Disarmed")
            labels['armed'].setStyleSheet("color: green;")
        
        # Battery with color coding
        bat_pct = telemetry.battery_remaining
        if bat_pct > 50:
            bat_color = "green"
        elif bat_pct > 20:
            bat_color = "orange"
        else:
            bat_color = "red"
        labels['battery'].setText(f"🔋 {telemetry.battery_voltage:.1f}V ({bat_pct}%)")
        labels['battery'].setStyleSheet(f"color: {bat_color};")
        
        # GPS fix type
        gps_text = {0: "No GPS", 1: "No Fix", 2: "2D", 3: "3D"}.get(
            telemetry.gps_fix_type, "?"
        )
        labels['gps'].setText(f"📡 {gps_text} ({telemetry.satellites_visible})")
        
        # Mode
        labels['mode'].setText(f"Mode: {telemetry.mode}")
    
    def _create_status_tab(self) -> QWidget:
        """Create the status monitoring tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Health metrics group
        health_group = QGroupBox("Service Health")
        health_layout = QFormLayout()
        
        self.rate_label = QLabel("0 Hz")
        self.rate_label.setFont(QFont("NotoSans", 12, QFont.Bold))
        health_layout.addRow("Message Rate:", self.rate_label)
        
        self.connections_count_label = QLabel("0")
        self.connections_count_label.setFont(QFont("NotoSans", 12, QFont.Bold))
        health_layout.addRow("Active Connections:", self.connections_count_label)
        
        self.messages_sent_label = QLabel("0")
        health_layout.addRow("Messages Sent:", self.messages_sent_label)
        
        self.messages_received_label = QLabel("0")
        health_layout.addRow("Messages Received:", self.messages_received_label)
        
        health_group.setLayout(health_layout)
        layout.addWidget(health_group)
        
        # Dialect info group
        dialect_group = QGroupBox("MAVLink Dialect")
        dialect_layout = QFormLayout()
        
        # Get dialect info from service
        from services.mavlink_service import MavlinkService
        dialect_info = MavlinkService.get_dialect_info()
        
        self.dialect_label = QLabel(dialect_info['dialect_name'].upper())
        if dialect_info['using_dtrg']:
            self.dialect_label.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.dialect_label.setStyleSheet("color: orange; font-weight: bold;")
        dialect_layout.addRow("Active Dialect:", self.dialect_label)
        
        self.dtrg_status_label = QLabel("Available" if dialect_info['dtrg_available'] else "Not Found")
        if dialect_info['dtrg_available']:
            self.dtrg_status_label.setStyleSheet("color: green;")
        else:
            self.dtrg_status_label.setStyleSheet("color: red;")
        dialect_layout.addRow("DTRG Submodule:", self.dtrg_status_label)
        
        # Show if dialect is built
        dtrg_built = dialect_info.get('dtrg_built', False)
        self.dtrg_built_label = QLabel("Built" if dtrg_built else "Not Built")
        if dtrg_built:
            self.dtrg_built_label.setStyleSheet("color: green;")
        else:
            self.dtrg_built_label.setStyleSheet("color: orange;")
        dialect_layout.addRow("DTRG Dialect:", self.dtrg_built_label)
        
        dialect_group.setLayout(dialect_layout)
        layout.addWidget(dialect_group)
        
        # Info group
        info_group = QGroupBox("MAVLink Info")
        info_layout = QVBoxLayout()
        
        info_text = QLabel("""<b>Message Priorities:</b><br>
        • <span style='color: red;'>Critical</span>: Motion capture data<br>
        • <span style='color: orange;'>High</span>: Setpoint commands<br>
        • <span style='color: green;'>Normal</span>: Telemetry data<br>
        <br>
        <b>Rate Limits:</b><br>
        • Motion capture: 100 Hz<br>
        • Setpoints: 50 Hz<br>
        • Telemetry: 20 Hz<br>
        <br>
        <b>Build DTRG Dialect:</b><br>
        <code>python scripts/build_mavlink.py --dialect dtrg</code>""")
        info_text.setWordWrap(True)
        info_text.setStyleSheet("font-size: 11px; color: #555;")
        info_layout.addWidget(info_text)
        
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)
        
        layout.addStretch()
        return widget
    
    def on_connect_clicked(self):
        """Handle connect button click."""
        if self.mavlink_service is None:
            return
        
        connection_string = self.connection_input.text().strip()
        system_id = self.system_id_input.value()
        name = self.name_input.text().strip()
        
        if not connection_string:
            return
        
        config = MavlinkConnectionConfig(
            connection_string=connection_string,
            system_id=system_id,
            name=name  # Will be auto-generated if empty
        )
        
        # Try to connect
        self.connect_btn.setEnabled(False)
        self.connect_btn.setText("Connecting...")
        
        success = self.mavlink_service.add_connection(config)
        
        self.connect_btn.setEnabled(True)
        self.connect_btn.setText("Connect")
        
        if success:
            # Clear name input for next connection
            self.name_input.clear()
            self._refresh_connections_list()
    
    def _refresh_connections_list(self):
        """Refresh the connections list showing all active and inactive connections."""
        # Clear current connections
        while self.connections_layout.count() > 0:
            child = self.connections_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        self._connection_cards.clear()
        
        if self.mavlink_service is None:
            self.no_connections_label = QLabel("No connections configured")
            self.no_connections_label.setStyleSheet("color: #666; font-style: italic;")
            self.connections_layout.addWidget(self.no_connections_label)
            return
        
        # Get all connections (active and inactive)
        all_connections = self.mavlink_service.get_all_connections()
        
        if not all_connections:
            self.no_connections_label = QLabel("No connections configured")
            self.no_connections_label.setStyleSheet("color: #666; font-style: italic;")
            self.connections_layout.addWidget(self.no_connections_label)
            return
        
        # Add connection cards
        for name, config in all_connections.items():
            # Check if this connection is active
            conn = self.mavlink_service.get_connection_by_name(name)
            is_active = conn is not None and conn.is_connected
            
            card = ConnectionCard(config, is_active=is_active)
            card.action_clicked.connect(self._on_connection_action)
            card.link_object_clicked.connect(self._on_link_object_clicked)
            card.test_clicked.connect(self._on_test_single_connection)
            
            self._connection_cards[name] = card
            self.connections_layout.addWidget(card)
        
        self.connections_layout.addStretch()
    
    def _on_connection_action(self, connection_name: str):
        """Handle connect/disconnect action for a connection."""
        if self.mavlink_service is None:
            return
        
        conn = self.mavlink_service.get_connection_by_name(connection_name)
        
        if conn is not None and conn.is_connected:
            # Disconnect
            self.mavlink_service.remove_connection(conn.config.system_id)
        else:
            # Connect - get saved config or create new
            all_conns = self.mavlink_service.get_all_connections()
            if connection_name in all_conns:
                config = all_conns[connection_name]
                self.mavlink_service.add_connection(config)
        
        self._refresh_connections_list()
    
    def _on_link_object_clicked(self, connection_name: str):
        """Handle link object button click - show object selection dialog."""
        if self.object_service is None:
            QMessageBox.warning(self, "No Objects", "Object service not available.")
            return
        
        objects = self.object_service.get_objects()
        controllable_objects = [obj for obj in objects if getattr(obj, 'controllable', False)]
        
        if not controllable_objects:
            QMessageBox.information(self, "No Objects", "No controllable objects available to link.")
            return
        
        # Create a simple selection dialog using combo box
        from PyQt5.QtWidgets import QDialog, QDialogButtonBox
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Link Object to Connection")
        dialog_layout = QVBoxLayout(dialog)
        
        dialog_layout.addWidget(QLabel(f"Select object to link to '{connection_name}':"))
        
        combo = QComboBox()
        combo.addItem("(None - Unlink)", "")
        for obj in controllable_objects:
            combo.addItem(obj.name, obj.name)
        
        # Pre-select current linked object
        current_linked = self.mavlink_service.get_linked_object_name(connection_name) if self.mavlink_service else ""
        if current_linked:
            idx = combo.findData(current_linked)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        
        dialog_layout.addWidget(combo)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        dialog_layout.addWidget(buttons)
        
        if dialog.exec_() == QDialog.Accepted:
            selected_name = combo.currentData()
            if self.mavlink_service:
                if selected_name:
                    self.mavlink_service.link_connection_to_object(connection_name, selected_name)
                else:
                    self.mavlink_service.unlink_connection_from_object(connection_name)
                
                # Update the card
                if connection_name in self._connection_cards:
                    self._connection_cards[connection_name].update_linked_object(selected_name)
                
                # Emit signal for other panels
                self.object_link_requested.emit(connection_name, selected_name)
    
    def _on_test_single_connection(self, connection_name: str):
        """Test a single connection."""
        if self.mavlink_service is None:
            return
        
        conn = self.mavlink_service.get_connection_by_name(connection_name)
        if conn is None:
            return
        
        results = self.mavlink_service.run_connection_test()
        sys_id = conn.config.system_id
        
        if sys_id in results:
            result = results[sys_id]
            quality = result.get('quality', 'unknown')
            rate = result.get('rate_hz', 0)
            latency = result.get('latency_ms', 0)
            
            QMessageBox.information(
                self, 
                f"Connection Test - {connection_name}",
                f"Quality: {quality.upper()}\nRate: {rate:.1f} Hz\nLatency: {latency:.1f} ms"
            )
    
    def _add_connection_widget(self, system_id: int, connection_string: str):
        """Legacy method - now calls _refresh_connections_list instead."""
        self._refresh_connections_list()
    
    def _disconnect(self, system_id: int):
        """Disconnect and remove a connection.
        
        Args:
            system_id: System ID of the connection to disconnect
        """
        if self.mavlink_service is not None:
            self.mavlink_service.remove_connection(system_id)
        
        # Remove telemetry display if exists
        if system_id in self._telemetry_labels:
            widget = self._telemetry_labels[system_id].get('widget')
            if widget:
                widget.deleteLater()
            del self._telemetry_labels[system_id]
        
        # Remove plots
        if system_id in self._mini_plots:
            del self._mini_plots[system_id]
        
        self._refresh_connections_list()
    
    def refresh_telemetry_display(self):
        """Refresh the telemetry display with current data."""
        if self.mavlink_service is None:
            return
        
        for system_id, telemetry in self.mavlink_service.get_all_telemetry().items():
            self._update_telemetry_display(system_id, telemetry)
    
    @pyqtSlot(int, object)
    def on_telemetry_updated(self, system_id: int, telemetry: MavlinkTelemetryData):
        """Handle telemetry update from mavlink service."""
        self._update_telemetry_display(system_id, telemetry)
    
    @pyqtSlot(int, bool)
    def on_connection_changed(self, system_id: int, connected: bool):
        """Handle connection state change."""
        # Refresh connections list to reflect new state
        self._refresh_connections_list()
    
    @pyqtSlot(float, int)
    def on_health_updated(self, rate_hz: float, active_connections: int):
        """Handle health metrics update."""
        self.rate_label.setText(f"{rate_hz:.0f} Hz")
        self.connections_count_label.setText(str(active_connections))
        
        # Enable/disable test button based on connections
        self.test_connection_btn.setEnabled(active_connections > 0)
        
        # Update no connections label visibility
        self.no_connections_label.setVisible(active_connections == 0)
        
        # Update message counts if mavlink service available
        if self.mavlink_service is not None:
            stats = self.mavlink_service.get_connection_statistics()
            self.messages_sent_label.setText(str(stats['total_sent']))
            self.messages_received_label.setText(str(stats['total_received']))
    
    def set_mavlink_service(self, mavlink_service):
        """Set or update the mavlink service reference.
        
        Args:
            mavlink_service: MAVLink service instance
        """
        self.mavlink_service = mavlink_service
        
        if mavlink_service is not None:
            mavlink_service.telemetry_updated.connect(self.on_telemetry_updated)
            mavlink_service.connection_changed.connect(self.on_connection_changed)
            mavlink_service.health_updated.connect(self.on_health_updated)
            
            # Refresh the connections list
            self._refresh_connections_list()
    
    def set_object_service(self, object_service):
        """Set the object service reference for object linking.
        
        Args:
            object_service: Object service instance
        """
        self.object_service = object_service
