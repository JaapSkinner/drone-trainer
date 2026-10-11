from OpenGL.GL import GL_BACK, GL_CULL_FACE, glColor4f, glCullFace, glEnable, glScalef

from models import mesh_data
from models.gl_buffers import MeshBuffer
from models.scene_object import SceneObject

_SPHERE = MeshBuffer(mesh_data.uv_sphere(), use_vbo=False)


class Sphere(SceneObject):
    """A sphere — useful as a marker, waypoint or setpoint indicator."""

    def __init__(self, pose=None, name=None, radius=0.1, colour=None, controllable=False):
        super().__init__(pose, name or "Unnamed Sphere", controllable=controllable, colour=colour)
        self.radius = float(radius)

    def bounding_radius(self) -> float:
        return self.radius

    def _draw(self):
        d = 2.0 * self.radius
        glScalef(d, d, d)
        glEnable(GL_CULL_FACE)  # closed surface; also keeps translucent spheres single-layer
        glCullFace(GL_BACK)
        glColor4f(*self.effective_colour())
        _SPHERE.draw()
