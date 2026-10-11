import os
import struct
import tempfile
import unittest

import numpy as np

from models import mesh_data
from models.cad_mesh import CadMesh

QUAD_STL = "cad_files/basic_quadcopter.stl"


def _assert_outward_ccw(test, mesh):
    tris = mesh.positions.reshape(-1, 3, 3)
    winding = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    centroids = tris.mean(axis=1)
    # Closed shapes centred on the origin: counter-clockwise faces point away from the centre.
    test.assertTrue(np.all(np.einsum("ij,ij->i", winding, centroids) > 0))


class PrimitiveTests(unittest.TestCase):
    def test_unit_cube_is_closed_outward_and_counter_clockwise(self):
        cube = mesh_data.unit_cube()
        self.assertEqual(cube.triangle_count, 12)
        _assert_outward_ccw(self, cube)
        lo, hi = cube.bounds()
        self.assertTrue(np.allclose(lo, -0.5) and np.allclose(hi, 0.5))

    def test_cube_edges(self):
        edges = mesh_data.unit_cube_edges().reshape(-1, 2, 3)
        self.assertEqual(len(edges), 12)
        lengths = np.linalg.norm(edges[:, 1] - edges[:, 0], axis=1)
        self.assertTrue(np.allclose(lengths, 1.0))

    def test_sphere_winding_and_radius(self):
        sphere = mesh_data.uv_sphere(16, 8)
        _assert_outward_ccw(self, sphere)
        self.assertTrue(np.allclose(np.linalg.norm(sphere.positions, axis=1), 0.5, atol=1e-6))


class LoaderTests(unittest.TestCase):
    def test_binary_stl(self):
        mesh = mesh_data.load_stl(QUAD_STL)
        self.assertEqual(mesh.triangle_count, 14014)
        self.assertEqual(mesh.positions.shape, (3 * 14014, 3))
        self.assertTrue(np.allclose(np.linalg.norm(mesh.normals, axis=1), 1.0, atol=1e-3))

    def test_zero_normals_in_stl_are_recomputed(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "tri.stl")
            with open(path, "wb") as fh:
                fh.write(b"\0" * 80 + struct.pack("<I", 1))
                fh.write(struct.pack("<12fH", 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0))
            mesh = mesh_data.load_stl(path)
        self.assertTrue(np.allclose(mesh.normals, (0, 0, 1)))

    def test_ascii_stl(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "tri.stl")
            with open(path, "w") as fh:
                fh.write("solid t\n facet normal 0 0 1\n  outer loop\n"
                         "   vertex 0 0 0\n   vertex 1 0 0\n   vertex 0 1 0\n"
                         "  endloop\n endfacet\nendsolid t\n")
            mesh = mesh_data.load_stl(path)
        self.assertEqual(mesh.triangle_count, 1)

    def test_obj_polygons_are_triangulated_and_use_file_normals(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "quad.obj")
            with open(path, "w") as fh:
                fh.write("v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\nvn 0 0 1\n"
                         "f 1//1 2//1 3//1 4//1\n"
                         "f -4 -3 -2\n")  # relative indices, no normals
            mesh = mesh_data.load_obj(path)
        self.assertEqual(mesh.triangle_count, 3)
        self.assertTrue(np.allclose(mesh.normals, (0, 0, 1)))

    def test_bundled_obj_loads(self):
        mesh = mesh_data.load_obj("cad_files/Crayons.obj")
        self.assertGreater(mesh.triangle_count, 395)


class DecimationTests(unittest.TestCase):
    def test_decimation_respects_limit_and_keeps_shape(self):
        mesh = mesh_data.load_stl(QUAD_STL)
        small = mesh_data.decimate(mesh, 3000)
        self.assertLessEqual(small.triangle_count, 3000)
        self.assertGreater(small.triangle_count, 1000)
        lo, hi = mesh.bounds()
        slo, shi = small.bounds()
        diag = np.linalg.norm(hi - lo)
        self.assertLess(np.abs(slo - lo).max(), 0.1 * diag)
        self.assertLess(np.abs(shi - hi).max(), 0.1 * diag)

    def test_small_meshes_are_untouched(self):
        cube = mesh_data.unit_cube()
        self.assertIs(mesh_data.decimate(cube, 100), cube)

    def test_cad_mesh_applies_triangle_limit(self):
        quad = CadMesh(QUAD_STL, max_triangles=2000)
        self.assertEqual(quad.source_triangle_count, 14014)
        self.assertLessEqual(quad.triangle_count, 2000)

    def test_missing_mesh_file_gives_an_empty_object(self):
        missing = CadMesh("cad_files/does_not_exist.stl")
        self.assertEqual(missing.triangle_count, 0)


if __name__ == "__main__":
    unittest.main()
