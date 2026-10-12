"""Objects panel: every scene object as a card, with features attached like modifiers.

Implements issue #23 (and Connor's card sketch on it): edit pose / shape /
colour / opacity, toggle visibility, attach motion capture, MAVLink and
control features, create and delete objects, clear the scene, and save or
load scenes.
"""
import os

from PyQt5.QtCore import QTimer, Qt, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog,
                             QDoubleSpinBox, QFileDialog, QFormLayout, QFrame, QGridLayout,
                             QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox, QPushButton,
                             QScrollArea, QSizePolicy, QSlider, QToolButton, QVBoxLayout, QWidget)

from models import frames, scene_io
from models.cad_mesh import CadMesh
from models.gate_frame import GateFrame
from models.rect_prism import RectPrism
from models.sphere import Sphere
from services.paths import data_dir
from ui import animation, theme
from ui.dialogs.shell import DialogShell
from ui.dock.panels.object_features import FEATURES, FeatureContext
from ui.widgets.toast import toast

TYPE_LABELS = {RectPrism: "Box", Sphere: "Sphere", CadMesh: "Mesh", GateFrame: "Gate"}

def _spin(minimum, maximum, decimals, step, suffix=""):
    spin = QDoubleSpinBox()
    spin.setRange(minimum, maximum)
    spin.setDecimals(decimals)
    spin.setSingleStep(step)
    if suffix:
        spin.setSuffix(suffix)
    spin.setKeyboardTracking(False)  # apply when the value is committed, not per keystroke
    spin.setButtonSymbols(QDoubleSpinBox.NoButtons)   # scroll or type; arrows crowd the narrow card
    spin.setProperty("compact", "true")
    spin.setMinimumWidth(64)
    return spin


def _section(text):
    return theme.section(text)


def _discard(widget):
    """Remove a widget now (deleteLater alone leaves it visible until the next event loop pass)."""
    if widget is not None:
        widget.hide()
        widget.setParent(None)
        widget.deleteLater()


def _colour_button_style(colour):
    r, g, b = (int(round(c * 255)) for c in colour[:3])
    return (f"QPushButton {{ background: rgb({r},{g},{b}); border: 1px solid {theme.colour('border_strong')};"
            " border-radius: 10px; padding: 0; min-width: 18px; max-width: 18px; min-height: 18px; max-height: 18px; }")


class ObjectCard(QFrame):
    """One object's card. Rebuilt by the panel when the object list changes."""

    focus_requested = pyqtSignal(object)
    select_requested = pyqtSignal(object)   # clicked (or opened) by the user

    def __init__(self, obj, ctx: FeatureContext, expanded=False, parent=None):
        super().__init__(parent)
        self.obj, self.ctx = obj, ctx
        self.setObjectName("ObjectCard")
        self.setProperty("role", "card")
        self._updating = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(6)
        layout.addLayout(self._build_header())

        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(4, 0, 2, 0)
        self.body_layout.setSpacing(6)
        layout.addWidget(self.body)
        self._build_body()
        self.set_expanded(expanded)
        self.reload()

    # -- header -----------------------------------------------------------

    def _build_header(self):
        row = QHBoxLayout()
        row.setSpacing(6)
        self.expand_button = theme.tool_button("chevron-right", "Show / hide details")
        self.expand_button.clicked.connect(self._on_expand_clicked)
        row.addWidget(self.expand_button)

        self.colour_button = QPushButton()
        self.colour_button.setToolTip("Colour")
        self.colour_button.clicked.connect(self._pick_colour)
        row.addWidget(self.colour_button)

        self.name_edit = QLineEdit(self.obj.name)
        self.name_edit.setFrame(False)
        self.name_edit.setProperty("frame", "false")
        self.name_edit.setProperty("role", "card-title")
        self.name_edit.editingFinished.connect(self._on_name_edited)
        row.addWidget(self.name_edit, 1)

        tag = theme.label(TYPE_LABELS.get(type(self.obj), type(self.obj).__name__), "pill")
        row.addWidget(tag)

        self.visible_check = QCheckBox()
        self.visible_check.setProperty("variant", "eye")
        self.visible_check.setToolTip("Visible in the viewport")
        self.visible_check.toggled.connect(self._on_visible_toggled)
        row.addWidget(self.visible_check)

        focus = theme.tool_button("locate-fixed", "Point the camera at this object (locks the view to it)")
        focus.clicked.connect(lambda: self.focus_requested.emit(self.obj))
        row.addWidget(focus)

        if not self.obj.helper:
            delete = theme.tool_button("trash", "Delete object")
            delete.clicked.connect(self._on_delete_clicked)
            row.addWidget(delete)
        return row

    def _on_expand_clicked(self):
        opening = not self.expanded
        self.set_expanded(opening)
        if opening:
            self.select_requested.emit(self.obj)

    def mousePressEvent(self, event):
        # Clicks on the card itself (labels and gaps; inputs keep their own clicks) select it.
        self.select_requested.emit(self.obj)
        super().mousePressEvent(event)

    def set_selected(self, selected: bool):
        theme.set_props(self, selected="true" if selected else "false")

    # -- body -------------------------------------------------------------

    def _build_body(self):
        body = self.body_layout

        body.addWidget(_section("Pose"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        self.position_spins = [_spin(-1000, 1000, 3, 0.05) for _ in range(3)]
        self.rotation_spins = [_spin(-180, 180, 1, 5.0) for _ in range(3)]
        for col, axis in enumerate("XYZ"):
            grid.addWidget(theme.label(axis, "hint"), 0, col + 1, Qt.AlignCenter)
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
        self.pose_note.setProperty("role", "hint")
        self.pose_note.setProperty("tone", "success")
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
        self.add_feature_button.setText("Add feature")
        self.add_feature_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.add_feature_button.setProperty("variant", "outline")
        self.add_feature_button.setCursor(Qt.PointingHandCursor)
        theme.set_icon(self.add_feature_button, "plus", "accent", 14)
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
            box.setProperty("role", "card-alt")
            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(10, 6, 8, 8)
            header = QHBoxLayout()
            title = theme.label(feature.title, "option-title")
            header.addWidget(title, 1)
            remove = theme.tool_button("x", f"Remove {feature.title}", size=14)
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
        was = self.body.isVisibleTo(self)
        self.body.setVisible(expanded)
        theme.set_icon(self.expand_button, "chevron-down" if expanded else "chevron-right", None, 16)
        if expanded:
            self.refresh_live()
            if not was and self.isVisible():
                animation.fade_in(self.body, animation.FAST)

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
        theme.set_props(self, tracking="true" if self.obj.tracked else "false")
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


class CreateObjectDialog(DialogShell):
    """Pick a type and initial properties for a new object."""

    def __init__(self, parent=None, start_dir="cad_files"):
        super().__init__("Add object", "A box, sphere, mesh or race gate. Drones are easier with "
                                       "“Add drone…”.", accept_text="Add", accept_icon="plus", parent=parent)
        self.resize(460, 0)
        self._mesh_path = ""
        self._start_dir = start_dir
        self._colour = (1.0, 0.55, 0.0, 1.0)

        # A grid rather than a QFormLayout: rows whose widgets are hidden take no space at all.
        grid = QGridLayout()
        grid.setVerticalSpacing(10)
        grid.setHorizontalSpacing(14)
        grid.setColumnStretch(1, 1)
        self.body.addLayout(grid)

        def add_row(label, field):
            row = grid.rowCount()
            if isinstance(label, str):
                label = QLabel(label)
            if label is not None:
                grid.addWidget(label, row, 0, Qt.AlignRight | Qt.AlignVCenter)
            if isinstance(field, QHBoxLayout):
                grid.addLayout(field, row, 1)
            else:
                grid.addWidget(field, row, 1)
            return label

        self.type_combo = QComboBox()
        for label in ("Box", "Sphere", "Mesh (STL / OBJ)", "Race gate"):
            self.type_combo.addItem(label)
        self.type_combo.currentIndexChanged.connect(self._update_fields)
        add_row("Type", self.type_combo)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. Gate 1")
        add_row("Name", self.name_edit)

        position_row = QHBoxLayout()
        self.position_spins = [_spin(-1000, 1000, 3, 0.1, " m") for _ in range(3)]
        for spin in self.position_spins:
            position_row.addWidget(spin)
        self.position_spins[1].setValue(0.5)
        add_row("Position X/Y/Z", position_row)

        size_row = QHBoxLayout()
        size_row.setContentsMargins(0, 0, 0, 0)
        self.size_spins = [_spin(0.01, 100, 3, 0.05, " m") for _ in range(3)]
        for spin in self.size_spins:
            spin.setValue(0.5)
            size_row.addWidget(spin)
        self.size_widget = QWidget()
        self.size_widget.setLayout(size_row)
        self.size_row_label = add_row("Size X/Y/Z", self.size_widget)

        self.radius_spin = _spin(0.005, 50, 3, 0.01, " m")
        self.radius_spin.setValue(0.1)
        self.radius_label = add_row("Radius", self.radius_spin)

        mesh_row = QHBoxLayout()
        mesh_row.setContentsMargins(0, 0, 0, 0)
        self.mesh_path_label = QLabel("No file chosen")
        self.mesh_path_label.setProperty("role", "hint")
        browse = theme.button("Browse…", None, "folder-open")
        browse.clicked.connect(self._choose_mesh)
        mesh_row.addWidget(self.mesh_path_label, 1)
        mesh_row.addWidget(browse)
        self.mesh_widget = QWidget()
        self.mesh_widget.setLayout(mesh_row)
        self.mesh_label = add_row("File", self.mesh_widget)
        self.scale_spin = _spin(0.0001, 1000, 4, 0.01)
        self.scale_spin.setValue(0.001)
        self.scale_spin.setToolTip("Mesh units → metres (0.001 for millimetre CAD exports)")
        self.scale_label = add_row("Scale", self.scale_spin)

        self.colour_button = QPushButton()
        self.colour_button.setStyleSheet(_colour_button_style(self._colour))
        self.colour_button.clicked.connect(self._choose_colour)
        add_row("Colour", self.colour_button)
        grid.itemAtPosition(grid.rowCount() - 1, 1).setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self.controllable_check = QCheckBox("Can be driven from the Command panel")
        self.controllable_check.setChecked(True)
        add_row(None, self.controllable_check)
        self._update_fields()

    def _update_fields(self):
        kind = self.type_combo.currentIndex()
        self.size_row_label.setText("Opening W/H" if kind == 3 else "Size X/Y/Z")
        self.size_spins[2].setVisible(kind != 3)
        for widgets, shown in (((self.size_row_label, self.size_widget), kind in (0, 3)),
                               ((self.radius_label, self.radius_spin), kind == 1),
                               ((self.mesh_label, self.mesh_widget, self.scale_label, self.scale_spin), kind == 2)):
            for w in widgets:
                w.setVisible(shown)
        self.accept_button.setEnabled(kind != 2 or bool(self._mesh_path))

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
    add_drone_requested = pyqtSignal()

    def __init__(self, parent=None, object_service=None, mavlink_service=None, motion_capture_service=None):
        super().__init__(parent)
        self.object_service = object_service
        self.ctx = FeatureContext(object_service, mavlink_service, motion_capture_service)
        self._cards = {}          # id(obj) → ObjectCard
        self._expanded = set()    # id(obj) of expanded cards (kept across rebuilds)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(theme.page_header("Objects", "Everything in the scene. Expand a card to edit it and "
                                                      "attach features."))

        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        self.add_drone_button = theme.button("Add drone…", "primary", "plus",
                                             tooltip="Step-by-step: model, motion capture tracking and "
                                                     "flight controller")
        self.add_drone_button.clicked.connect(lambda: self.add_drone_requested.emit())
        toolbar.addWidget(self.add_drone_button)
        self.add_button = theme.button("Add object", None, "boxes")
        self.add_button.clicked.connect(self._on_add_clicked)
        toolbar.addWidget(self.add_button)
        self.scene_button = QToolButton()
        self.scene_button.setText("Scene")
        self.scene_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.scene_button.setProperty("variant", "outline")
        self.scene_button.setCursor(Qt.PointingHandCursor)
        theme.set_icon(self.scene_button, "layers", None, 16)
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
            object_service.selection_changed.connect(self._on_selection_changed)
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
            empty = theme.label("No objects yet — use “Add drone…” or “Add object”, or create one from a "
                                "Motion Capture subject.", "hint", wrap=True)
            self.cards_layout.addWidget(empty)
        for obj in regular:
            self._add_card(obj)
        if helpers:
            self.cards_layout.addWidget(_section("Scene helpers"))
            for obj in helpers:
                self._add_card(obj)
        live_ids = {id(o) for o in objects}
        self._expanded &= live_ids
        selected = self.object_service.get_selected_object()
        if selected is not None and self.card_for(selected) is not None:
            self.card_for(selected).set_selected(True)

    def _add_card(self, obj):
        card = ObjectCard(obj, self.ctx, expanded=id(obj) in self._expanded)
        card.focus_requested.connect(self.focus_requested)
        card.select_requested.connect(self._on_card_select_requested)
        self._cards[id(obj)] = card
        self.cards_layout.addWidget(card)
        return card

    @pyqtSlot(object)
    def _on_card_select_requested(self, obj):
        if self.object_service is not None:
            self.object_service.select_object(obj)

    @pyqtSlot(object)
    def _on_selection_changed(self, obj):
        """Highlight the selected object's card, open it and bring it into view."""
        for card in self._cards.values():
            card.set_selected(card.obj is obj)
        card = self.card_for(obj) if obj is not None else None
        if card is not None:
            if not card.expanded:
                card.set_expanded(True)
            QTimer.singleShot(0, self._scroll_to_selected)   # once the opened card has its size

    @pyqtSlot()
    def _scroll_to_selected(self):
        selected = self.object_service.get_selected_object() if self.object_service is not None else None
        card = self.card_for(selected) if selected is not None else None
        if card is not None:
            self.scroll.ensureWidgetVisible(card, 0, 12)

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
            toast(f"Scene saved — {os.path.basename(path)}")
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
            toast(f"Scene loaded — {os.path.basename(path)}")
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Load scene", f"Could not load the scene:\n{exc}")
