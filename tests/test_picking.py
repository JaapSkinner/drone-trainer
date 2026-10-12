"""Clicking objects in the 3-D view: picking maths, selection, and what clicks do in the app."""
import math
import os
import tempfile
import unittest
from unittest import mock

import numpy as np
from qt_test_utils import get_app, process_events_for
from PyQt5.QtCore import QEvent, QPoint, Qt
from PyQt5.QtGui import QMouseEvent
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QMessageBox

from models import frames, picking
from models.grid import Grid
from models.rect_prism import RectPrism
from models.sphere import Sphere
from services.object_service import ObjectService
from services.paths import DATA_DIR_ENV_VAR
from ui import theme
from ui.gl_widget.ground_overlay import GroundOverlay, shadow_radius_alpha
from ui.gl_widget.scene_renderer import Camera

W, H = 800, 600


def theme_shadow():
    return theme.rgba("viewport_shadow")


def _drag_to(widget, pos):
    """A real mouse-move with the left button held (QTest.mouseMove doesn't deliver one headless)."""
    QApplication.sendEvent(widget, QMouseEvent(QEvent.MouseMove, pos, Qt.NoButton, Qt.LeftButton, Qt.NoModifier))


def _sphere(name, position, radius=0.5):
    s = Sphere(name=name, radius=radius)
    s.set_pose((*position, *frames.IDENTITY_QUAT))
    return s


class PickingMathsTests(unittest.TestCase):
    def test_ray_through_the_centre_points_at_the_camera_target(self):
        camera = Camera(target=(1.0, 0.5, -2.0))
        origin, direction = picking.screen_ray(camera, W / 2, H / 2, W, H)
        to_target = np.asarray(camera.target) - origin
        np.testing.assert_allclose(direction, to_target / np.linalg.norm(to_target), atol=1e-6)

    def test_picks_the_nearest_object_under_the_pixel(self):
        camera = Camera()
        eye = camera.eye()
        near = _sphere("near", eye * 0.5, radius=0.2)
        far = _sphere("far", (0, 0, 0))
        origin, direction = picking.screen_ray(camera, W / 2, H / 2, W, H)
        obj, distance = picking.pick([far, near], origin, direction)
        self.assertIs(obj, near)
        self.assertAlmostEqual(distance, np.linalg.norm(eye * 0.5 - origin) - 0.2, places=2)
        corner = picking.screen_ray(camera, 2, 2, W, H)
        self.assertEqual(picking.pick([far, near], *corner), (None, None))

    def test_uses_the_real_shape_not_the_bounding_sphere(self):
        rod = RectPrism(dimensions=(2.0, 0.1, 0.1), edge_colour=None)   # bounding radius ≈ 1 m
        origin, down = np.array([0.0, 5.0, 0.0]), np.array([0.0, -1.0, 0.0])
        self.assertAlmostEqual(picking.ray_hits_object(rod, origin, down), 4.95, places=6)
        beside = np.array([0.0, 5.0, 0.5])            # inside the bounding sphere, outside the rod
        self.assertIsNone(picking.ray_hits_object(rod, beside, down))

    def test_follows_rotation_and_scale(self):
        rod = RectPrism(dimensions=(2.0, 0.1, 0.1), edge_colour=None)
        rod.set_pose((3.0, 0.0, 0.0, *frames.quat_from_axis_angle((0, 1, 0), math.pi / 2)))   # now along Z
        down = np.array([0.0, -1.0, 0.0])
        self.assertIsNotNone(picking.ray_hits_object(rod, np.array([3.0, 5.0, 0.8]), down))
        self.assertIsNone(picking.ray_hits_object(rod, np.array([3.8, 5.0, 0.0]), down))

    def test_scene_furniture_and_hidden_objects_cannot_be_picked(self):
        hidden = _sphere("hidden", (0, 0, 0))
        hidden.rendered = False
        origin, direction = np.array([0.0, 5.0, 0.0]), np.array([0.0, -1.0, 0.0])
        self.assertEqual(picking.pick([Grid(), hidden], origin, direction), (None, None))

    def test_triangle_hits_from_either_side(self):
        tri = np.array([[[0, 0, 0], [1, 0, 0], [0, 0, 1]]], dtype=np.float32)
        self.assertAlmostEqual(picking.ray_triangles(np.array([0.2, 1, 0.2]), np.array([0, -1, 0]), tri), 1.0)
        self.assertAlmostEqual(picking.ray_triangles(np.array([0.2, -2, 0.2]), np.array([0, 1, 0]), tri), 2.0)
        self.assertIsNone(picking.ray_triangles(np.array([0.9, 1, 0.9]), np.array([0, -1, 0]), tri))


class SelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = get_app()

    def test_select_clear_and_remove(self):
        service = ObjectService()
        ball = _sphere("ball", (0, 1, 0))
        service.add_object(ball)
        seen = []
        service.selection_changed.connect(seen.append)
        service.select_object(ball)
        service.select_object(ball)                     # no change, no signal
        self.assertIs(service.get_selected_object(), ball)
        service.select_object(_sphere("elsewhere", (0, 0, 0)))   # not in the scene
        self.assertIsNone(service.get_selected_object())
        service.select_object(ball)
        service.remove_object(obj=ball)
        self.assertIsNone(service.get_selected_object())
        self.assertEqual(seen, [ball, None, ball, None])


class GroundOverlayTests(unittest.TestCase):
    def setUp(self):
        self.service = ObjectService()
        self.box = RectPrism(name="box", dimensions=0.3)   # controllable: counts as a drone
        self.box.set_pose((1.0, 2.0, 0.0, *frames.IDENTITY_QUAT))
        self.service.add_object(self.box)
        self.service.add_object(Grid())
        self.overlay = GroundOverlay(self.service)

    def _items(self):
        (marks,) = self.overlay.drawables()          # one per pickable object (not the grid)
        return marks, marks.draw_items()

    def test_shadow_below_and_height_line_for_a_flying_drone(self):
        marks, items = self._items()
        shadow, line = items
        self.assertTrue(shadow.falloff)
        np.testing.assert_allclose(shadow.model[:3, 3], (1.0, 0.003, 0.0), atol=1e-6)
        np.testing.assert_allclose(line.model @ np.array([0, 1, 0, 1]), (1.0, 2.003, 0.0, 1.0), atol=1e-6)

    def test_shadow_fades_and_spreads_with_height(self):
        low = shadow_radius_alpha(0.3, 0.1, 0.3)
        high = shadow_radius_alpha(0.3, 3.0, 0.3)
        self.assertGreater(high[0], low[0])
        self.assertLess(high[1], low[1])

    def test_selected_object_gets_a_ring_even_with_shadows_off(self):
        self.service.select_object(self.box)
        _, items = self._items()
        self.assertEqual(len(items), 4)                # shadow, height line, highlight disc, ring
        self.overlay.enabled = False
        marks, items = self._items()
        self.assertFalse(any(i.falloff and i.colour[:3] == theme_shadow()[:3] for i in items), "no shadow")
        self.assertEqual(len(items), 3)                # height line, highlight disc, ring
        self.service.select_object(None)
        self.assertEqual(self.overlay.drawables(), [])

    def test_hovered_object_gets_a_lighter_ring(self):
        overlay = GroundOverlay(self.service, hovered=lambda: self.box)
        (marks,) = overlay.drawables()
        ring = marks.draw_items()[-1]
        self.assertTrue(ring.is_mesh and not ring.falloff)
        self.assertLess(ring.colour[3], 1.0)           # lighter than the selection ring


class ViewportMouseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = get_app()

    def setUp(self):
        from ui.gl_widget.gl_widget import GLWidget
        self.service = ObjectService()
        self.ball = _sphere("ball", (0, 0, 0), radius=1.0)
        self.service.add_object(self.ball)
        self.view = GLWidget(self.service)
        self.view.resize(W, H)
        self.view.timer.stop()
        self.addCleanup(self.view.deleteLater)
        self.clicked, self.double, self.menus = [], [], []
        self.view.object_clicked.connect(self.clicked.append)
        self.view.object_double_clicked.connect(self.double.append)
        self.view.object_context_menu.connect(lambda obj, pos: self.menus.append(obj))

    def test_click_on_an_object_and_on_empty_space(self):
        QTest.mouseClick(self.view, Qt.LeftButton, pos=QPoint(W // 2, H // 2))
        QTest.mouseClick(self.view, Qt.LeftButton, pos=QPoint(5, 5))
        self.assertEqual(self.clicked, [self.ball, None])

    def test_dragging_orbits_instead_of_clicking(self):
        angle = self.view.camera_angle_y
        QTest.mousePress(self.view, Qt.LeftButton, pos=QPoint(W // 2, H // 2))
        _drag_to(self.view, QPoint(W // 2 + 60, H // 2))
        QTest.mouseRelease(self.view, Qt.LeftButton, pos=QPoint(W // 2 + 60, H // 2))
        self.assertEqual(self.clicked, [])
        self.assertNotEqual(self.view.camera_angle_y, angle)

    def test_a_tiny_wobble_is_still_a_click_and_leaves_the_camera_alone(self):
        angle = self.view.camera_angle_y
        QTest.mousePress(self.view, Qt.LeftButton, pos=QPoint(W // 2, H // 2))
        _drag_to(self.view, QPoint(W // 2 + 2, H // 2))
        QTest.mouseRelease(self.view, Qt.LeftButton, pos=QPoint(W // 2 + 2, H // 2))
        self.assertEqual(self.clicked, [self.ball])
        self.assertEqual(self.view.camera_angle_y, angle)

    def test_double_and_right_click(self):
        QTest.mouseDClick(self.view, Qt.LeftButton, pos=QPoint(W // 2, H // 2))
        self.assertEqual(self.double, [self.ball])
        QTest.mouseClick(self.view, Qt.RightButton, pos=QPoint(W // 2, H // 2))
        self.assertEqual(self.menus, [self.ball])

    def test_selected_and_hovered_objects_glow(self):
        self.assertIsNone(self.view._rim_for(self.ball))
        self.view._set_hovered(self.ball)
        self.assertAlmostEqual(self.view._rim_for(self.ball)[3], self.view.HOVER_RIM)
        self.service.select_object(self.ball)
        self.assertAlmostEqual(self.view._rim_for(self.ball)[3], self.view.SELECTED_RIM)


class AppSelectionTests(unittest.TestCase):
    """Selection and flying through the real MainWindow."""

    @classmethod
    def setUpClass(cls):
        cls.app = get_app()
        # One window for the class (booting takes a while); each test gets fresh drones.
        cls._data_dir = tempfile.TemporaryDirectory()
        cls._env = mock.patch.dict(os.environ, {DATA_DIR_ENV_VAR: cls._data_dir.name})
        cls._env.start()
        from ui.main_window import MainWindow
        cls.window = MainWindow()
        cls.window.show()
        process_events_for(0.2)
        cls.objects = cls.window.object_service

    @classmethod
    def tearDownClass(cls):
        cls.window.close()
        process_events_for(0.1)
        cls._env.stop()
        cls._data_dir.cleanup()

    def setUp(self):
        self.objects.clear_controlled_object()
        self.a = RectPrism(name="Drone A", dimensions=0.3)
        self.b = RectPrism(name="Drone B", dimensions=0.3)
        for drone in (self.a, self.b):
            self.objects.add_object(drone)

    def tearDown(self):
        menu = getattr(self.window, "_object_menu", None)
        if menu is not None:
            menu.close()
        for obj in list(self.objects.get_objects()):
            if obj.name in ("Drone A", "Drone B", "Marker"):
                self.objects.remove_object(obj=obj)

    def test_selecting_highlights_and_opens_the_card(self):
        self.window._show_panel("objects")
        self.objects.select_object(self.b)
        process_events_for(0.05)
        card = self.window.objects_panel.card_for(self.b)
        self.assertEqual(card.property("selected"), "true")
        self.assertTrue(card.expanded)
        self.assertEqual(self.window.objects_panel.card_for(self.a).property("selected"), "false")

    def test_clicking_a_card_selects_its_object(self):
        card = self.window.objects_panel.card_for(self.a)
        card.select_requested.emit(self.a)
        self.assertIs(self.objects.get_selected_object(), self.a)

    def test_fly_selected_button_and_flying(self):
        panel = self.window.command_panel
        self.objects.select_object(self.a)
        self.assertTrue(panel.fly_selected_button.isVisibleTo(panel))
        self.assertIn("Drone A", panel.fly_selected_button.text())
        panel.fly_selected_button.click()
        self.assertIs(self.objects.get_controlled_object(), self.a)
        self.assertFalse(panel.fly_selected_button.isVisibleTo(panel))

    def test_switching_away_from_a_live_drone_asks_first(self):
        self.window.fly_object(self.a)
        with mock.patch.object(type(self.window), "_is_live", return_value=True), \
                mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Cancel) as asked:
            self.window.fly_object(self.b)
        asked.assert_called_once()
        self.assertIs(self.objects.get_controlled_object(), self.a)
        with mock.patch.object(type(self.window), "_is_live", return_value=True), \
                mock.patch.object(QMessageBox, "question", return_value=QMessageBox.Yes):
            self.window.fly_object(self.b)
        self.assertIs(self.objects.get_controlled_object(), self.b)

    def test_objects_that_cannot_be_flown_are_only_selected(self):
        ball = _sphere("Marker", (0, 1, 0))   # spheres aren't controllable by default
        self.objects.add_object(ball)
        self.window.fly_object(ball)
        self.assertIs(self.objects.get_selected_object(), ball)
        self.assertIsNot(self.objects.get_controlled_object(), ball)

    def test_right_click_menu(self):
        menu = self.window._show_object_menu(self.a, QPoint(10, 10))
        texts = [a.text() for a in menu.actions() if a.text()]
        self.assertEqual(texts, ["Fly this drone", "Follow with camera", "Show in Objects", "Drone setup…"])
        self.assertIs(self.objects.get_selected_object(), self.a)
        menu.close()


if __name__ == "__main__":
    unittest.main()
