import json
import os
import tempfile
import unittest

from models import scene_io
from models.axes import Axes
from models.cad_mesh import CadMesh
from models.grid import Grid
from models.rect_prism import RectPrism
from models.sphere import Sphere


class SceneIoTests(unittest.TestCase):
    def _round_trip(self, obj):
        data = json.loads(json.dumps(scene_io.object_to_dict(obj)))  # must be JSON-safe
        return scene_io.object_from_dict(data)

    def test_box_round_trip_with_common_fields(self):
        box = RectPrism(name="Gate", dimensions=(2.0, 0.5, 0.1), colour=(0.2, 0.3, 0.4, 0.5))
        box.set_pose((1.0, 2.0, 3.0, 0.0, 1.0, 0.0, 0.0))
        box.set_tracked(True, "gate1")
        box.pose_locked = True
        box.controllable = False
        box.mavlink_config.enabled = True
        box.mavlink_config.system_id = 7
        box.mavlink_config.linked_connection_name = "Drone-1"

        back = self._round_trip(box)
        self.assertIsInstance(back, RectPrism)
        self.assertEqual(back.name, "Gate")
        self.assertEqual(back.dimensions, (2.0, 0.5, 0.1))
        self.assertEqual(back.colour, (0.2, 0.3, 0.4, 0.5))
        self.assertEqual(back.pose, (1.0, 2.0, 3.0, 0.0, 1.0, 0.0, 0.0))
        self.assertTrue(back.tracked)
        self.assertEqual(back.tracking_id, "gate1")
        self.assertTrue(back.pose_locked)
        self.assertFalse(back.controllable)
        self.assertTrue(back.mavlink_config.enabled)
        self.assertEqual(back.mavlink_config.system_id, 7)
        self.assertEqual(back.mavlink_config.linked_connection_name, "Drone-1")

    def test_other_types_round_trip(self):
        sphere = self._round_trip(Sphere(name="Ball", radius=0.25))
        self.assertEqual(sphere.radius, 0.25)

        grid = self._round_trip(Grid(name="G", half_extent=5, spacing=0.5))
        self.assertEqual((grid.half_extent, grid.spacing), (5, 0.5))

        axes = self._round_trip(Axes(name="Ax", length=2.0))
        self.assertEqual(axes.length, 2.0)

        mesh = CadMesh("cad_files/basic_quadcopter.stl", name="Quad", scale=0.1, max_triangles=3000)
        data = scene_io.object_to_dict(mesh)
        self.assertEqual(data["filename"], "cad_files/basic_quadcopter.stl")  # stored relative
        back = scene_io.object_from_dict(data)
        self.assertEqual(back.scale, (0.1, 0.1, 0.1))
        self.assertLessEqual(back.triangle_count, 3000)

    def test_unknown_types_and_keys_are_tolerated(self):
        objects = scene_io.scene_from_dict({"objects": [
            {"type": "hologram", "name": "?"},
            {"type": "box", "name": "Box", "future_field": 1},
        ]})
        self.assertEqual([o.name for o in objects], ["Box"])

    def test_save_and_load_file(self):
        scene = [Grid(name="Grid"), RectPrism(name="A"), Sphere(name="B")]
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "scenes", "lab.json")
            scene_io.save_scene(scene, path)
            self.assertFalse(os.path.exists(path + ".tmp"))
            loaded = scene_io.load_scene(path)
        self.assertEqual([o.name for o in loaded], ["Grid", "A", "B"])


if __name__ == "__main__":
    unittest.main()
