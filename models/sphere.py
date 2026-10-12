from models import mesh_data
from models.render_items import DrawItem, Mesh, scale_matrix
from models.scene_object import SceneObject

# Unit-diameter sphere shared by every Sphere (setpoints, markers, zones…).
_SPHERE = Mesh.from_mesh_data(mesh_data.uv_sphere(), "sphere")


class Sphere(SceneObject):
    """A sphere — useful as a marker, waypoint or setpoint indicator."""

    def __init__(self, pose=None, name=None, radius=0.1, colour=None, controllable=False):
        super().__init__(pose, name or "Unnamed Sphere", controllable=controllable, colour=colour)
        self.radius = float(radius)

    def bounding_radius(self) -> float:
        return self.radius

    def local_items(self):
        # Closed surface: culling also keeps a translucent sphere to a single layer.
        return [DrawItem(_SPHERE, scale_matrix(2.0 * self.radius), self.effective_colour(),
                         lit=self.shaded, cull=True)]
