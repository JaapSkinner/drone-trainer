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
    QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSlot, pyqtSignal, QTimer, QThread
import dataclasses
import math

from models.structs import MavlinkConnectionConfig, MavlinkTelemetryData
from models.mavlink_links import parse_link
from ui import theme
from ui.dialogs.shell import DialogShell
from ui.widgets.link_editor import LinkEditor
from ui.widgets.empty_state import EmptyState


class DiscoveryWorker(QThread):
    """Worker thread to perform MAVLink device discovery off the UI thread."""

    devices_discovered = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, mavlink_service, timeout_secs: float = 2.0, parent=None):
        super().__init__(parent)
        self._mavlink_service = mavlink_service
        self._timeout_secs = timeout_secs

    def run(self):
        if self._mavlink_service is None:
            self.error.emit("MAVLink service not available")
            return

        try:
            devices = self._mavlink_service.discover_devices(timeout_secs=self._timeout_secs)
            self.devices_discovered.emit(devices)
        except Exception as e:
            self.error.emit(str(e))


class ConnectionCard(QFrame):
    """Widget representing a single MAVLink connection.
    
    The card stores a `connection_name` attribute that is the resolved name
    used as the key in the connections list. All signals emit this name
    to ensure consistency with the service's connection lookup.
    """
    
    # Signals for connection actions
    action_clicked = pyqtSignal(str)  # connection_name - for connect/disconnect
    link_object_clicked = pyqtSignal(str)  # connection_name
    test_clicked = pyqtSignal(str)  # connection_name
    edit_clicked = pyqtSignal(str)  # connection_name

    def __init__(self, config: MavlinkConnectionConfig, connection_name: str, is_active: bool = True,
                 parent=None, connecting: bool = False, connection=None):
        """Initialize a connection card.
        
        Args:
            config: Connection configuration
            connection_name: The resolved connection name used as dict key
            is_active: Whether the connection is currently active
            parent: Parent widget
        """
        super().__init__(parent)
        self.config = config
        # Store the resolved connection name for consistent signal emission
        self.connection_name = connection_name
        self.is_active = is_active
        self.connecting = connecting
        self.connection = connection   # the live MavlinkConnection, if connected
        self._init_ui()
    
    def _init_ui(self):
        """Initialize the connection card UI."""
        self.setProperty("role", "card")

        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(14, 12, 14, 12)

        # Header row with name and status
        header = QHBoxLayout()
        header.setSpacing(8)
        icon = QLabel()
        icon.setPixmap(theme.icon("radio-tower", "accent" if self.is_active else "muted", 18).pixmap(18, 18))
        header.addWidget(icon)

        # Connection name - use the resolved name for display
        self.name_label = theme.label(self.connection_name, "option-title")
        header.addWidget(self.name_label)
        header.addStretch()

        # Status pill
        if self.is_active:
            status_text, tone = "Connected", "success"
        elif getattr(self, "connecting", False):
            status_text, tone = "Connecting…", "warning"
        elif getattr(self.config, "auto_connect", False):
            status_text, tone = "Waiting for vehicle", "muted"
        else:
            status_text, tone = "Disconnected", "muted"
        self.status_label = theme.label(status_text, "pill", tone)
        header.addWidget(self.status_label)
        layout.addLayout(header)

        # Connection details
        id_text = f"system ID {self.config.system_id}" if self.is_active else "system ID detected on connect"
        link = parse_link(self.config.connection_string)
        details = theme.label(f"{link.describe().capitalize()} · {id_text}", "hint", wrap=True)
        details.setToolTip(self.config.connection_string)
        layout.addWidget(details)

        # Shared with another ground station (QGroundControl)?
        connection = self.connection
        forward = getattr(self.config, "forward_to", "")
        if forward:
            relayed = ""
            if connection is not None and connection.forwarding:
                relayed = f" · {connection.forwarded_out} out / {connection.forwarded_in} in"
            layout.addWidget(theme.label(f"Shared with QGroundControl at {forward}{relayed}", "hint", "accent",
                                         wrap=True))
        others = sorted(connection.other_systems()) if connection is not None else []
        if others:
            names = ", ".join(str(s) for s in others)
            layout.addWidget(theme.label(f"Also hearing vehicle {names} on this link — ignored. Give each "
                                         "vehicle its own link (port or radio) and a unique MAV_SYS_ID.",
                                         "banner", "warning", wrap=True))

        # Linked object
        linked = self.config.linked_object_name
        self.linked_label = theme.label(f"Linked to <b>{linked}</b>" if linked else "Not linked to an object", "hint",
                                        wrap=True)
        layout.addWidget(self.linked_label)

        # Button row
        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        buttons.setContentsMargins(0, 4, 0, 0)

        # Link/Unlink object button - emit resolved connection_name
        link_text = "Change Object" if linked else "Link Object"
        self.link_btn = theme.button(link_text, None, "link", "sm",
                                     tooltip="Choose the object this vehicle is (its motion capture is sent here)")
        self.link_btn.clicked.connect(lambda: self.link_object_clicked.emit(self.connection_name))
        buttons.addWidget(self.link_btn)

        if self.is_active:
            # Test button - emit resolved connection_name
            test_btn = theme.tool_button("activity", "Test this link's rate and latency")
            test_btn.setProperty("variant", "square")
            test_btn.setFixedSize(28, 28)
            test_btn.clicked.connect(lambda: self.test_clicked.emit(self.connection_name))
            buttons.addWidget(test_btn)
            buttons.addStretch()

            # Disconnect button - emit resolved connection_name
            disconnect_btn = theme.button("Disconnect", "ghost", "unplug", "sm",
                                          tooltip="Stays disconnected until you connect again")
            disconnect_btn.clicked.connect(lambda: self.action_clicked.emit(self.connection_name))
            buttons.addWidget(disconnect_btn)
        else:
            # Edit button for inactive connections only - emit resolved connection_name
            edit_btn = theme.tool_button("sliders-horizontal", "Edit this connection")
            edit_btn.setProperty("variant", "square")
            edit_btn.setFixedSize(28, 28)
            edit_btn.clicked.connect(lambda: self.edit_clicked.emit(self.connection_name))
            buttons.addWidget(edit_btn)
            buttons.addStretch()

            # Connect button for inactive connections - emit resolved connection_name
            connecting = getattr(self, "connecting", False)
            connect_btn = theme.button("Connecting…" if connecting else "Connect", "subtle", "plug", "sm")
            connect_btn.setEnabled(not connecting)
            connect_btn.clicked.connect(lambda: self.action_clicked.emit(self.connection_name))
            buttons.addWidget(connect_btn)

        layout.addLayout(buttons)

    def update_linked_object(self, object_name: str):
        """Update the linked object display."""
        self.config.linked_object_name = object_name
        if object_name:
            self.linked_label.setText(f"Linked to <b>{object_name}</b>")
            self.link_btn.setText("Change Object")
        else:
            self.linked_label.setText("Not linked to an object")
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
        self._telemetry_labels: dict = {}
        self._storage_service = None  # Set via set_storage_service()
        self._user_attempts = {}  # connection name → "new" | "saved" (attempts the user started)
        
        self.init_ui()
        
        # Connect to mavlink service signals if available
        if self.mavlink_service is not None:
            self.mavlink_service.telemetry_updated.connect(self.on_telemetry_updated)
            self.mavlink_service.connection_changed.connect(self.on_connection_changed)
            self.mavlink_service.health_updated.connect(self.on_health_updated)
            self.mavlink_service.console_output.connect(self._on_console_output)
            self.mavlink_service.connection_test_complete.connect(self._on_connection_test_complete)
        
        # Track pending single-connection test
        self._pending_test_connection_name = None

    def init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(theme.page_header("MAVLink", "Connections to flight controllers, live telemetry and "
                                                      "link health."))

        # Tab widget — fills all remaining space
        self._tabs = QTabWidget()
        self._tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._tabs.addTab(self._create_connection_tab(), "Connections")
        self._tabs.addTab(self._create_telemetry_tab(),  "Telemetry")
        self._tabs.addTab(self._create_status_tab(),     "Status")
        self._tabs.addTab(self._create_console_tab(),    "Console")

        layout.addWidget(self._tabs, stretch=1)

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
        
        # How to reach the vehicle: network (UDP/TCP) or USB/serial, and sharing with QGC.
        self.connection_input = LinkEditor()      # text()/setText(): the connection string
        self.connection_input.setText("udpin:0.0.0.0:14550")
        self.connection_input.changed.connect(self._on_link_edited)
        form_layout.addRow(self.connection_input)
        
        # System ID input
        # No System ID field: it is read from the vehicle's heartbeat when it connects.
        
        # Button row
        btn_row = QHBoxLayout()
        
        # Discover devices button
        self.discover_btn = theme.button("Discover", None, "search",
                                         tooltip="Listen for MAVLink heartbeats on the network")
        self.discover_btn.clicked.connect(self.on_discover_clicked)
        btn_row.addWidget(self.discover_btn)
        
        # Connect button
        self.connect_btn = theme.button("Connect", "primary", "plug")
        self.connect_btn.clicked.connect(self.on_connect_clicked)
        btn_row.addWidget(self.connect_btn)
        
        form_layout.addRow("", btn_row)
        
        form_group.setLayout(form_layout)
        layout.addWidget(form_group)
        
        # === Discovered Devices Section (initially hidden) ===
        self.discovered_group = QGroupBox("Discovered Devices")
        self.discovered_layout = QVBoxLayout()
        self.discovered_label = QLabel("Click 'Discover' to scan the network")
        self.discovered_label.setProperty("role", "hint")
        self.discovered_layout.addWidget(self.discovered_label)
        self.discovered_group.setLayout(self.discovered_layout)
        self.discovered_group.setVisible(False)  # Hidden until discovery is run
        layout.addWidget(self.discovered_group)
        
        # === Connections List Section ===
        connections_group = QGroupBox("Connections")
        connections_scroll = QScrollArea()
        connections_scroll.setWidgetResizable(True)
        connections_scroll.setFrameShape(QFrame.NoFrame)
        connections_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        connections_scroll.setMaximumHeight(250)
        
        self.connections_container = QWidget()
        self.connections_layout = QVBoxLayout(self.connections_container)
        self.connections_layout.setSpacing(6)
        self.connections_layout.setContentsMargins(0, 0, 0, 0)
        
        self.no_connections_label = self._no_connections_state()
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
        self.test_connection_btn = theme.button("Test All Connections", None, "activity")
        self.test_connection_btn.clicked.connect(self.on_test_connection_clicked)
        self.test_connection_btn.setEnabled(False)
        test_btn_row.addWidget(self.test_connection_btn)
        test_layout.addLayout(test_btn_row)
        
        self.test_results_label = QLabel("")
        self.test_results_label.setWordWrap(True)
        self.test_results_label.setProperty("role", "hint")
        test_layout.addWidget(self.test_results_label)
        
        test_group.setLayout(test_layout)
        layout.addWidget(test_group)
        
        layout.addStretch()
        return widget
    
    def on_discover_clicked(self):
        """Handle discover devices button click."""
        self.discovered_group.setVisible(True)
        self.discover_btn.setEnabled(False)
        self.discover_btn.setText("Discovering…")
        
        # Clear previous results
        while self.discovered_layout.count() > 0:
            child = self.discovered_layout.takeAt(0)
            if child.widget():
                child.widget().hide()
                child.widget().deleteLater()
        
        progress = QLabel("Scanning network for MAVLink devices...")
        progress.setProperty("role", "hint")
        self.discovered_layout.addWidget(progress)
        
        # Run discovery in a worker thread to avoid blocking the UI thread
        self._discovery_worker = DiscoveryWorker(
            self.mavlink_service,
            timeout_secs=5.0,
            parent=self,
        )
        self._discovery_worker.devices_discovered.connect(self._run_discovery)
        self._discovery_worker.error.connect(self._show_discovery_error)
        self._discovery_worker.finished.connect(self._on_discovery_finished)
        self._discovery_worker.start()
    
    def _run_discovery(self, devices):
        """Update UI with discovery results (called when worker completes)."""
        # Clear layout
        while self.discovered_layout.count() > 0:
            child = self.discovered_layout.takeAt(0)
            if child.widget():
                child.widget().hide()
                child.widget().deleteLater()

        if not devices:
            no_devices = QLabel("No devices found. Make sure drones are powered on.")
            no_devices.setProperty("role", "hint")
            self.discovered_layout.addWidget(no_devices)
        else:
            for device in devices:
                card = QFrame()
                card.setProperty("role", "card-alt")
                card_layout = QHBoxLayout(card)
                card_layout.setSpacing(10)
                card_layout.setContentsMargins(12, 10, 12, 10)

                # --- Left: identification text block ---
                text_block = QVBoxLayout()
                text_block.setSpacing(2)

                # Row 1: Firmware · Vehicle type  (most important identity info)
                firmware = device.autopilot_name if device.autopilot >= 0 else "Unknown firmware"
                vtype    = device.vehicle_type_name if device.vehicle_type >= 0 else "Unknown type"
                title_row = QHBoxLayout()
                title_row.setSpacing(6)
                title_row.addWidget(theme.label(f"{firmware} · {vtype}", "option-title"))
                if device.armed:
                    title_row.addWidget(theme.label("Armed", "pill", "danger"))
                title_row.addStretch()
                text_block.addLayout(title_row)

                # Row 2: SysID · IP:port
                sys_str  = f"SysID {device.system_id}" if device.system_id > 0 else "SysID ?"
                addr_str = f"{device.address}:{device.port}"
                subtitle = QLabel(f"{sys_str}  ·  {addr_str}")
                subtitle.setProperty("role", "hint")
                text_block.addWidget(subtitle)

                # Row 3: MAVLink version (minor detail)
                if device.mavlink_version:
                    mv_label = theme.label(f"MAVLink v{device.mavlink_version}", "hint")
                    text_block.addWidget(mv_label)

                card_layout.addLayout(text_block, stretch=1)

                # --- Right: Use button ---
                use_btn = theme.button("Use", "subtle", None, "sm")
                use_btn.clicked.connect(
                    lambda checked, d=device: self._use_discovered_device(d)
                )
                card_layout.addWidget(use_btn, alignment=Qt.AlignVCenter)

                self.discovered_layout.addWidget(card)

    def _on_discovery_finished(self):
        """Re-enable discovery UI after the worker thread has finished."""
        self.discover_btn.setEnabled(True)
        self.discover_btn.setText("Discover")
        # Drop the reference to allow the worker to be garbage collected
        self._discovery_worker = None
    
    def _show_discovery_error(self, message: str):
        """Show discovery error message."""
        while self.discovered_layout.count() > 0:
            child = self.discovered_layout.takeAt(0)
            if child.widget():
                child.widget().hide()
                child.widget().deleteLater()
        
        error = QLabel(f"Discovery failed: {message}")
        error.setProperty("tone", "danger")
        self.discovered_layout.addWidget(error)
        
        self.discover_btn.setEnabled(True)
        self.discover_btn.setText("Discover")
    
    def _use_discovered_device(self, device):
        """Use a discovered device's connection string."""
        self.connection_input.setText(device.connection_string)
    
    def on_test_connection_clicked(self):
        """Run a connection quality test (non-blocking).
        
        Tests packet rate by sending a burst of messages and measuring response times.
        Results are received via the _on_connection_test_complete callback.
        """
        if self.mavlink_service is None:
            return
        
        active_conns = self.mavlink_service.get_connection_count()
        if active_conns == 0:
            self.test_results_label.setText(f"<span style='color: {theme.colour('danger')};'>No active connections to test</span>")
            return
        
        self.test_results_label.setText(f"<span style='color: {theme.colour('warning')};'>Testing connection quality…</span>")
        self.test_connection_btn.setEnabled(False)
        
        # Clear pending single-connection test marker (this is test all)
        self._pending_test_connection_name = None
        
        # Start non-blocking test - results delivered via signal
        self.mavlink_service.run_connection_test()
    
    def _on_connection_test_complete(self, test_results: dict):
        """Handle connection test results from the service (non-blocking callback).
        
        Args:
            test_results: Dictionary mapping system_id to test result metrics
        """
        # Check if this was a single-connection test
        if self._pending_test_connection_name is not None:
            self._show_single_connection_test_result(test_results)
            self._pending_test_connection_name = None
            return
        
        # Multi-connection test result display
        result_text = "<b>Test Results:</b><br>"
        for sys_id, result in test_results.items():
            rate_hz = result.get('rate_hz', 0)
            latency_ms = result.get('latency_ms', 0)
            lost_packets = result.get('lost_packets', 0)
            messages_sent = result.get('messages_sent', 0)
            messages_received = result.get('messages_received', 0)

            # Color code based on quality thresholds
            if rate_hz >= self.GOOD_RATE_HZ and latency_ms < self.GOOD_LATENCY_MS and lost_packets == 0:
                color = theme.colour('success')
                status = '✓ Good'
            elif rate_hz >= self.FAIR_RATE_HZ and latency_ms < self.FAIR_LATENCY_MS:
                color = theme.colour('warning')
                status = '◐ Fair'
            else:
                color = theme.colour('danger')
                status = '✗ Poor'
            
            result_text += f"<span style='color: {color};'><b>ID {sys_id}:</b> {status}</span><br>"
            result_text += f"  • Rate: {rate_hz:.0f} Hz (messages/second)<br>"
            result_text += f"  • Sent: {messages_sent:,} | Received: {messages_received:,}<br>"

            # Always show latency
            result_text += f"  • Latency: {latency_ms:.1f} ms (round-trip time)<br>"

            # Show dropped packets as ratio of total
            total_expected = messages_received + lost_packets
            result_text += f"  • Dropped: {lost_packets} out of {total_expected:,} packet(s)<br>"

            result_text += "<br>"

        self.test_results_label.setText(result_text)
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
        self.telemetry_placeholder = EmptyState("activity", "No telemetry yet",
                                                "Connect to a drone to see its attitude, position and battery.")
        self.telemetry_layout.addWidget(self.telemetry_placeholder)
        
        self.telemetry_layout.addStretch()
        
        scroll.setWidget(content)
        layout.addWidget(scroll)
        
        return widget
    
    # (key, caption, initial text) for the telemetry tiles, three per row
    _TELEMETRY_TILES = (
        ("roll", "Roll", "0°"), ("pitch", "Pitch", "0°"), ("yaw", "Yaw", "0°"),
        ("x", "X", "0.0 m"), ("y", "Y", "0.0 m"), ("z", "Z", "0.0 m"),
        ("vx", "VX", "0.0 m/s"), ("vy", "VY", "0.0 m/s"), ("vz", "VZ", "0.0 m/s"),
        ("rollspeed", "Roll rate", "0°/s"), ("pitchspeed", "Pitch rate", "0°/s"), ("yawspeed", "Yaw rate", "0°/s"),
    )

    def _create_telemetry_widget(self, system_id: int) -> QGroupBox:
        """Create a compact telemetry display widget for a drone."""
        group = QGroupBox(f"Drone {system_id}")
        main_layout = QVBoxLayout()
        main_layout.setSpacing(10)

        labels = {}

        # Status pills: armed, mode / battery, GPS (two rows so the panel stays narrow)
        status_layout = QGridLayout()
        status_layout.setHorizontalSpacing(6)
        status_layout.setVerticalSpacing(6)
        labels['armed'] = theme.label("Disarmed", "pill", "muted")
        labels['mode'] = theme.label("Mode —", "pill")
        labels['battery'] = theme.label("Battery —", "pill", "muted")
        labels['gps'] = theme.label("GPS —", "pill", "muted")
        for index, key in enumerate(('armed', 'mode', 'battery', 'gps')):
            status_layout.addWidget(labels[key], index // 2, index % 2, Qt.AlignLeft)
        status_layout.setColumnStretch(2, 1)
        main_layout.addLayout(status_layout)

        # Attitude, position, velocity and rates as small tiles
        grid = QGridLayout()
        grid.setSpacing(6)
        for index, (key, caption, initial) in enumerate(self._TELEMETRY_TILES):
            tile = QFrame()
            tile.setProperty("role", "card-alt")
            tile_layout = QVBoxLayout(tile)
            tile_layout.setContentsMargins(10, 6, 10, 6)
            tile_layout.setSpacing(0)
            tile_layout.addWidget(theme.label(caption, "hint"))
            labels[key] = theme.label(initial, "value")
            tile_layout.addWidget(labels[key])
            grid.addWidget(tile, index // 3, index % 3)
        main_layout.addLayout(grid)

        group.setLayout(main_layout)

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

        # Convert radians to degrees for display
        roll_deg = math.degrees(telemetry.roll)
        pitch_deg = math.degrees(telemetry.pitch)
        yaw_deg = math.degrees(telemetry.yaw)
        
        # Update attitude
        labels['roll'].setText(f"{roll_deg:.1f}°")
        labels['pitch'].setText(f"{pitch_deg:.1f}°")
        labels['yaw'].setText(f"{yaw_deg:.1f}°")
        
        # Update position
        labels['x'].setText(f"{telemetry.x:.1f} m")
        labels['y'].setText(f"{telemetry.y:.1f} m")
        labels['z'].setText(f"{telemetry.z:.1f} m")
        
        # Update velocity
        labels['vx'].setText(f"{telemetry.vx:.1f} m/s")
        labels['vy'].setText(f"{telemetry.vy:.1f} m/s")
        labels['vz'].setText(f"{telemetry.vz:.1f} m/s")

        # Update angular rates
        labels['rollspeed'].setText(f"{math.degrees(telemetry.rollspeed):.1f}°/s")
        labels['pitchspeed'].setText(f"{math.degrees(telemetry.pitchspeed):.1f}°/s")
        labels['yawspeed'].setText(f"{math.degrees(telemetry.yawspeed):.1f}°/s")

        # Update status
        labels['armed'].setText("Armed" if telemetry.armed else "Disarmed")
        theme.set_tone(labels['armed'], "danger" if telemetry.armed else "muted")

        # Battery with color coding (no voltage reported = no battery data, e.g. SITL)
        bat_pct = telemetry.battery_remaining
        if telemetry.battery_voltage <= 0:
            labels['battery'].setText("Battery —")
            theme.set_tone(labels['battery'], "muted")
        else:
            labels['battery'].setText(f"Battery {telemetry.battery_voltage:.1f} V · {bat_pct}%")
            theme.set_tone(labels['battery'], "success" if bat_pct > 50 else "warning" if bat_pct > 20 else "danger")

        # GPS fix type (indoors under motion capture there usually is none)
        gps_text = {0: "No GPS", 1: "No Fix", 2: "2D", 3: "3D"}.get(
            telemetry.gps_fix_type, "?"
        )
        labels['gps'].setText(f"GPS {gps_text}" + (f" · {telemetry.satellites_visible} sats"
                                                    if telemetry.gps_fix_type >= 2 else ""))
        theme.set_tone(labels['gps'], "success" if telemetry.gps_fix_type >= 3 else "muted")

        # Mode
        labels['mode'].setText(f"Mode {telemetry.mode}")

    def _create_status_tab(self) -> QWidget:
        """Create the status monitoring tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Health metrics group
        health_group = QGroupBox("Service Health")
        health_layout = QFormLayout()
        
        self.rate_label = QLabel("0 Hz")
        self.rate_label.setProperty("role", "metric")
        self.rate_label.setToolTip("Messages per second (Hz = Hertz)\nHigher is better. Good: >50 Hz, Fair: >20 Hz")
        health_layout.addRow("Message Rate:", self.rate_label)
        
        self.connections_count_label = QLabel("0")
        self.connections_count_label.setProperty("role", "metric")
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
            self.dialect_label.setProperty("tone", "success")
        else:
            self.dialect_label.setProperty("tone", "warning")
        dialect_layout.addRow("Active Dialect:", self.dialect_label)
        
        self.dtrg_status_label = QLabel("Available" if dialect_info['dtrg_available'] else "Not Found")
        if dialect_info['dtrg_available']:
            self.dtrg_status_label.setProperty("tone", "success")
        else:
            self.dtrg_status_label.setProperty("tone", "danger")
        dialect_layout.addRow("DTRG Submodule:", self.dtrg_status_label)
        
        # Show if dialect is built
        dtrg_built = dialect_info.get('dtrg_built', False)
        self.dtrg_built_label = QLabel("Built" if dtrg_built else "Not Built")
        if dtrg_built:
            self.dtrg_built_label.setProperty("tone", "success")
        else:
            self.dtrg_built_label.setProperty("tone", "warning")
        dialect_layout.addRow("DTRG Dialect:", self.dtrg_built_label)
        
        dialect_group.setLayout(dialect_layout)
        layout.addWidget(dialect_group)
        
        # Info group
        info_group = QGroupBox("MAVLink Info")
        info_layout = QVBoxLayout()
        
        info_text = QLabel("""<b>Message Priorities:</b><br>
        • <span style='color: {danger};'>Critical</span>: Motion capture data<br>
        • <span style='color: {warning};'>High</span>: Setpoint commands<br>
        • <span style='color: {success};'>Normal</span>: Telemetry data<br>
        <br>
        <b>Rate Limits:</b><br>
        • Motion capture: 100 Hz<br>
        • Setpoints: 50 Hz<br>
        • Telemetry: 20 Hz<br>
        <br>
        <b>Build DTRG Dialect:</b><br>
        <code>python scripts/build_mavlink.py --dialect dtrg</code>""".format(
            danger=theme.colour("danger"), warning=theme.colour("warning"), success=theme.colour("success")))
        info_text.setWordWrap(True)
        info_text.setProperty("role", "hint")
        info_layout.addWidget(info_text)
        
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)
        
        layout.addStretch()
        return widget
    
    def _on_link_edited(self):
        # Discover listens for UDP heartbeats: not for a serial port.
        self.discover_btn.setVisible(self.connection_input.link().kind != "serial")

    def on_connect_clicked(self):
        """Connect in the background; the result arrives in _on_attempt_finished."""
        if self.mavlink_service is None:
            return
        connection_string = self.connection_input.text().strip()
        if not connection_string:
            return
        problem = self.connection_input.problem()
        if problem:
            QMessageBox.warning(self, "Connection", problem)
            return
        config = MavlinkConnectionConfig(connection_string=connection_string,
                                         name=self.name_input.text().strip(),  # name auto-generated if empty
                                         forward_to=self.connection_input.forward_to())
        self.connect_btn.setEnabled(False)
        self.connect_btn.setText("Connecting…")
        name = self.mavlink_service.add_connection_async(config)
        self._user_attempts[name] = "new"
        self._refresh_connections_list()

    def _on_attempt_finished(self, name: str, success: bool, message: str):
        kind = self._user_attempts.pop(name, None)
        if kind == "new":
            self.connect_btn.setEnabled(True)
            self.connect_btn.setText("Connect")
            if success:
                self.name_input.clear()
        self._refresh_connections_list()
        if not success and kind is not None:
            QMessageBox.warning(self, "Connection failed", f"Couldn't connect '{name}'.\n\n{message}")

    @staticmethod
    def _no_connections_state():
        return EmptyState("radio-tower", "No connections yet",
                          "Add one above, or use “Add a drone…” to set up a drone and its connection together.")

    def _refresh_connections_list(self):
        """Refresh the connections list showing all active and inactive connections."""
        # Clear current connections
        while self.connections_layout.count() > 0:
            child = self.connections_layout.takeAt(0)
            if child.widget():
                child.widget().hide()
                child.widget().deleteLater()
        
        self._connection_cards.clear()
        
        if self.mavlink_service is None:
            self.no_connections_label = self._no_connections_state()
            self.connections_layout.addWidget(self.no_connections_label)
            return
        
        # Get all connections (active and inactive)
        all_connections = self.mavlink_service.get_all_connections()
        
        if not all_connections:
            self.no_connections_label = self._no_connections_state()
            self.connections_layout.addWidget(self.no_connections_label)
            return
        
        # Add connection cards
        for name, config in all_connections.items():
            # Check if this connection is active
            conn = self.mavlink_service.get_connection_by_name(name)
            is_active = conn is not None and conn.is_connected
            
            # Pass the resolved name to ensure consistent signal emission
            card = ConnectionCard(config, connection_name=name, is_active=is_active,
                                  connecting=self.mavlink_service.is_connecting(name), connection=conn)
            card.action_clicked.connect(self._on_connection_action)
            card.link_object_clicked.connect(self._on_link_object_clicked)
            card.test_clicked.connect(self._on_test_single_connection)
            card.edit_clicked.connect(self._on_edit_connection)

            self._connection_cards[name] = card
            self.connections_layout.addWidget(card)
        
        self.connections_layout.addStretch()
    
    def _on_connection_action(self, connection_name: str):
        """Handle connect/disconnect action for a connection."""
        if self.mavlink_service is None:
            return
        
        conn = self.mavlink_service.get_connection_by_name(connection_name)
        
        if conn is not None and conn.is_connected:
            # Disconnect, and stay disconnected (no auto-reconnect) until connected again.
            self.mavlink_service.disconnect_by_user(conn.config.system_id)
            self._refresh_connections_list()
        else:
            all_conns = self.mavlink_service.get_all_connections()
            if connection_name in all_conns:
                self._user_attempts[connection_name] = "saved"
                self.mavlink_service.add_connection_async(all_conns[connection_name])
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
        from PyQt5.QtWidgets import QDialog
        
        dialog = DialogShell("Link an object", f"The object whose motion capture is sent to "
                                               f"'{connection_name}', and which it commands.",
                             accept_text="Link", accept_icon="link", parent=self)
        dialog.resize(420, 0)
        dialog_layout = dialog.body
        
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
        
        if dialog.exec_() == QDialog.Accepted:
            selected_name = combo.currentData()
            if self.mavlink_service:
                # Link through the object so mocap actually streams to this connection.
                previous = self.object_service.get_object(current_linked) if current_linked else None
                selected = self.object_service.get_object(selected_name) if selected_name else None
                if selected is not None:
                    self.mavlink_service.link_object(selected, connection_name)
                elif previous is not None:
                    self.mavlink_service.unlink_object(previous)
                else:
                    self.mavlink_service.unlink_connection_from_object(connection_name)
                if self.object_service is not None:
                    for obj in (previous, selected):
                        if obj is not None:
                            self.object_service.notify_object_changed(obj)
                
                # Update the card
                if connection_name in self._connection_cards:
                    self._connection_cards[connection_name].update_linked_object(selected_name)
                
                # Emit signal for other panels
                self.object_link_requested.emit(connection_name, selected_name)
    
    def _on_test_single_connection(self, connection_name: str):
        """Test a single connection (non-blocking).
        
        Starts the test and stores the connection name. Results are handled
        in _on_connection_test_complete via the service signal.
        """
        if self.mavlink_service is None:
            return
        
        conn = self.mavlink_service.get_connection_by_name(connection_name)
        if conn is None:
            return
        
        # Store which connection we're testing for the callback
        self._pending_test_connection_name = connection_name
        
        # Start non-blocking test - results delivered via signal
        self.mavlink_service.run_connection_test()
    
    def _show_single_connection_test_result(self, test_results: dict):
        """Show test result dialog for a single connection.
        
        Called from _on_connection_test_complete when a single-connection test finishes.
        
        Args:
            test_results: Dictionary mapping system_id to test result metrics
        """
        connection_name = self._pending_test_connection_name
        if connection_name is None:
            return
        
        conn = self.mavlink_service.get_connection_by_name(connection_name)
        if conn is None:
            return
        
        sys_id = conn.config.system_id
        
        if sys_id in test_results:
            result = test_results[sys_id]
            quality = result.get('quality', 'unknown')
            rate = result.get('rate_hz', 0)
            latency = result.get('latency_ms', 0)
            sent = result.get('messages_sent', 0)
            received = result.get('messages_received', 0)
            dropped = result.get('lost_packets', 0)

            # Build detailed message
            msg = f"Quality: {quality.upper()}\n"
            msg += f"Rate: {rate:.1f} Hz (messages/second)\n"
            msg += f"Messages Sent: {sent:,}\n"
            msg += f"Messages Received: {received:,}\n"
            msg += f"Latency: {latency:.1f} ms (round-trip time)\n"

            total_expected = received + dropped
            msg += f"Dropped Packets: {dropped} out of {total_expected:,}\n"

            QMessageBox.information(
                self, 
                f"Connection Test - {connection_name}",
                msg
            )
    
    def _on_edit_connection(self, connection_name: str):
        """Handle edit connection button click - show edit dialog."""
        if self.mavlink_service is None:
            return

        # Try to get active connection first, then check saved connections
        conn = self.mavlink_service.get_connection_by_name(connection_name)
        config = None

        if conn is not None:
            # Active connection
            config = conn.config
        else:
            # Check saved connections
            all_connections = self.mavlink_service.get_all_connections()
            if connection_name in all_connections:
                config = all_connections[connection_name]

        if config is None:
            QMessageBox.warning(self, "Connection Not Found", f"Connection '{connection_name}' not found.")
            return

        # Create edit dialog
        from PyQt5.QtWidgets import QDialog

        dialog = DialogShell(f"Edit {connection_name}", "Where the vehicle's MAVLink arrives.", accept_text="Save",
                             accept_icon="save", parent=self)
        dialog.resize(440, 0)
        dialog_layout = dialog.body

        # Form for editing
        form_layout = QFormLayout()
        form_layout.setVerticalSpacing(10)

        # Name field
        name_edit = QLineEdit(config.name or "")
        name_edit.setPlaceholderText("Connection name")
        form_layout.addRow("Name:", name_edit)

        # How to reach the vehicle (and whether to share it with QGC)
        address_edit = LinkEditor()
        address_edit.setText(config.connection_string)
        address_edit.set_forward_to(getattr(config, "forward_to", ""))
        form_layout.addRow(address_edit)

        # System ID field (editable for saved connections, read-only for active)
        if conn is not None:
            # Active connection - system ID is read-only
            system_id_widget = QLabel(str(config.system_id))
            system_id_widget.setProperty("role", "hint")
        else:
            # Saved connection - system ID can be edited
            system_id_widget = QSpinBox()
            system_id_widget.setRange(1, 255)
            system_id_widget.setValue(config.system_id)
        form_layout.addRow("System ID:", system_id_widget)

        # Warning label
        warning = theme.label("Changing the address needs a reconnect." if conn else
                              "Changes are used the next time it connects.", "banner", "warning", wrap=True)

        dialog_layout.addLayout(form_layout)
        dialog_layout.addWidget(warning)

        if dialog.exec_() == QDialog.Accepted:
            new_name = name_edit.text().strip()
            new_address = address_edit.text().strip()
            new_system_id = system_id_widget.value() if isinstance(system_id_widget, QSpinBox) else config.system_id

            if not new_address:
                QMessageBox.warning(self, "Invalid Input", "Connection address cannot be empty.")
                return
            problem = address_edit.problem()
            if problem:
                QMessageBox.warning(self, "Invalid Input", problem)
                return
            new_forward = address_edit.forward_to()

            # Check what changed
            address_changed = new_address != config.connection_string
            name_changed = new_name != (config.name or "")
            system_id_changed = new_system_id != config.system_id

            if conn is not None:
                # Active connection - not allowed to edit, should disconnect first
                QMessageBox.warning(
                    self,
                    "Cannot Edit Active Connection",
                    "Please disconnect before editing connection properties."
                )
                return
            else:
                # Saved connection - update the saved config
                old_linked_object = config.linked_object_name

                # Updated copy: fields this dialog doesn't show (rates, intervals …) are kept.
                updated_config = dataclasses.replace(
                    config,
                    connection_string=new_address,
                    system_id=new_system_id,
                    name=new_name if new_name else connection_name,
                    linked_object_name=old_linked_object,
                    forward_to=new_forward,
                )

                # Remove old saved connection (by old name) using public API
                self.mavlink_service.remove_saved_connection(connection_name)

                # Save updated config with new name, and keep objects linked to it.
                self.mavlink_service.save_connection_config(updated_config)
                self.mavlink_service.rename_links(
                    connection_name, updated_config.name,
                    objects=self.object_service.get_objects() if self.object_service else ())

                # Persist the edit to storage
                if self._storage_service is not None:
                    from models.storage_models import ConnectionEntry
                    # Remove old entry if name changed
                    if connection_name != updated_config.name:
                        self._storage_service.delete_connection(connection_name)
                    self._storage_service.upsert_connection(ConnectionEntry.from_config(updated_config.name,
                                                                                        updated_config))

            # Refresh the connections list
            self._refresh_connections_list()

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
        self._refresh_connections_list()
        self._console_refresh_connections()

    @pyqtSlot(float, int)
    def on_health_updated(self, rate_hz: float, active_connections: int):
        """Handle health metrics update."""
        self.rate_label.setText(f"{rate_hz:.0f} Hz")
        self.connections_count_label.setText(str(active_connections))
        
        # Enable/disable test button based on connections
        self.test_connection_btn.setEnabled(active_connections > 0)
        
        # Update no connections label visibility if it exists
        if hasattr(self, 'no_connections_label') and self.no_connections_label is not None:
            try:
                self.no_connections_label.setVisible(active_connections == 0)
            except RuntimeError:
                # Widget has been deleted, ignore
                pass

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
            mavlink_service.console_output.connect(self._on_console_output)
            mavlink_service.connection_attempt_finished.connect(self._on_attempt_finished)

            # Refresh the connections list
            self._refresh_connections_list()
            self._console_refresh_connections()

    def set_object_service(self, object_service):
        """Set the object service reference for object linking.

        Args:
            object_service: Object service instance
        """
        self.object_service = object_service

    def set_storage_service(self, storage_service):
        """Set the storage service reference for persisting connection edits.

        Args:
            storage_service: StorageService instance
        """
        self._storage_service = storage_service

    # ------------------------------------------------------------------
    # Console tab
    # ------------------------------------------------------------------

    def _create_console_tab(self) -> QWidget:
        """Create the MAVLink console tab.

        Mirrors the QGC MAVLink Console — sends shell commands via
        SERIAL_CONTROL and displays stdout + STATUSTEXT in a scrolling log.
        """
        from PyQt5.QtGui import QTextCursor, QColor
        widget = QWidget()
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout(widget)
        layout.setSpacing(6)
        layout.setContentsMargins(6, 6, 6, 6)

        # --- Connection selector ---
        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Connection:"))

        self._console_conn_combo = QComboBox()
        self._console_conn_combo.setMinimumWidth(160)
        top_row.addWidget(self._console_conn_combo, stretch=1)

        clear_btn = theme.button("Clear", "ghost", None, "sm")
        clear_btn.clicked.connect(self._on_console_clear)
        top_row.addWidget(clear_btn)

        layout.addLayout(top_row)

        # --- Output area ---
        from PyQt5.QtWidgets import QPlainTextEdit
        self._console_output = QPlainTextEdit()
        self._console_output.setReadOnly(True)
        self._console_output.setLineWrapMode(QPlainTextEdit.NoWrap)
        self._console_output.setMaximumBlockCount(2000)
        self._console_output.setProperty("role", "console")
        layout.addWidget(self._console_output, stretch=1)

        # --- Input row ---
        input_row = QHBoxLayout()
        input_row.setSpacing(4)

        prompt = theme.label("$", "mono", "muted")
        input_row.addWidget(prompt)

        self._console_input = QLineEdit()
        self._console_input.setPlaceholderText("Enter shell command…")
        self._console_input.setProperty("role", "console")
        self._console_input.returnPressed.connect(self._on_console_send)
        input_row.addWidget(self._console_input, stretch=1)

        send_btn = theme.button("Send", "primary", None, "sm")
        send_btn.clicked.connect(self._on_console_send)
        input_row.addWidget(send_btn)

        layout.addLayout(input_row)

        # Command history (↑/↓ navigation like a real terminal)
        self._console_history: list = []
        self._console_history_idx: int = -1
        self._console_input.installEventFilter(self)

        # Populate dropdown with any already-connected drones
        self._console_refresh_connections()

        return widget

    def eventFilter(self, obj, event):
        """Intercept Up/Down arrow keys in the console input for history navigation."""
        from PyQt5.QtCore import QEvent
        from PyQt5.QtGui import QKeyEvent
        from PyQt5.QtCore import Qt as _Qt
        if obj is self._console_input and event.type() == QEvent.KeyPress:
            key = event.key()
            if key == _Qt.Key_Up:
                if self._console_history:
                    self._console_history_idx = max(0, self._console_history_idx - 1)
                    self._console_input.setText(self._console_history[self._console_history_idx])
                return True
            elif key == _Qt.Key_Down:
                if self._console_history:
                    self._console_history_idx = min(
                        len(self._console_history) - 1,
                        self._console_history_idx + 1
                    )
                    self._console_input.setText(self._console_history[self._console_history_idx])
                return True
        return super().eventFilter(obj, event)

    def _console_refresh_connections(self):
        """Repopulate the connection dropdown with currently active connections.
        
        Uses the public get_active_connections() API instead of accessing
        internal _connections attribute directly.
        """
        if not hasattr(self, '_console_conn_combo'):
            return

        prev = self._console_conn_combo.currentData()
        self._console_conn_combo.blockSignals(True)
        self._console_conn_combo.clear()

        if self.mavlink_service is None:
            self._console_conn_combo.addItem("No service", userData=None)
        else:
            # Use public API to get active connections
            all_connections = self.mavlink_service.get_active_connections()
            active = {
                sid: conn for sid, conn in all_connections.items()
                if conn.is_connected
            }
            if not active:
                self._console_conn_combo.addItem("No active connections", userData=None)
            else:
                for sid, conn in active.items():
                    label = conn.config.name or f"SysID {sid}"
                    self._console_conn_combo.addItem(label, userData=sid)

        # Restore previous selection if still present
        if prev is not None:
            idx = self._console_conn_combo.findData(prev)
            if idx >= 0:
                self._console_conn_combo.setCurrentIndex(idx)

        self._console_conn_combo.blockSignals(False)

    def _on_console_send(self):
        """Send the current input line to the selected drone's shell."""
        if not hasattr(self, '_console_input'):
            return

        text = self._console_input.text().strip()
        if not text:
            return

        # Echo the command to the output
        self._console_append(f"$ {text}", color="accent")

        # History bookkeeping
        if not self._console_history or self._console_history[-1] != text:
            self._console_history.append(text)
        self._console_history_idx = len(self._console_history)

        self._console_input.clear()

        # Resolve selected system_id
        sys_id = self._console_conn_combo.currentData()
        if sys_id is None or self.mavlink_service is None:
            self._console_append("[No active connection selected]", color="danger")
            return

        ok = self.mavlink_service.send_console_command(sys_id, text)
        if not ok:
            self._console_append("[Send failed — is the drone connected?]", color="danger")

    def _on_console_clear(self):
        """Clear the console output area."""
        if hasattr(self, '_console_output'):
            self._console_output.clear()

    @pyqtSlot(int, str)
    def _on_console_output(self, system_id: int, text: str):
        """Receive output from the drone and append it to the console.

        Only shown if the system_id matches the currently selected connection,
        so output from multiple drones doesn't interleave.
        """
        if not hasattr(self, '_console_conn_combo'):
            return

        selected_sid = self._console_conn_combo.currentData()
        if selected_sid is not None and selected_sid != system_id:
            return  # Output is from a different drone — ignore

        # STATUSTEXT lines get a distinct colour; raw shell output is plain text
        if text.startswith("[STATUS]"):
            self._console_append(text, color="success")
        else:
            self._console_append(text, color="text")

    def _console_append(self, text: str, color: str = "text"):
        """Append styled text to the console output, then scroll to bottom."""
        from PyQt5.QtGui import QTextCursor
        cursor = self._console_output.textCursor()
        cursor.movePosition(QTextCursor.End)

        fmt = cursor.charFormat()
        fmt.setForeground(theme.qcolour(color))   # a theme token: text | accent | success | danger
        cursor.setCharFormat(fmt)
        cursor.insertText(text if text.endswith('\n') else text + '\n')

        self._console_output.setTextCursor(cursor)
        self._console_output.ensureCursorVisible()

