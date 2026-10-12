"""The scene shown on first launch (before the user has saved one)."""
from models.axes import Axes
from models.cad_mesh import CadMesh
from models.grid import Grid
from models.rect_prism import RectPrism


def build_default_scene():
    # The cubes are props (not controllable), so the Command panel only offers the quad.
    green_cube = RectPrism(name="Green Cube", colour=(0.0, 1.0, 0.0), controllable=False)
    green_cube.set_pose((2.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0))
    blue_cube = RectPrism(name="Blue Cube", colour=(0.0, 0.0, 1.0, 0.5), controllable=False)
    blue_cube.set_pose((0.0, 0.0, 2.0, 1.0, 0.0, 0.0, 0.0))
    return [
        Grid(name="Grid"),
        Axes(name="Axes"),
        RectPrism(name="Red Cube", colour=(1.0, 0.0, 0.0), controllable=False),
        green_cube,
        blue_cube,
        # The STL is in millimetres and 84 mm across; 0.004 shows it as a ~0.34 m quad.
        CadMesh("cad_files/basic_quadcopter.stl", scale=0.004, colour=(0.5, 0.9, 0.5)),
    ]
