from PyQt5.QtWidgets import QWidget, QScrollArea, QVBoxLayout, QFormLayout, QGroupBox, QLabel, QLineEdit, QComboBox

class ObjectPanel(QWidget):
    NavTag = "live_data"
    def __init__(self, gl_widget, set_controlled_object_callback, parent=None, object_service=None):
        super().__init__(parent)
        self.gl_widget = gl_widget
        self.set_controlled_object = set_controlled_object_callback
        self.input_fields = []
        self.object_service = object_service

        layout = QVBoxLayout(self)
        self.combo_box = QComboBox()
        self.combo_box.currentIndexChanged.connect(self.on_object_selected)
        layout.addWidget(QLabel("Select Controlled Object"))
        layout.addWidget(self.combo_box)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        content = QWidget()
        self.scroll_layout = QVBoxLayout(content)
        content.setLayout(self.scroll_layout)

        scroll.setWidget(content)
        layout.addWidget(scroll)

        self.populate()

    def populate(self):
        self.input_fields.clear()
        self.combo_box.clear()
        # clear layout
        while self.scroll_layout.count():
            child = self.scroll_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        for i, obj in enumerate(self.object_service.get_objects()):
            self.combo_box.addItem(obj.name, i)

            group_box = QGroupBox(f"Object {i} - {obj.name}")
            form_layout = QFormLayout()

            x = QLineEdit(f"{obj.pose[0]:.4f}")
            y = QLineEdit(f"{obj.pose[1]:.4f}")
            z = QLineEdit(f"{obj.pose[2]:.4f}")
            xr = QLineEdit(f"{obj.pose[4]:.4f}")
            yr = QLineEdit(f"{obj.pose[5]:.4f}")
            zr = QLineEdit(f"{obj.pose[6]:.4f}")
            color = QLineEdit(f"({obj.colour[0]:.4f}, {obj.colour[1]:.4f}, {obj.colour[2]:.4f})")
            if hasattr(obj, 'dimensions'):
                size = QLineEdit(f"{obj.dimensions[0]:.4f}")
                length = QLineEdit(f"{obj.dimensions[1]:.4f}")
            else:
                size = QLineEdit(f"-1")
                length = QLineEdit(f"-1")

            trans = QLineEdit(f"{obj.colour[3]:.4f}")

            self._connect(x, i, 'x_pos')
            self._connect(y, i, 'y_pos')
            self._connect(z, i, 'z_pos')
            self._connect(xr, i, 'x_rot')
            self._connect(yr, i, 'y_rot')
            self._connect(zr, i, 'z_rot')
            self._connect(color, i, 'color')
            self._connect(size, i, 'size')
            self._connect(length, i, 'length')
            self._connect(trans, i, 'transparency')

            form_layout.addRow(QLabel("X Pos"), x)
            form_layout.addRow(QLabel("Y Pos"), y)
            form_layout.addRow(QLabel("Z Pos"), z)
            form_layout.addRow(QLabel("X Rot"), xr)
            form_layout.addRow(QLabel("Y Rot"), yr)
            form_layout.addRow(QLabel("Z Rot"), zr)
            form_layout.addRow(QLabel("Color"), color)
            form_layout.addRow(QLabel("Size"), size)
            form_layout.addRow(QLabel("Length"), length)
            form_layout.addRow(QLabel("Transparency"), trans)

            group_box.setLayout(form_layout)
            self.scroll_layout.addWidget(group_box)

            self.input_fields.append({
                'x_pos': x, 'y_pos': y, 'z_pos': z,
                'x_rot': xr, 'y_rot': yr, 'z_rot': zr,
                'color': color, 'size': size,
                'length': length, 'transparency': trans
            })

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

    def on_object_selected(self, index):
        obj_index = self.combo_box.itemData(index)
        if obj_index is not None:
            self.set_controlled_object(obj_index)

    def refresh(self):
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
