"""What scene objects ask the renderer to draw (no GPU needed; pixels are checked in test_rendering)."""
import math
import unittest

import numpy as np

from models import frames
from models.axes import Axes
from models.cad_mesh import CadMesh
from models.gate_frame import GateFrame
from models.grid import Grid
from models.polyline import Polyline
from models.rect_prism import RectPrism
from models.render_items import IDENTITY, Lines, Mesh, pose_matrix
from models.sphere import Sphere

QUAD = "cad_files/basic_quadcopter.stl"


def _apply(matrix, point):
    return (matrix @ np.array([*point, 1.0]))[:3]


class DrawItemTests(unittest.TestCase):
    def test_pose_places_local_geometry_in_the_scene(self):
        box = RectPrism(dimensions=(2.0, 1.0, 0.5), edge_colour=None)
        quarter_turn = frames.quat_from_axis_angle((0, 1, 0), math.pi / 2)
        box.set_pose((1.0, 2.0, 3.0, *quarter_turn))
        (faces,) = box.draw_items()
        # The unit cube's +X corner, scaled by the size and turned 90° about +Y, ends up along -Z.
        np.testing.assert_allclose(_apply(faces.model, (0.5, 0.0, 0.0)), (1.0, 2.0, 2.0), atol=1e-6)

    def test_model_matrix_follows_pose_changes(self):
        sphere = Sphere()
        first = sphere.model_matrix()
        self.assertIs(sphere.model_matrix(), first)          # cached while the pose stays
        sphere.set_pose((1.0, 0.0, 0.0, *frames.IDENTITY_QUAT))
        np.testing.assert_allclose(sphere.model_matrix()[:3, 3], (1.0, 0.0, 0.0))

    def test_box_faces_and_outline(self):
        box = RectPrism(colour=(1, 0, 0), edge_colour=(0, 0, 0))
        faces, edges = box.draw_items()
        self.assertIsInstance(faces.geometry, Mesh)
        self.assertTrue(faces.offset, "faces are pushed back so the outline wins")
        self.assertFalse(faces.cull)
        self.assertIsInstance(edges.geometry, Lines)
        self.assertFalse(edges.lit)

        glass = RectPrism(colour=(0, 0, 1, 0.5), edge_colour=None)
        (faces,) = glass.draw_items()
        self.assertTrue(faces.translucent)
        self.assertTrue(faces.cull, "a translucent box shows one layer")

    def test_fading_reaches_every_item(self):
        box = RectPrism(colour=(1, 0, 0), edge_colour=(0, 0, 0))
        box.draw_alpha_scale = 0.3
        self.assertTrue(all(abs(item.colour[3] - 0.3) < 1e-9 for item in box.draw_items()))
        axes = Axes()
        axes.draw_alpha_scale = 0.5
        self.assertEqual(axes.draw_items()[0].colour[3], 0.5)

    def test_shapes_share_geometry(self):
        self.assertIs(Sphere().draw_items()[0].geometry, Sphere(radius=3).draw_items()[0].geometry)
        gate = GateFrame(width=1.2, height=0.8)
        bars = gate.draw_items()
        self.assertEqual(len(bars), 4)
        self.assertIs(bars[0].geometry, RectPrism().draw_items()[0].geometry)

    def test_meshes_from_the_same_file_share_one_copy(self):
        a = CadMesh(QUAD, scale=0.004)
        b = CadMesh(QUAD, scale=0.01)
        self.assertIs(a.draw_items()[0].geometry, b.draw_items()[0].geometry)
        self.assertGreater(a.triangle_count, 0)

    def test_released_mesh_reloads_when_drawn_again(self):
        mesh = CadMesh(QUAD, scale=0.004)
        mesh.release_gl()
        (item,) = mesh.draw_items()
        self.assertEqual(item.geometry.triangle_count, mesh.triangle_count)

    def test_mesh_normals_stay_right_under_non_uniform_scale(self):
        uniform = CadMesh(QUAD, scale=0.004).draw_items()[0]
        self.assertEqual(uniform.normal_scale, (1.0, 1.0, 1.0))
        stretched = CadMesh(QUAD, scale=(1.0, 2.0, 4.0)).draw_items()[0]
        np.testing.assert_allclose(stretched.normal_scale, (1.0, 0.25, 0.0625))
        # mat3(model) · (normal_scale · n) is parallel to the exact (M⁻¹)ᵀ · n.
        model = pose_matrix((0, 0, 0, *frames.quat_from_axis_angle((1, 1, 0), 0.7))) @ stretched.model
        n = np.array([0.3, 0.5, 0.8])
        shader = model[:3, :3] @ (np.asarray(stretched.normal_scale) * n)
        exact = np.linalg.inv(model[:3, :3]).T @ n
        np.testing.assert_allclose(shader / np.linalg.norm(shader), exact / np.linalg.norm(exact), atol=1e-5)

    def test_grid_is_static_and_lines_from_overlays_are_not(self):
        (grid,) = Grid().local_items()
        self.assertTrue(grid.geometry.static)
        self.assertIs(grid.model, IDENTITY)        # no local transform: drawn with the pose alone
        line = Polyline([(0, 0, 0), (1, 0, 0)], (0, 0, 0, 1), width=2.0)
        (item,) = line.draw_items()
        self.assertFalse(item.geometry.static)
        self.assertEqual(item.width, 2.0)
        self.assertEqual(Polyline().draw_items(), [])

    def test_hidden_objects_still_describe_themselves(self):
        # Visibility is the renderer's call (it skips objects with rendered=False).
        box = RectPrism()
        box.rendered = False
        self.assertTrue(box.draw_items())


if __name__ == "__main__":
    unittest.main()
