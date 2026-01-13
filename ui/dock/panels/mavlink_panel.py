"""
MAVLink Panel for displaying telemetry data and connection status.

This panel provides:
- Connection management UI
- Real-time telemetry display
- Basic visualization of drone status
"""
from PyQt5.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QGroupBox, 
    QFormLayout, QPushButton, QLineEdit, QScrollArea, QFrame,
    QSpinBox, QTabWidget, QGridLayout
)
from PyQt5.QtCore import Qt, pyqtSlot
from PyQt5.QtGui import QFont

from models.structs import MavlinkConnectionConfig, MavlinkTelemetryData
import math


class MavlinkPanel(QWidget):
    """Panel for MAVLink connection management and telemetry display.
    
    Provides UI for:
    - Adding/removing drone connections
    - Viewing real-time telemetry data
    - Monitoring connection health
    """
    NavTag = "mavlink"
    
    def __init__(self, parent=None, mavlink_service=None):
        """Initialize the MAVLink panel.
        
        Args:
            parent: Parent widget
            mavlink_service: MAVLink service instance
        """
        super().__init__(parent)
        self.mavlink_service = mavlink_service
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
        """Create the connection management tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Connection form group
        form_group = QGroupBox("Add Connection")
        form_layout = QFormLayout()
        
        # Connection string input
        self.connection_input = QLineEdit()
        self.connection_input.setPlaceholderText("udp:127.0.0.1:14550")
        self.connection_input.setText("udp:127.0.0.1:14550")
        form_layout.addRow("Connection:", self.connection_input)
        
        # System ID input
        self.system_id_input = QSpinBox()
        self.system_id_input.setRange(1, 255)
        self.system_id_input.setValue(1)
        form_layout.addRow("System ID:", self.system_id_input)
        
        # Connect button
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.on_connect_clicked)
        form_layout.addRow("", self.connect_btn)
        
        form_group.setLayout(form_layout)
        layout.addWidget(form_group)
        
        # Active connections group
        connections_group = QGroupBox("Active Connections")
        self.connections_layout = QVBoxLayout()
        
        self.no_connections_label = QLabel("No active connections")
        self.no_connections_label.setStyleSheet("color: #666; font-style: italic;")
        self.connections_layout.addWidget(self.no_connections_label)
        
        connections_group.setLayout(self.connections_layout)
        layout.addWidget(connections_group)
        
        layout.addStretch()
        return widget
    
    def _create_telemetry_tab(self) -> QWidget:
        """Create the telemetry display tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Scroll area for telemetry data
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        
        content = QWidget()
        self.telemetry_layout = QVBoxLayout(content)
        
        # Placeholder for telemetry display
        self.telemetry_placeholder = QLabel("Connect to a drone to view telemetry")
        self.telemetry_placeholder.setStyleSheet("color: #666; font-style: italic;")
        self.telemetry_placeholder.setAlignment(Qt.AlignCenter)
        self.telemetry_layout.addWidget(self.telemetry_placeholder)
        
        scroll.setWidget(content)
        layout.addWidget(scroll)
        
        # Refresh button
        refresh_btn = QPushButton("Refresh Display")
        refresh_btn.clicked.connect(self.refresh_telemetry_display)
        layout.addWidget(refresh_btn)
        
        return widget
    
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
        • Telemetry: 20 Hz""")
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
        
        if not connection_string:
            return
        
        config = MavlinkConnectionConfig(
            connection_string=connection_string,
            system_id=system_id
        )
        
        # Try to connect
        self.connect_btn.setEnabled(False)
        self.connect_btn.setText("Connecting...")
        
        success = self.mavlink_service.add_connection(config)
        
        self.connect_btn.setEnabled(True)
        self.connect_btn.setText("Connect")
        
        if success:
            self._add_connection_widget(system_id, connection_string)
    
    def _add_connection_widget(self, system_id: int, connection_string: str):
        """Add a widget representing an active connection."""
        # Hide placeholder
        self.no_connections_label.hide()
        
        # Create connection frame
        frame = QFrame()
        frame.setObjectName(f"conn_{system_id}")
        frame.setStyleSheet("""
            QFrame {
                background-color: #f0f0f0;
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 8px;
                margin: 4px 0;
            }
        """)
        
        layout = QHBoxLayout(frame)
        
        # Connection info
        info_label = QLabel(f"<b>ID {system_id}</b>: {connection_string}")
        layout.addWidget(info_label)
        
        layout.addStretch()
        
        # Disconnect button
        disconnect_btn = QPushButton("Disconnect")
        disconnect_btn.clicked.connect(lambda: self._disconnect(system_id, frame))
        layout.addWidget(disconnect_btn)
        
        self.connections_layout.addWidget(frame)
    
    def _disconnect(self, system_id: int, frame: QFrame):
        """Disconnect and remove a connection."""
        if self.mavlink_service is not None:
            self.mavlink_service.remove_connection(system_id)
        
        # Remove widget
        frame.deleteLater()
        
        # Remove telemetry display if exists
        if system_id in self._telemetry_labels:
            widget = self._telemetry_labels[system_id].get('widget')
            if widget:
                widget.deleteLater()
            del self._telemetry_labels[system_id]
        
        # Show placeholder if no connections
        if self.mavlink_service is None or self.mavlink_service.get_connection_count() == 0:
            self.no_connections_label.show()
            self.telemetry_placeholder.show()
    
    def refresh_telemetry_display(self):
        """Refresh the telemetry display with current data."""
        if self.mavlink_service is None:
            return
        
        for system_id, telemetry in self.mavlink_service.get_all_telemetry().items():
            self._update_telemetry_display(system_id, telemetry)
    
    def _create_telemetry_widget(self, system_id: int) -> QGroupBox:
        """Create a telemetry display widget for a drone."""
        group = QGroupBox(f"Drone {system_id}")
        layout = QGridLayout()
        
        labels = {}
        
        # Attitude row
        layout.addWidget(QLabel("Roll:"), 0, 0)
        labels['roll'] = QLabel("0.0°")
        layout.addWidget(labels['roll'], 0, 1)
        
        layout.addWidget(QLabel("Pitch:"), 0, 2)
        labels['pitch'] = QLabel("0.0°")
        layout.addWidget(labels['pitch'], 0, 3)
        
        layout.addWidget(QLabel("Yaw:"), 0, 4)
        labels['yaw'] = QLabel("0.0°")
        layout.addWidget(labels['yaw'], 0, 5)
        
        # Position row
        layout.addWidget(QLabel("X:"), 1, 0)
        labels['x'] = QLabel("0.0 m")
        layout.addWidget(labels['x'], 1, 1)
        
        layout.addWidget(QLabel("Y:"), 1, 2)
        labels['y'] = QLabel("0.0 m")
        layout.addWidget(labels['y'], 1, 3)
        
        layout.addWidget(QLabel("Z:"), 1, 4)
        labels['z'] = QLabel("0.0 m")
        layout.addWidget(labels['z'], 1, 5)
        
        # Status row
        layout.addWidget(QLabel("Armed:"), 2, 0)
        labels['armed'] = QLabel("No")
        layout.addWidget(labels['armed'], 2, 1)
        
        layout.addWidget(QLabel("Battery:"), 2, 2)
        labels['battery'] = QLabel("0.0V")
        layout.addWidget(labels['battery'], 2, 3)
        
        layout.addWidget(QLabel("GPS:"), 2, 4)
        labels['gps'] = QLabel("No Fix")
        layout.addWidget(labels['gps'], 2, 5)
        
        group.setLayout(layout)
        
        # Store labels for updates
        labels['widget'] = group
        self._telemetry_labels[system_id] = labels
        
        return group
    
    def _update_telemetry_display(self, system_id: int, telemetry: MavlinkTelemetryData):
        """Update the telemetry display for a specific drone."""
        if system_id not in self._telemetry_labels:
            # Create new widget
            widget = self._create_telemetry_widget(system_id)
            self.telemetry_layout.insertWidget(0, widget)
            self.telemetry_placeholder.hide()
        
        labels = self._telemetry_labels[system_id]
        
        # Update attitude (convert radians to degrees)
        labels['roll'].setText(f"{math.degrees(telemetry.roll):.1f}°")
        labels['pitch'].setText(f"{math.degrees(telemetry.pitch):.1f}°")
        labels['yaw'].setText(f"{math.degrees(telemetry.yaw):.1f}°")
        
        # Update position
        labels['x'].setText(f"{telemetry.x:.2f} m")
        labels['y'].setText(f"{telemetry.y:.2f} m")
        labels['z'].setText(f"{telemetry.z:.2f} m")
        
        # Update status
        labels['armed'].setText("Yes" if telemetry.armed else "No")
        labels['armed'].setStyleSheet("color: red;" if telemetry.armed else "color: green;")
        
        labels['battery'].setText(f"{telemetry.battery_voltage:.1f}V ({telemetry.battery_remaining}%)")
        
        gps_text = {0: "No GPS", 1: "No Fix", 2: "2D Fix", 3: "3D Fix"}.get(
            telemetry.gps_fix_type, "Unknown"
        )
        labels['gps'].setText(f"{gps_text} ({telemetry.satellites_visible} sats)")
    
    @pyqtSlot(int, object)
    def on_telemetry_updated(self, system_id: int, telemetry: MavlinkTelemetryData):
        """Handle telemetry update from mavlink service."""
        self._update_telemetry_display(system_id, telemetry)
    
    @pyqtSlot(int, bool)
    def on_connection_changed(self, system_id: int, connected: bool):
        """Handle connection state change."""
        if not connected:
            # Update connection widget to show disconnected state
            pass
    
    @pyqtSlot(float, int)
    def on_health_updated(self, rate_hz: float, active_connections: int):
        """Handle health metrics update."""
        self.rate_label.setText(f"{rate_hz:.0f} Hz")
        self.connections_count_label.setText(str(active_connections))
        
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
