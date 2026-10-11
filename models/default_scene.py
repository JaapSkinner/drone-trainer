"""The scene shown on first launch (before the user has saved one)."""
from models.axes import Axes
from models.cad_mesh import CadMesh
from models.grid import Grid
from models.rect_prism import RectPrism


def build_default_scene():
    green_cube = RectPrism(name="Green Cube", colour=(0.0, 1.0, 0.0))
    green_cube.set_pose((2.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0))
    blue_cube = RectPrism(name="Blue Cube", colour=(0.0, 0.0, 1.0, 0.5))
    blue_cube.set_pose((0.0, 0.0, 2.0, 1.0, 0.0, 0.0, 0.0))
    return [
        Grid(name="Grid", colour=(0.68, 0.68, 0.68, 1.0)),
        Axes(name="Axes"),
        RectPrism(name="Red Cube", colour=(1.0, 0.0, 0.0)),
        green_cube,
        blue_cube,
        CadMesh("cad_files/basic_quadcopter.stl", scale=0.05, colour=(0.5, 0.9, 0.5)),
    ]
