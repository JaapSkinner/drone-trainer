from PyQt5.QtWidgets import (QWidget, QScrollArea, QVBoxLayout, QFormLayout,
                             QGroupBox, QLabel, QLineEdit, QComboBox, QCheckBox,
                             QSpinBox, QDoubleSpinBox, QHBoxLayout, QPushButton,
                             QDialog, QDialogButtonBox)
from PyQt5.QtCore import pyqtSignal
from models.structs import MavlinkObjectConfig

class ObjectPanel(QWidget):
    """Panel for viewing and editing scene object properties.

    Includes MAVLink configuration for each object.

    Signals:
        mavlink_config_changed: Emitted when an object's MAVLink config changes
    """
    NavTag = "live_data"

    # Signal emitted when mavlink config changes (object, config)
    mavlink_config_changed = pyqtSignal(object, object)

    def __init__(self, gl_widget, parent=None, object_service=None, mavlink_service=None):
        super().__init__(parent)
        self.gl_widget = gl_widget
        self.input_fields = []
        self.object_service = object_service
        self.mavlink_service = mavlink_service

        layout = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        content = QWidget()
        self.scroll_layout = QVBoxLayout(content)
        content.setLayout(self.scroll_layout)

        scroll.setWidget(content)
        layout.addWidget(scroll)

        self.populate()

    def populate(self):
        """Populate the panel with all objects from the object service."""
        self.input_fields.clear()
        # clear layout
        while self.scroll_layout.count():
            child = self.scroll_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        for i, obj in enumerate(self.object_service.get_objects()):

            group_box = QGroupBox(f"Object {i} - {obj.name}")
            form_layout = QFormLayout()

            x = QLineEdit(f"{obj.pose[0]:.4f}")
            y = QLineEdit(f"{obj.pose[1]:.4f}")
            z = QLineEdit(f"{obj.pose[2]:.4f}")
            xr = QLineEdit(f"{obj.pose[4]:.4f}")
            yr = QLineEdit(f"{obj.pose[5]:.4f}")
            zr = QLineEdit(f"{obj.pose[6]:.4f}")
            # color = QLineEdit(f"({obj.colour[0]:.4f}, {obj.colour[1]:.4f}, {obj.colour[2]:.4f})")
            if hasattr(obj, 'dimensions'):
                size = QLineEdit(f"{obj.dimensions[0]:.4f}")
                length = QLineEdit(f"{obj.dimensions[1]:.4f}")
            else:
                size = QLineEdit(f"-1")
                length = QLineEdit(f"-1")

            # trans = QLineEdit(f"{obj.colour[3]:.4f}")

            self._connect(x, i, 'x_pos')
            self._connect(y, i, 'y_pos')
            self._connect(z, i, 'z_pos')
            self._connect(xr, i, 'x_rot')
            self._connect(yr, i, 'y_rot')
            self._connect(zr, i, 'z_rot')
            # self._connect(color, i, 'color')
            self._connect(size, i, 'size')
            self._connect(length, i, 'length')
            # self._connect(trans, i, 'transparency')

            form_layout.addRow(QLabel("X Pos"), x)
            form_layout.addRow(QLabel("Y Pos"), y)
            form_layout.addRow(QLabel("Z Pos"), z)
            form_layout.addRow(QLabel("X Rot"), xr)
            form_layout.addRow(QLabel("Y Rot"), yr)
            form_layout.addRow(QLabel("Z Rot"), zr)
            # form_layout.addRow(QLabel("Color"), color)
            form_layout.addRow(QLabel("Size"), size)
            form_layout.addRow(QLabel("Length"), length)
            # form_layout.addRow(QLabel("Transparency"), trans)

            group_box.setLayout(form_layout)
            self.scroll_layout.addWidget(group_box)

            # Add MAVLink configuration group for controllable objects
            if getattr(obj, 'controllable', False):
                mavlink_group = self._create_mavlink_group(obj, i)
                self.scroll_layout.addWidget(mavlink_group)

            self.input_fields.append({
                'x_pos': x, 'y_pos': y, 'z_pos': z,
                'x_rot': xr, 'y_rot': yr, 'z_rot': zr,
                # 'color': color, 'size': size,
                # 'length': length, 'transparency': trans
            })

    def _create_mavlink_group(self, obj, index):
        """Create a MAVLink configuration group for an object.

        Args:
            obj: The scene object
            index: Object index in the list

        Returns:
            QGroupBox with MAVLink configuration widgets
        """
        group = QGroupBox(f"MAVLink - {obj.name}")
        layout = QFormLayout()

        config = getattr(obj, 'mavlink_config', MavlinkObjectConfig())

        # Container widget for all non-enabled options (for hiding/showing)
        options_container = QWidget()
        options_layout = QFormLayout(options_container)
        options_layout.setContentsMargins(0, 0, 0, 0)

        # Enable MAVLink checkbox
        enabled_cb = QCheckBox()
        enabled_cb.setChecked(config.enabled)
        enabled_cb.stateChanged.connect(
            lambda state, o=obj, c=options_container: self._on_mavlink_enabled_toggled(o, state == 2, c)
        )
        layout.addRow("MAVLink Enabled:", enabled_cb)

        # === Link Connection Section ===
        # Show linked connection name
        linked_name = config.linked_connection_name or "(Not linked)"
        linked_label = QLabel(linked_name)
        linked_label.setStyleSheet("color: #666;" if not config.linked_connection_name else "color: green; font-weight: bold;")

        # Store reference for updating
        if not hasattr(self, '_linked_labels'):
            self._linked_labels = {}
        self._linked_labels[obj.name] = linked_label

        # Link button
        link_btn = QPushButton("Link Connection" if not config.linked_connection_name else "Change Connection")
        link_btn.clicked.connect(lambda checked, o=obj: self._on_link_connection_clicked(o))

        link_row = QHBoxLayout()
        link_row.addWidget(linked_label)
        link_row.addWidget(link_btn)
        options_layout.addRow("Linked Connection:", link_row)

        # Use global connection checkbox
        use_global_cb = QCheckBox()
        use_global_cb.setChecked(config.use_global_connection)
        use_global_cb.stateChanged.connect(
            lambda state, o=obj: self._on_mavlink_param_changed(o, 'use_global_connection', state == 2)
        )
        options_layout.addRow("Use Global Connection:", use_global_cb)

        # Connection string (only visible if not using global)
        conn_edit = QLineEdit(config.connection_string)
        conn_edit.setEnabled(not config.use_global_connection)
        conn_edit.textChanged.connect(
            lambda text, o=obj: self._on_mavlink_param_changed(o, 'connection_string', text)
        )
        use_global_cb.stateChanged.connect(
            lambda state: conn_edit.setEnabled(state != 2)
        )
        options_layout.addRow("Connection String:", conn_edit)

        # System ID
        system_id_spin = QSpinBox()
        system_id_spin.setRange(1, 255)
        system_id_spin.setValue(config.system_id)
        system_id_spin.valueChanged.connect(
            lambda val, o=obj: self._on_mavlink_param_changed(o, 'system_id', val)
        )
        options_layout.addRow("System ID:", system_id_spin)

        # Component ID
        component_id_spin = QSpinBox()
        component_id_spin.setRange(1, 255)
        component_id_spin.setValue(config.component_id)
        component_id_spin.valueChanged.connect(
            lambda val, o=obj: self._on_mavlink_param_changed(o, 'component_id', val)
        )
        options_layout.addRow("Component ID:", component_id_spin)

        # Send Mocap checkbox
        send_mocap_cb = QCheckBox()
        send_mocap_cb.setChecked(config.send_mocap)
        send_mocap_cb.stateChanged.connect(
            lambda state, o=obj: self._on_mavlink_param_changed(o, 'send_mocap', state == 2)
        )
        options_layout.addRow("Send MoCap Data:", send_mocap_cb)

        # Receive Setpoints checkbox
        recv_sp_cb = QCheckBox()
        recv_sp_cb.setChecked(config.receive_setpoints)
        recv_sp_cb.stateChanged.connect(
            lambda state, o=obj: self._on_mavlink_param_changed(o, 'receive_setpoints', state == 2)
        )
        options_layout.addRow("Receive Setpoints:", recv_sp_cb)

        # Mocap Rate
        mocap_rate_spin = QDoubleSpinBox()
        mocap_rate_spin.setRange(0, 200)
        mocap_rate_spin.setValue(config.mocap_rate_hz)
        mocap_rate_spin.setSuffix(" Hz")
        mocap_rate_spin.setToolTip("0 = use global default rate")
        mocap_rate_spin.valueChanged.connect(
            lambda val, o=obj: self._on_mavlink_param_changed(o, 'mocap_rate_hz', val)
        )
        options_layout.addRow("MoCap Rate (0=default):", mocap_rate_spin)

        # Add options container to main layout
        layout.addRow(options_container)

        # Initially hide/show options based on enabled state
        options_container.setVisible(config.enabled)

        group.setLayout(layout)
        return group

    def _on_link_connection_clicked(self, obj):
        """Handle link connection button click for an object."""
        if self.mavlink_service is None:
            return

        # Get available connection names
        connection_names = self.mavlink_service.get_available_connection_names()

        if not connection_names:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.information(
                self,
                "No Connections",
                "No MAVLink connections available. Create a connection in the MAVLink panel first."
            )
            return

        # Create selection dialog
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Link MAVLink Connection - {obj.name}")
        dialog_layout = QVBoxLayout(dialog)

        dialog_layout.addWidget(QLabel("Select a connection to link:"))

        combo = QComboBox()
        combo.addItem("(None - Unlink)", "")
        for name in connection_names:
            combo.addItem(name, name)

        # Pre-select current linked connection
        current_linked = getattr(obj, 'mavlink_config', MavlinkObjectConfig()).linked_connection_name
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

            # Update object config
            if hasattr(obj, 'mavlink_config'):
                obj.mavlink_config.linked_connection_name = selected_name
                self.mavlink_config_changed.emit(obj, obj.mavlink_config)

            # Update linked label display
            if obj.name in self._linked_labels:
                if selected_name:
                    self._linked_labels[obj.name].setText(selected_name)
                    self._linked_labels[obj.name].setStyleSheet("color: green; font-weight: bold;")
                else:
                    self._linked_labels[obj.name].setText("(Not linked)")
                    self._linked_labels[obj.name].setStyleSheet("color: #666;")

            # Update mavlink service bidirectional link
            if self.mavlink_service:
                if selected_name:
                    self.mavlink_service.link_connection_to_object(selected_name, obj.name)
                else:
                    # Find and unlink the old connection
                    old_linked = getattr(obj, 'mavlink_config', MavlinkObjectConfig()).linked_connection_name
                    if old_linked:
                        self.mavlink_service.unlink_connection_from_object(old_linked)

    def _on_mavlink_enabled_toggled(self, obj, enabled, options_container):
        """Handle MAVLink enabled state change with UI update.

        Args:
            obj: Scene object
            enabled: New enabled state
            options_container: Widget containing options to show/hide
        """
        options_container.setVisible(enabled)
        self._on_mavlink_enabled_changed(obj, enabled)

    def _on_mavlink_enabled_changed(self, obj, enabled):
        """Handle MAVLink enabled state change for an object."""
        if hasattr(obj, 'mavlink_config'):
            obj.mavlink_config.enabled = enabled
            self.mavlink_config_changed.emit(obj, obj.mavlink_config)

    def _on_mavlink_param_changed(self, obj, param, value):
        """Handle MAVLink parameter change for an object."""
        if hasattr(obj, 'mavlink_config'):
            setattr(obj.mavlink_config, param, value)
            self.mavlink_config_changed.emit(obj, obj.mavlink_config)

    def _connect(self, line_edit, index, attr):
        line_edit.textChanged.connect(lambda text, i=index, a=attr: self._update_object(i, a, text))

    def _update_object(self, i, attr, val):
        try:
            if attr in ['x_pos', 'y_pos', 'z_pos', 'x_rot', 'y_rot', 'z_rot', 'size', 'length', 'transparency']:
                val = float(val)
            elif attr == 'color':
                val = tuple(map(float, val.strip("()").split(',')))
            setattr(self.gl_widget.objects[i], attr, val)
        except:
            pass

    def refresh(self):
        # TODO: implement this with new object service features
        return

        for i, obj in enumerate(self.object_service.get_objects()):
            fields = self.input_fields[i]
            fields['x_pos'].setText(f"{obj.pose[0]:.4f}")
            fields['y_pos'].setText(f"{obj.pose[1]:.4f}")
            fields['z_pos'].setText(f"{obj.pose[2]:.4f}")
            fields['x_rot'].setText(f"{obj.pose[3]:.4f}")
            fields['y_rot'].setText(f"{obj.pose[4]:.4f}")
            fields['z_rot'].setText(f"{obj.pose[5]:.4f}")
            # fields['color'].setText(f"({obj.color[0]:.4f}, {obj.color[1]:.4f}, {obj.color[2]:.4f})")
            # fields['size'].setText(f"{obj.size:.4f}")
            # fields['length'].setText(f"{obj.length:.4f}")
            # fields['transparency'].setText(f"{obj.transparency:.4f}")
