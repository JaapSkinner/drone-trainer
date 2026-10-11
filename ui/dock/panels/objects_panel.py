"""Objects panel: every scene object as a card, with features attached like modifiers.

Implements issue #23 (and Connor's card sketch on it): edit pose / shape /
colour / opacity, toggle visibility, attach motion capture, MAVLink and
control features, create and delete objects, clear the scene, and save or
load scenes.
"""
import os

from PyQt5.QtCore import QTimer, Qt, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
                             QDoubleSpinBox, QFileDialog, QFormLayout, QFrame, QGridLayout,
                             QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox, QPushButton,
                             QScrollArea, QSizePolicy, QSlider, QToolButton, QVBoxLayout, QWidget)

from models import frames, scene_io
from models.cad_mesh import CadMesh
from models.gate_frame import GateFrame
from models.rect_prism import RectPrism
from models.sphere import Sphere
from services.paths import data_dir
from ui.dock.panels.object_features import FEATURES, FeatureContext

TYPE_LABELS = {RectPrism: "Box", Sphere: "Sphere", CadMesh: "Mesh", GateFrame: "Gate"}

_PANEL_STYLE = """
QFrame#ObjectCard { background: #ffffff; border: 1px solid #d8d8d8; border-radius: 8px; }
QFrame#ObjectCard[tracking="true"] { border-color: #1e7e34; }
QFrame#FeatureBox { background: #f7f7f8; border: 1px solid #e2e2e2; border-radius: 6px; }
QLabel#TypeTag { color: #555; background: #eeeeee; border-radius: 4px; padding: 1px 6px; font-size: 11px; }
QLabel#SectionTitle { font-weight: 600; color: #333; margin-top: 4px; }
QToolButton#CardButton { border: none; padding: 2px 4px; }
QToolButton#CardButton:hover { background: #ececec; border-radius: 4px; }
"""


def _spin(minimum, maximum, decimals, step, suffix=""):
    spin = QDoubleSpinBox()
    spin.setRange(minimum, maximum)
    spin.setDecimals(decimals)
    spin.setSingleStep(step)
    if suffix:
        spin.setSuffix(suffix)
    spin.setKeyboardTracking(False)  # apply when the value is committed, not per keystroke
    spin.setMinimumWidth(70)
    return spin


def _section(text):
    label = QLabel(text)
    label.setObjectName("SectionTitle")
    return label


def _discard(widget):
    """Remove a widget now (deleteLater alone leaves it visible until the next event loop pass)."""
    if widget is not None:
        widget.hide()
        widget.setParent(None)
        widget.deleteLater()


def _colour_button_style(colour):
    r, g, b = (int(round(c * 255)) for c in colour[:3])
    return (f"QPushButton {{ background: rgb({r},{g},{b}); border: 1px solid #888;"
            " border-radius: 4px; min-width: 18px; max-width: 18px; min-height: 18px; max-height: 18px; }")


class ObjectCard(QFrame):
    """One object's card. Rebuilt by the panel when the object list changes."""

    focus_requested = pyqtSignal(object)

    def __init__(self, obj, ctx: FeatureContext, expanded=False, parent=None):
        super().__init__(parent)
        self.obj, self.ctx = obj, ctx
        self.setObjectName("ObjectCard")
        self._updating = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 8)
        layout.setSpacing(4)
        layout.addLayout(self._build_header())

        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(4, 0, 0, 0)
        self.body_layout.setSpacing(4)
        layout.addWidget(self.body)
        self._build_body()
        self.set_expanded(expanded)
        self.reload()

    # -- header -----------------------------------------------------------

    def _build_header(self):
        row = QHBoxLayout()
        row.setSpacing(6)
        self.expand_button = QToolButton()
        self.expand_button.setObjectName("CardButton")
        self.expand_button.clicked.connect(lambda: self.set_expanded(not self.expanded))
        row.addWidget(self.expand_button)

        self.colour_button = QPushButton()
        self.colour_button.setToolTip("Colour")
        self.colour_button.clicked.connect(self._pick_colour)
        row.addWidget(self.colour_button)

        self.name_edit = QLineEdit(self.obj.name)
        self.name_edit.setFrame(False)
        self.name_edit.setStyleSheet("font-weight: 600; background: transparent;")
        self.name_edit.editingFinished.connect(self._on_name_edited)
        row.addWidget(self.name_edit, 1)

        tag = QLabel(TYPE_LABELS.get(type(self.obj), type(self.obj).__name__))
        tag.setObjectName("TypeTag")
        row.addWidget(tag)

        self.visible_check = QCheckBox()
        self.visible_check.setToolTip("Visible in the viewport")
        self.visible_check.toggled.connect(self._on_visible_toggled)
        row.addWidget(self.visible_check)

        focus = QToolButton()
        focus.setObjectName("CardButton")
        focus.setText("◎")
        focus.setToolTip("Point the camera at this object (locks the view to it)")
        focus.clicked.connect(lambda: self.focus_requested.emit(self.obj))
        row.addWidget(focus)

        if not self.obj.helper:
            delete = QToolButton()
            delete.setObjectName("CardButton")
            delete.setText("✕")
            delete.setToolTip("Delete object")
            delete.clicked.connect(self._on_delete_clicked)
            row.addWidget(delete)
        return row

    # -- body -------------------------------------------------------------

    def _build_body(self):
        body = self.body_layout

        body.addWidget(_section("Pose"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        self.position_spins = [_spin(-1000, 1000, 3, 0.05) for _ in range(3)]
        self.rotation_spins = [_spin(-180, 180, 1, 5.0) for _ in range(3)]
        for col, axis in enumerate("XYZ"):
            grid.addWidget(QLabel(axis), 0, col + 1, Qt.AlignCenter)
        grid.addWidget(QLabel("Position (m)"), 1, 0)
        grid.addWidget(QLabel("Rotation (°)"), 2, 0)
        for col in range(3):
            grid.addWidget(self.position_spins[col], 1, col + 1)
            grid.addWidget(self.rotation_spins[col], 2, col + 1)
            self.position_spins[col].valueChanged.connect(self._on_pose_edited)
            self.rotation_spins[col].valueChanged.connect(self._on_pose_edited)
        body.addLayout(grid)
        self.pose_note = QLabel()
        self.pose_note.setWordWrap(True)
        self.pose_note.setStyleSheet("color: #1e7e34; font-size: 11px;")
        body.addWidget(self.pose_note)

        shape = self._build_shape_editor()
        if shape is not None:
            body.addWidget(_section("Shape"))
            body.addWidget(shape)

        body.addWidget(_section("Appearance"))
        opacity_row = QHBoxLayout()
        opacity_row.addWidget(QLabel("Opacity"))
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(5, 100)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        opacity_row.addWidget(self.opacity_slider, 1)
        self.opacity_label = QLabel()
        self.opacity_label.setMinimumWidth(36)
        opacity_row.addWidget(self.opacity_label)
        body.addLayout(opacity_row)

        self.features_title = _section("Features")
        body.addWidget(self.features_title)
        self.features_container = QVBoxLayout()
        self.features_container.setSpacing(4)
        body.addLayout(self.features_container)
        self.add_feature_button = QToolButton()
        self.add_feature_button.setText("+ Add feature")
        self.add_feature_button.setPopupMode(QToolButton.InstantPopup)
        self.add_feature_button.setMenu(QMenu(self.add_feature_button))
        self.add_feature_button.menu().aboutToShow.connect(self._populate_feature_menu)
        body.addWidget(self.add_feature_button, 0, Qt.AlignLeft)
        self._feature_editors = []

    def _build_shape_editor(self):
        obj = self.obj
        widget = QWidget()
        form = QFormLayout(widget)
        form.setContentsMargins(0, 0, 0, 0)
        if isinstance(obj, RectPrism):
            row = QHBoxLayout()
            self.dimension_spins = [_spin(0.01, 100, 3, 0.05) for _ in range(3)]
            for spin, value in zip(self.dimension_spins, obj.dimensions):
                spin.setValue(value)
                spin.valueChanged.connect(self._on_dimensions_edited)
                row.addWidget(spin)
            form.addRow("Size X/Y/Z (m):", row)
        elif isinstance(obj, Sphere):
            self.radius_spin = _spin(0.005, 50, 3, 0.01)
            self.radius_spin.setValue(obj.radius)
            self.radius_spin.valueChanged.connect(self._on_radius_edited)
            form.addRow("Radius (m):", self.radius_spin)
        elif isinstance(obj, GateFrame):
            row = QHBoxLayout()
            self.gate_spins = [_spin(0.1, 20, 2, 0.05) for _ in range(2)]
            for spin, value in zip(self.gate_spins, (obj.width, obj.height)):
                spin.setValue(value)
                spin.valueChanged.connect(self._on_gate_size_edited)
                row.addWidget(spin)
            form.addRow("Opening W/H (m):", row)
        elif isinstance(obj, CadMesh):
            form.addRow("File:", QLabel(os.path.basename(obj.filename)))
            self.scale_spin = _spin(0.0001, 1000, 4, 0.01)
            self.scale_spin.setValue(obj.scale[0])
            self.scale_spin.valueChanged.connect(self._on_scale_edited)
            form.addRow("Scale:", self.scale_spin)
            info = f"{obj.triangle_count:,} triangles"
            if obj.triangle_count != obj.source_triangle_count:
                info += f" (simplified from {obj.source_triangle_count:,})"
            form.addRow("Detail:", QLabel(info))
        else:
            return None
        return widget

    def _rebuild_features(self):
        while self.features_container.count():
            _discard(self.features_container.takeAt(0).widget())
        self._feature_editors = []
        applicable = [f for f in FEATURES if f.applies_to(self.obj)]
        present = [f for f in applicable if f.is_present(self.obj)]
        for feature in present:
            box = QFrame()
            box.setObjectName("FeatureBox")
            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(8, 4, 8, 6)
            header = QHBoxLayout()
            title = QLabel(feature.title)
            title.setStyleSheet("font-weight: 600;")
            header.addWidget(title, 1)
            remove = QToolButton()
            remove.setObjectName("CardButton")
            remove.setText("✕")
            remove.setToolTip(f"Remove {feature.title}")
            remove.clicked.connect(lambda _c=False, f=feature: f.remove(self.obj, self.ctx))
            header.addWidget(remove)
            box_layout.addLayout(header)
            editor = feature.build_editor(self.obj, self.ctx)
            box_layout.addWidget(editor)
            self._feature_editors.append(editor)
            self.features_container.addWidget(box)
        visible = bool(applicable)
        self.features_title.setVisible(visible)
        self.add_feature_button.setVisible(visible and len(present) < len(applicable))

    def _populate_feature_menu(self):
        menu = self.add_feature_button.menu()
        menu.clear()
        for feature in FEATURES:
            if feature.applies_to(self.obj) and not feature.is_present(self.obj):
                action = menu.addAction(feature.title)
                action.setToolTip(feature.description)
                action.triggered.connect(lambda _c=False, f=feature: f.add(self.obj, self.ctx))

    # -- state <-> widgets ---------------------------------------------------

    @property
    def expanded(self):
        return self.body.isVisibleTo(self)

    def set_expanded(self, expanded: bool):
        self.body.setVisible(expanded)
        self.expand_button.setText("▾" if expanded else "▸")
        if expanded:
            self.refresh_live()

    def reload(self):
        """Re-read every property of the object (after a property change)."""
        self._updating = True
        try:
            if not self.name_edit.hasFocus():
                self.name_edit.setText(self.obj.name)
                self.name_edit.setCursorPosition(0)
            self.colour_button.setStyleSheet(_colour_button_style(self.obj.colour))
            self.visible_check.setChecked(self.obj.rendered)
            alpha = int(round(self.obj.colour[3] * 100))
            self.opacity_slider.setValue(alpha)
            self.opacity_label.setText(f"{alpha}%")
        finally:
            self._updating = False
        self.setProperty("tracking", "true" if self.obj.tracked else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        self._rebuild_features()
        self.refresh_live()

    def _pose_driven_by_mocap(self):
        return self.obj.tracked and not self.obj.pose_locked

    def refresh_live(self):
        """Update values that change continuously (pose, feature status)."""
        if not self.expanded:
            return
        driven = self._pose_driven_by_mocap()
        editing = any(s.hasFocus() for s in self.position_spins + self.rotation_spins)
        if not editing:
            self._updating = True
            try:
                for spin, value in zip(self.position_spins, self.obj.pose[:3]):
                    spin.setValue(value)
                for spin, value in zip(self.rotation_spins, frames.quat_to_euler_deg(self.obj.pose[3:])):
                    spin.setValue(value)
            finally:
                self._updating = False
        for spin in self.position_spins + self.rotation_spins:
            spin.setEnabled(not driven)
        self.pose_note.setVisible(driven)
        if driven:
            self.pose_note.setText(f"Following mocap subject '{self.obj.tracking_id}'. "
                                   "Lock the pose or stop following to edit.")
        for editor in self._feature_editors:
            editor.refresh()

    # -- edits -------------------------------------------------------------

    def _on_name_edited(self):
        name = self.ctx.object_service.rename_object(self.obj, self.name_edit.text())
        self.name_edit.setText(name)
        self.name_edit.setCursorPosition(0)

    def _on_visible_toggled(self, checked):
        if not self._updating:
            self.obj.rendered = checked
            self.ctx.object_service.notify_object_changed(self.obj)

    def _pick_colour(self):
        initial = QColor.fromRgbF(*self.obj.colour[:3])
        colour = QColorDialog.getColor(initial, self, f"Colour — {self.obj.name}")
        if colour.isValid():
            self.obj.colour = (colour.redF(), colour.greenF(), colour.blueF(), self.obj.colour[3])
            self.ctx.object_service.notify_object_changed(self.obj)

    def _on_opacity_changed(self, value):
        self.opacity_label.setText(f"{value}%")
        if not self._updating:
            self.obj.colour = (*self.obj.colour[:3], value / 100.0)
            self.ctx.object_service.notify_object_changed(self.obj)

    def _on_pose_edited(self, _value=None):
        if self._updating or self._pose_driven_by_mocap():
            return
        position = [s.value() for s in self.position_spins]
        q = frames.euler_deg_to_quat(*(s.value() for s in self.rotation_spins))
        self.obj.set_pose((*position, *q))

    def _on_dimensions_edited(self, _value=None):
        self.obj.set_dimensions(tuple(s.value() for s in self.dimension_spins))

    def _on_gate_size_edited(self, _value=None):
        self.obj.width, self.obj.height = (s.value() for s in self.gate_spins)

    def _on_radius_edited(self, value):
        self.obj.radius = value

    def _on_scale_edited(self, value):
        self.obj.scale = (value, value, value)

    def _on_delete_clicked(self):
        answer = QMessageBox.question(self, "Delete object", f"Delete '{self.obj.name}'?",
                                      QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer == QMessageBox.Yes:
            self.ctx.object_service.remove_object(obj=self.obj)


class CreateObjectDialog(QDialog):
    """Pick a type and initial properties for a new object."""

    def __init__(self, parent=None, start_dir="cad_files"):
        super().__init__(parent)
        self.setWindowTitle("Add object")
        self._mesh_path = ""
        self._start_dir = start_dir
        self._colour = (1.0, 0.55, 0.0, 1.0)

        form = QFormLayout(self)
        self.type_combo = QComboBox()
        for label in ("Box", "Sphere", "Mesh (STL / OBJ)", "Race gate"):
            self.type_combo.addItem(label)
        self.type_combo.currentIndexChanged.connect(self._update_fields)
        form.addRow("Type:", self.type_combo)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. Gate 1")
        form.addRow("Name:", self.name_edit)

        position_row = QHBoxLayout()
        self.position_spins = [_spin(-1000, 1000, 3, 0.1, " m") for _ in range(3)]
        for spin in self.position_spins:
            position_row.addWidget(spin)
        self.position_spins[1].setValue(0.5)
        form.addRow("Position X/Y/Z:", position_row)

        size_row = QHBoxLayout()
        self.size_spins = [_spin(0.01, 100, 3, 0.05, " m") for _ in range(3)]
        for spin in self.size_spins:
            spin.setValue(0.5)
            size_row.addWidget(spin)
        self.size_row_label = QLabel("Size X/Y/Z:")
        self.size_widget = QWidget()
        self.size_widget.setLayout(size_row)
        form.addRow(self.size_row_label, self.size_widget)

        self.radius_label = QLabel("Radius:")
        self.radius_spin = _spin(0.005, 50, 3, 0.01, " m")
        self.radius_spin.setValue(0.1)
        form.addRow(self.radius_label, self.radius_spin)

        self.mesh_label = QLabel("File:")
        mesh_row = QHBoxLayout()
        self.mesh_path_label = QLabel("No file chosen")
        self.mesh_path_label.setStyleSheet("color: #666;")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._choose_mesh)
        mesh_row.addWidget(self.mesh_path_label, 1)
        mesh_row.addWidget(browse)
        self.mesh_widget = QWidget()
        self.mesh_widget.setLayout(mesh_row)
        form.addRow(self.mesh_label, self.mesh_widget)
        self.scale_label = QLabel("Scale:")
        self.scale_spin = _spin(0.0001, 1000, 4, 0.01)
        self.scale_spin.setValue(0.001)
        self.scale_spin.setToolTip("Mesh units → metres (0.001 for millimetre CAD exports)")
        form.addRow(self.scale_label, self.scale_spin)

        self.colour_button = QPushButton()
        self.colour_button.setStyleSheet(_colour_button_style(self._colour))
        self.colour_button.clicked.connect(self._choose_colour)
        form.addRow("Colour:", self.colour_button)

        self.controllable_check = QCheckBox("Can be driven from the Command panel")
        self.controllable_check.setChecked(True)
        form.addRow("", self.controllable_check)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        form.addRow(self.buttons)
        self._update_fields()

    def _update_fields(self):
        kind = self.type_combo.currentIndex()
        self.size_row_label.setText("Opening W/H:" if kind == 3 else "Size X/Y/Z:")
        self.size_spins[2].setVisible(kind != 3)
        for widgets, shown in (((self.size_row_label, self.size_widget), kind in (0, 3)),
                               ((self.radius_label, self.radius_spin), kind == 1),
                               ((self.mesh_label, self.mesh_widget, self.scale_label, self.scale_spin), kind == 2)):
            for w in widgets:
                w.setVisible(shown)
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(kind != 2 or bool(self._mesh_path))

    def _choose_mesh(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose mesh", self._start_dir,
                                              "Meshes (*.stl *.obj);;All files (*)")
        if path:
            self.set_mesh_path(path)

    def set_mesh_path(self, path):
        self._mesh_path = path
        self.mesh_path_label.setText(os.path.basename(path))
        if not self.name_edit.text():
            self.name_edit.setText(os.path.splitext(os.path.basename(path))[0])
        self._update_fields()

    def _choose_colour(self):
        colour = QColorDialog.getColor(QColor.fromRgbF(*self._colour[:3]), self, "Colour")
        if colour.isValid():
            self._colour = (colour.redF(), colour.greenF(), colour.blueF(), 1.0)
            self.colour_button.setStyleSheet(_colour_button_style(self._colour))

    def build_object(self):
        kind = self.type_combo.currentIndex()
        name = self.name_edit.text().strip() or None
        if kind == 0:
            obj = RectPrism(name=name or "Box", dimensions=tuple(s.value() for s in self.size_spins),
                            colour=self._colour)
        elif kind == 1:
            obj = Sphere(name=name or "Sphere", radius=self.radius_spin.value(), colour=self._colour)
        elif kind == 2:
            obj = CadMesh(self._mesh_path, name=name, scale=self.scale_spin.value(), colour=self._colour)
        else:
            obj = GateFrame(name=name or "Gate", width=self.size_spins[0].value(),
                            height=self.size_spins[1].value(), colour=self._colour)
            obj.gate_order = 1
        obj.controllable = self.controllable_check.isChecked() and kind != 3
        obj.set_pose((*(s.value() for s in self.position_spins), *frames.IDENTITY_QUAT))
        return obj


class ObjectsPanel(QWidget):
    NavTag = "objects"
    LIVE_REFRESH_MS = 100

    focus_requested = pyqtSignal(object)  # camera should lock onto this object

    def __init__(self, parent=None, object_service=None, mavlink_service=None, motion_capture_service=None):
        super().__init__(parent)
        self.object_service = object_service
        self.ctx = FeatureContext(object_service, mavlink_service, motion_capture_service)
        self._cards = {}          # id(obj) → ObjectCard
        self._expanded = set()    # id(obj) of expanded cards (kept across rebuilds)
        self.setStyleSheet(_PANEL_STYLE)

        layout = QVBoxLayout(self)
        title = QLabel("Objects")
        title.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 6px;")
        layout.addWidget(title)

        toolbar = QHBoxLayout()
        self.add_button = QPushButton("+ Add object")
        self.add_button.clicked.connect(self._on_add_clicked)
        toolbar.addWidget(self.add_button)
        self.scene_button = QToolButton()
        self.scene_button.setText("Scene ▾")
        self.scene_button.setPopupMode(QToolButton.InstantPopup)
        scene_menu = QMenu(self.scene_button)
        self.save_action = scene_menu.addAction("Save scene…", self._on_save_clicked)
        self.load_action = scene_menu.addAction("Load scene…", self._on_load_clicked)
        scene_menu.addSeparator()
        self.clear_action = scene_menu.addAction("Clear all objects", self._on_clear_clicked)
        self.scene_button.setMenu(scene_menu)
        toolbar.addWidget(self.scene_button)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        self.cards_layout = QVBoxLayout(content)
        self.cards_layout.setContentsMargins(0, 0, 8, 0)
        self.cards_layout.setSpacing(6)
        self.cards_layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(content)
        self.scroll = scroll
        layout.addWidget(scroll, 1)

        if object_service is not None:
            object_service.objects_changed.connect(self.rebuild)
            object_service.object_changed.connect(self._on_object_changed)
        self.rebuild()

        self._live_timer = QTimer(self)
        self._live_timer.timeout.connect(self._refresh_live)
        self._live_timer.start(self.LIVE_REFRESH_MS)

    # -- cards ---------------------------------------------------------------

    def card_for(self, obj):
        return self._cards.get(id(obj))

    def rebuild(self):
        for card in self._cards.values():
            if card.expanded:
                self._expanded.add(id(card.obj))
            else:
                self._expanded.discard(id(card.obj))
        self._cards = {}
        while self.cards_layout.count():
            _discard(self.cards_layout.takeAt(0).widget())
        if self.object_service is None:
            return

        objects = self.object_service.get_objects()
        regular = [o for o in objects if not o.helper]
        helpers = [o for o in objects if o.helper]
        if not regular:
            empty = QLabel("No objects yet — use “+ Add object”, or create one from a "
                           "Motion Capture subject.")
            empty.setWordWrap(True)
            empty.setStyleSheet("color: #666; font-style: italic; padding: 8px;")
            self.cards_layout.addWidget(empty)
        for obj in regular:
            self._add_card(obj)
        if helpers:
            self.cards_layout.addWidget(_section("Scene helpers"))
            for obj in helpers:
                self._add_card(obj)
        live_ids = {id(o) for o in objects}
        self._expanded &= live_ids

    def _add_card(self, obj):
        card = ObjectCard(obj, self.ctx, expanded=id(obj) in self._expanded)
        card.focus_requested.connect(self.focus_requested)
        self._cards[id(obj)] = card
        self.cards_layout.addWidget(card)
        return card

    def _on_object_changed(self, obj):
        card = self.card_for(obj)
        if card is not None:
            card.reload()

    def _refresh_live(self):
        if not self.isVisible():
            return
        for card in self._cards.values():
            card.refresh_live()

    # -- toolbar actions -------------------------------------------------------

    def _on_add_clicked(self):
        dialog = CreateObjectDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            self.add_new_object(dialog.build_object())

    def add_new_object(self, obj):
        if obj.gate_order is not None:  # new gates go at the end of the course
            used = [o.gate_order for o in self.object_service.get_objects() if o.gate_order is not None]
            obj.gate_order = max(used, default=0) + 1
        self._expanded.add(id(obj))
        self.object_service.add_object(obj)
        card = self.card_for(obj)
        if card is not None:
            QTimer.singleShot(0, lambda: self.scroll.ensureWidgetVisible(card))
        return obj

    def clear_objects(self):
        self.object_service.clear_objects(keep=lambda o: o.helper)

    def _on_clear_clicked(self):
        count = sum(1 for o in self.object_service.get_objects() if not o.helper)
        if not count:
            return
        answer = QMessageBox.question(self, "Clear all objects",
                                      f"Delete all {count} object(s)? The grid and axes are kept.",
                                      QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer == QMessageBox.Yes:
            self.clear_objects()

    @staticmethod
    def scenes_dir():
        path = os.path.join(data_dir(), "scenes")
        os.makedirs(path, exist_ok=True)
        return path

    def save_scene(self, path):
        scene_io.save_scene(self.object_service.get_objects(), path)

    def load_scene(self, path, replace=True):
        objects = scene_io.load_scene(path)
        if replace:
            self.object_service.clear_objects()
        self.object_service.add_objects(objects)
        mavlink = self.ctx.mavlink_service
        if mavlink is not None:
            for obj in objects:
                if obj.mavlink_config.enabled:
                    mavlink.update_object_config(obj, obj.mavlink_config)
        return objects

    def _on_save_clicked(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save scene", os.path.join(self.scenes_dir(), "scene.json"),
                                              "Scenes (*.json)")
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            self.save_scene(path)
        except OSError as exc:
            QMessageBox.critical(self, "Save scene", f"Could not save the scene:\n{exc}")

    def _on_load_clicked(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load scene", self.scenes_dir(), "Scenes (*.json)")
        if not path:
            return
        box = QMessageBox(QMessageBox.Question, "Load scene",
                          "Replace the current scene, or add these objects to it?", parent=self)
        replace = box.addButton("Replace", QMessageBox.AcceptRole)
        add = box.addButton("Add to scene", QMessageBox.AcceptRole)
        box.addButton(QMessageBox.Cancel)
        box.exec_()
        if box.clickedButton() not in (replace, add):
            return
        try:
            self.load_scene(path, replace=box.clickedButton() is replace)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Load scene", f"Could not load the scene:\n{exc}")
