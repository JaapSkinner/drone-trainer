import os
import tempfile
import unittest

from qt_test_utils import get_app

from PyQt5.QtWidgets import QToolButton

from models import frames
from models.grid import Grid
from models.rect_prism import RectPrism
from models.sphere import Sphere
from services.object_service import ObjectService
from ui.dock.panels.object_features import FEATURES
from ui.dock.panels.objects_panel import CreateObjectDialog, ObjectsPanel


class _FakeMavlink:
    def __init__(self):
        self.calls = []

    def get_available_connection_names(self):
        return ["Drone-1", "Drone-2"]

    def get_connection_by_name(self, name):
        return None

    def link_object(self, obj, name):
        self.calls.append(("link", obj.name, name))
        obj.mavlink_config.enabled = True
        obj.mavlink_config.linked_connection_name = name

    def unlink_object(self, obj, disable=False):
        self.calls.append(("unlink", obj.name, disable))
        obj.mavlink_config.linked_connection_name = ""
        if disable:
            obj.mavlink_config.enabled = False

    def update_object_config(self, obj, config):
        self.calls.append(("update", obj.name))


def _feature(key):
    return next(f for f in FEATURES if f.key == key)


class ObjectsPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = get_app()

    def setUp(self):
        self.objects = ObjectService()
        self.grid = self.objects.add_object(Grid(name="Grid"))
        self.box = self.objects.add_object(RectPrism(name="Box"))
        self.mavlink = _FakeMavlink()
        self.panel = ObjectsPanel(object_service=self.objects, mavlink_service=self.mavlink)
        self.panel.resize(400, 800)
        self.panel.show()

    def tearDown(self):
        self.panel.close()
        self.panel.deleteLater()

    def _card(self, obj, expand=True):
        card = self.panel.card_for(obj)
        if expand:
            card.set_expanded(True)
        return card

    def test_cards_for_objects_and_helpers(self):
        self.assertIsNotNone(self.panel.card_for(self.box))
        helper_card = self.panel.card_for(self.grid)
        self.assertNotIn("Delete object", [b.toolTip() for b in helper_card.findChildren(QToolButton)])
        self.assertIn("Delete object", [b.toolTip() for b in self.panel.card_for(self.box).findChildren(QToolButton)])

    def test_editing_pose_moves_the_object(self):
        card = self._card(self.box)
        card.position_spins[0].setValue(1.5)
        card.position_spins[1].setValue(0.25)
        card.rotation_spins[1].setValue(90.0)
        self.assertAlmostEqual(self.box.pose[0], 1.5)
        self.assertAlmostEqual(self.box.pose[1], 0.25)
        self.assertTrue(frames.quats_equivalent(self.box.pose[3:], frames.euler_deg_to_quat(0, 90, 0), tol=1e-6))

    def test_pose_is_read_only_while_following_mocap_unless_locked(self):
        self.box.set_tracked(True, "cf1")
        card = self._card(self.box)
        card.refresh_live()
        self.assertFalse(card.position_spins[0].isEnabled())
        self.box.pose_locked = True
        card.refresh_live()
        self.assertTrue(card.position_spins[0].isEnabled())

    def test_live_refresh_shows_new_pose(self):
        card = self._card(self.box)
        self.box.set_pose((3.0, 2.0, 1.0, *frames.IDENTITY_QUAT))
        card.refresh_live()
        self.assertAlmostEqual(card.position_spins[0].value(), 3.0)

    def test_opacity_sets_alpha(self):
        card = self._card(self.box)
        card.opacity_slider.setValue(40)
        self.assertAlmostEqual(self.box.colour[3], 0.4)
        self.assertTrue(self.box.is_translucent())

    def test_rename_keeps_names_unique(self):
        self.objects.add_object(RectPrism(name="Gate"))
        card = self._card(self.box)
        card.name_edit.setText("Gate")
        card.name_edit.editingFinished.emit()
        self.assertEqual(self.box.name, "Gate 2")

    def test_adding_and_removing_features(self):
        mocap = _feature("motion_capture")
        self.assertFalse(mocap.is_present(self.box))
        mocap.add(self.box, self.panel.ctx)
        self.assertTrue(self.box.tracked)
        self.assertEqual(self.box.tracking_id, "Box")
        card = self.panel.card_for(self.box)
        self.assertEqual(len(card._feature_editors), 2)  # controllable + motion capture
        mocap.remove(self.box, self.panel.ctx)
        self.assertIsNone(self.box.tracking_id)
        self.assertEqual(len(card._feature_editors), 1)

        _feature("controllable").remove(self.box, self.panel.ctx)
        self.assertFalse(self.box.controllable)

    def test_mavlink_feature_links_through_the_service(self):
        mav = _feature("mavlink")
        mav.add(self.box, self.panel.ctx)
        card = self._card(self.box)
        editor = card._feature_editors[-1]
        index = editor.connection_combo.findData("Drone-2")
        editor.connection_combo.setCurrentIndex(index)
        editor._on_connection_chosen(index)
        self.assertIn(("link", "Box", "Drone-2"), self.mavlink.calls)
        mav.remove(self.box, self.panel.ctx)
        self.assertIn(("unlink", "Box", True), self.mavlink.calls)
        self.assertFalse(self.box.mavlink_config.enabled)

    def test_create_dialog_builds_objects(self):
        dialog = CreateObjectDialog()
        dialog.name_edit.setText("Gate 1")
        dialog.position_spins[0].setValue(2.0)
        dialog.size_spins[0].setValue(1.5)
        box = dialog.build_object()
        self.assertIsInstance(box, RectPrism)
        self.assertEqual(box.name, "Gate 1")
        self.assertEqual(box.dimensions[0], 1.5)
        self.assertEqual(box.pose[0], 2.0)

        dialog.type_combo.setCurrentIndex(1)
        self.assertIsInstance(dialog.build_object(), Sphere)

        dialog.type_combo.setCurrentIndex(2)
        ok = dialog.accept_button
        self.assertFalse(ok.isEnabled())  # a mesh needs a file
        dialog.set_mesh_path("cad_files/basic_quadcopter.stl")
        self.assertTrue(ok.isEnabled())
        self.assertEqual(dialog.build_object().filename, "cad_files/basic_quadcopter.stl")

    def test_add_new_object_expands_its_card(self):
        sphere = self.panel.add_new_object(Sphere(name="Ball"))
        self.assertTrue(self.panel.card_for(sphere).expanded)

    def test_clear_keeps_helpers(self):
        self.panel.clear_objects()
        self.assertEqual([o.name for o in self.objects.get_objects()], ["Grid"])

    def test_save_and_load_scene(self):
        self.box.set_pose((1.0, 2.0, 3.0, *frames.IDENTITY_QUAT))
        self.box.mavlink_config.enabled = True
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "scene.json")
            self.panel.save_scene(path)
            self.panel.clear_objects()
            self.panel.load_scene(path, replace=True)
            names = [o.name for o in self.objects.get_objects()]
            self.assertEqual(names, ["Grid", "Box"])
            loaded = self.objects.get_object("Box")
            self.assertEqual(loaded.pose[:3], (1.0, 2.0, 3.0))
            self.assertIn(("update", "Box"), self.mavlink.calls)  # MAVLink routing restored

            self.panel.load_scene(path, replace=False)
            self.assertEqual(len(self.objects.get_objects()), 4)  # added alongside, names made unique
            self.assertIsNotNone(self.objects.get_object("Box 2"))


if __name__ == "__main__":
    unittest.main()
