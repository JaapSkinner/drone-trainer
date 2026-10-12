"""Draws the scene with OpenGL. No Qt here, so it also runs in headless tests.

Scene objects don't touch GL: each returns :class:`~models.render_items.DrawItem` s
(geometry + model matrix + colour). The renderer draws them with two small GLSL
programs (lit meshes, lines), uploading each piece of geometry once.

Frame order: free buffers of geometry that went away → clear → background
gradient → opaque meshes (grouped by geometry so buffers are bound once) →
opaque lines → translucent items back-to-front with depth writes off.
"""
from __future__ import annotations

import ctypes
import logging
import math
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional, Sequence, Tuple

import numpy as np
from OpenGL.GL import (GL_ARRAY_BUFFER, GL_BACK, GL_BLEND, GL_COLOR_BUFFER_BIT, GL_CULL_FACE,
                       GL_DEPTH_BUFFER_BIT, GL_DEPTH_TEST, GL_FALSE, GL_FLOAT, GL_LEQUAL, GL_LINES,
                       GL_ONE_MINUS_SRC_ALPHA, GL_POLYGON_OFFSET_FILL, GL_SRC_ALPHA, GL_TRIANGLE_STRIP,
                       GL_TRIANGLES, GL_TRUE, glBindBuffer, glBlendFunc, glClear, glClearColor, glCullFace,
                       glDepthFunc, glDepthMask, glDisable, glDisableVertexAttribArray, glDrawArrays, glEnable,
                       glEnableVertexAttribArray, glLineWidth, glPolygonOffset, glUseProgram, glVertexAttrib4f,
                       glVertexAttribPointer, glViewport)

from ui.gl_widget.gpu import BufferCache, Program, ShaderError

logger = logging.getLogger(__name__)


@dataclass
class Camera:
    """Orbit camera around ``target`` (scene frame, Y up). Angles in degrees."""
    distance: float = 10.0
    angle_x: float = 30.0   # elevation
    angle_y: float = 45.0   # azimuth around +Y
    target: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    fov_y_deg: float = 45.0
    near: float = 0.05
    far: float = 200.0

    def eye(self) -> np.ndarray:
        ax, ay = math.radians(self.angle_x), math.radians(self.angle_y)
        offset = np.array([math.sin(ay) * math.cos(ax), math.sin(ax), math.cos(ay) * math.cos(ax)])
        return np.asarray(self.target, dtype=float) + self.distance * offset

    def projection_matrix(self, aspect: float) -> np.ndarray:
        f = 1.0 / math.tan(math.radians(self.fov_y_deg) / 2.0)
        n, fa = self.near, self.far
        return np.array([
            [f / aspect, 0, 0, 0],
            [0, f, 0, 0],
            [0, 0, (fa + n) / (n - fa), 2 * fa * n / (n - fa)],
            [0, 0, -1, 0],
        ], dtype=np.float32)

    def view_matrix(self) -> np.ndarray:
        eye = self.eye()
        forward = np.asarray(self.target, dtype=float) - eye
        forward /= np.linalg.norm(forward)
        up = np.array([0.0, 1.0, 0.0])
        side = np.cross(forward, up)
        if np.linalg.norm(side) < 1e-9:  # looking straight up/down
            side = np.array([1.0, 0.0, 0.0])
        side /= np.linalg.norm(side)
        true_up = np.cross(side, forward)
        m = np.identity(4, dtype=np.float32)
        m[0, :3], m[1, :3], m[2, :3] = side, true_up, -forward
        m[:3, 3] = -m[:3, :3] @ eye
        return m


# --- shaders (GLSL 1.20 / OpenGL 2.1) -------------------------------------------

POSITION, NORMAL, COLOUR = 0, 1, 1   # attribute locations (lines use 1 for colour)

MESH_VS = """
#version 120
attribute vec3 a_position;
attribute vec3 a_normal;
uniform mat4 u_view_proj;
uniform mat4 u_model;
uniform vec3 u_normal_scale;   // see DrawItem.normal_scale
varying vec3 v_normal;
varying vec3 v_world;
void main() {
    vec4 world = u_model * vec4(a_position, 1.0);
    v_world = world.xyz;
    v_normal = mat3(u_model) * (u_normal_scale * a_normal);
    gl_Position = u_view_proj * world;
}
"""

MESH_FS = """
#version 120
uniform vec4 u_colour;
uniform float u_lit;
uniform vec3 u_light_dir;   // towards the key light (world, unit length)
uniform vec3 u_fill_dir;    // towards a soft fill light from the other side
uniform vec3 u_eye;
uniform vec3 u_sky;         // hemisphere ambient: light from above…
uniform vec3 u_ground;      // …and bounced up from the floor
varying vec3 v_normal;
varying vec3 v_world;
void main() {
    if (u_lit < 0.5) {
        gl_FragColor = u_colour;
        return;
    }
    vec3 n = normalize(v_normal);
    if (!gl_FrontFacing) n = -n;    // open meshes: light their inside too
    float key = max(dot(n, u_light_dir), 0.0);
    float fill = max(dot(n, u_fill_dir), 0.0);
    vec3 h = normalize(u_light_dir + normalize(u_eye - v_world));
    float specular = key > 0.0 ? 0.14 * pow(max(dot(n, h), 0.0), 48.0) : 0.0;
    vec3 ambient = mix(u_ground, u_sky, 0.5 + 0.5 * n.y);
    gl_FragColor = vec4(u_colour.rgb * (ambient + 0.6 * key + 0.2 * fill) + vec3(specular), u_colour.a);
}
"""

LINES_VS = """
#version 120
attribute vec3 a_position;
attribute vec4 a_colour;
uniform mat4 u_view_proj;
uniform mat4 u_model;
varying vec4 v_colour;
void main() {
    v_colour = a_colour;
    gl_Position = u_view_proj * (u_model * vec4(a_position, 1.0));
}
"""

LINES_FS = """
#version 120
uniform vec4 u_colour;
varying vec4 v_colour;
void main() {
    gl_FragColor = u_colour * v_colour;
}
"""

BACKGROUND_VS = """
#version 120
attribute vec2 a_position;
varying float v_height;
void main() {
    v_height = 0.5 + 0.5 * a_position.y;
    gl_Position = vec4(a_position, 0.0, 1.0);
}
"""

BACKGROUND_FS = """
#version 120
uniform vec4 u_top;
uniform vec4 u_bottom;
varying float v_height;
void main() {
    gl_FragColor = mix(u_bottom, u_top, v_height);
}
"""

_SCREEN_QUAD = np.array([(-1, -1), (1, -1), (-1, 1), (1, 1)], dtype=np.float32)
_MESH_STRIDE = 6 * 4      # interleaved position + normal (float32)
_LINE_STRIDE = 7 * 4      # interleaved position + RGBA


def _interleave(*arrays):
    return np.ascontiguousarray(np.hstack(arrays), dtype=np.float32)


@dataclass
class SceneRenderer:
    background: Tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)
    # Optional (top RGBA, bottom RGBA) vertical gradient drawn behind the scene instead.
    background_gradient: Optional[Tuple[Sequence[float], Sequence[float]]] = None
    # Directional light, deliberately off the default view diagonal so the
    # visible faces of a box get different shades.
    light_position: Tuple[float, float, float, float] = (4.0, 10.0, 2.0, 0.0)
    fill_direction: Tuple[float, float, float] = (-0.6, 0.35, -0.7)
    sky_light: Tuple[float, float, float] = (0.50, 0.50, 0.53)
    ground_light: Tuple[float, float, float] = (0.28, 0.27, 0.26)
    last_draw_count: int = field(default=0, init=False)       # objects drawn last frame
    last_item_count: int = field(default=0, init=False)       # draw calls last frame

    def __post_init__(self):
        self.buffers = BufferCache()
        self._programs = None

    # -- setup ----------------------------------------------------------------

    def initialize(self):
        """Call once per GL context (from ``initializeGL``); compiles the shaders."""
        self.buffers.reset()   # buffers of an earlier context are gone with it
        try:
            self._programs = {
                "mesh": Program(MESH_VS, MESH_FS, {"a_position": POSITION, "a_normal": NORMAL}),
                "lines": Program(LINES_VS, LINES_FS, {"a_position": POSITION, "a_colour": COLOUR}),
                "background": Program(BACKGROUND_VS, BACKGROUND_FS, {"a_position": POSITION}),
            }
        except ShaderError:
            logger.exception("Could not compile the viewport shaders; the 3-D view will stay blank")
            self._programs = None

    def _apply_state(self):
        glEnable(GL_DEPTH_TEST)
        # LEQUAL: lines drawn later at the same depth (axes over the grid) win.
        glDepthFunc(GL_LEQUAL)
        glDepthMask(GL_TRUE)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glDisable(GL_CULL_FACE)
        glCullFace(GL_BACK)
        glDisable(GL_POLYGON_OFFSET_FILL)
        glPolygonOffset(1.0, 1.0)

    # -- frame ----------------------------------------------------------------

    def render(self, objects: Iterable, camera: Camera, width: int, height: int,
               viewport: Optional[Sequence[int]] = None, overlays: Iterable = (),
               alpha_for: Optional[Callable] = None, colour_for: Optional[Callable] = None):
        """Draw one frame.

        ``width``/``height`` set the aspect ratio. Pass ``viewport`` to also
        call glViewport (QOpenGLWidget sets the viewport itself).
        ``overlays`` are extra drawables (e.g. setpoint markers) and
        ``alpha_for(obj)`` scales each scene object's opacity for this frame and
        ``colour_for(obj)`` may return an RGBA to draw it with instead (or None).
        """
        self.buffers.flush()
        if viewport is not None:
            glViewport(*viewport)
        self._apply_state()
        glClearColor(*self.background)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        if self._programs is None:
            return
        if self.background_gradient is not None:
            self._draw_background(*self.background_gradient)

        visible = [o for o in objects if getattr(o, "rendered", True)]
        for obj in visible:
            obj.draw_alpha_scale = alpha_for(obj) if alpha_for is not None else 1.0
            obj.draw_colour_override = colour_for(obj) if colour_for is not None else None
        visible += list(overlays)
        self.last_draw_count = len(visible)

        # Opaque items in any order (meshes grouped by geometry); translucent ones per
        # object, far to near, so blending composes correctly.
        eye = camera.eye()
        opaque, translucent = [], []
        for obj in visible:
            items = obj.draw_items()
            if not items:
                continue
            solid = [i for i in items if not i.translucent]
            opaque.extend(solid)
            if len(solid) != len(items):
                distance = float(np.linalg.norm(np.asarray(obj.pose[:3], dtype=float) - eye))
                translucent.append((distance, [i for i in items if i.translucent]))
        translucent.sort(key=lambda entry: -entry[0])
        meshes = sorted((i for i in opaque if i.is_mesh), key=lambda i: id(i.geometry))
        lines = [i for i in opaque if not i.is_mesh]
        self.last_item_count = len(opaque) + sum(len(items) for _, items in translucent)

        view_proj = camera.projection_matrix(width / max(1, height)) @ camera.view_matrix()
        self._begin_frame(view_proj, eye)
        self._draw_items(meshes + lines)
        if translucent:
            glDepthMask(GL_FALSE)
            self._draw_items([i for _, items in translucent for i in items])
            glDepthMask(GL_TRUE)
        self._end_frame()

    def _begin_frame(self, view_proj, eye):
        light = np.asarray(self.light_position[:3], dtype=np.float32)
        light /= max(1e-9, float(np.linalg.norm(light)))
        mesh = self._programs["mesh"]
        mesh.use()
        mesh.set_mat4("u_view_proj", view_proj)
        mesh.set_vec3("u_light_dir", light)
        fill = np.asarray(self.fill_direction, dtype=np.float32)
        mesh.set_vec3("u_fill_dir", fill / max(1e-9, float(np.linalg.norm(fill))))
        mesh.set_vec3("u_eye", eye.astype(np.float32))
        mesh.set_vec3("u_sky", self.sky_light)
        mesh.set_vec3("u_ground", self.ground_light)
        lines = self._programs["lines"]
        lines.use()
        lines.set_mat4("u_view_proj", view_proj)
        self._state = {"program": None, "geometry": None, "cull": False, "offset": False, "lit": None,
                       "width": None, "normal_scale": None}

    def _end_frame(self):
        glBindBuffer(GL_ARRAY_BUFFER, 0)
        glDisableVertexAttribArray(POSITION)
        glDisableVertexAttribArray(NORMAL)
        glDisable(GL_CULL_FACE)
        glDisable(GL_POLYGON_OFFSET_FILL)
        glUseProgram(0)

    def _draw_items(self, items):
        state = self._state
        for item in items:
            geometry = item.geometry
            kind = "mesh" if item.is_mesh else "lines"
            if state["program"] != kind:
                self._programs[kind].use()
                state["program"], state["geometry"], state["lit"], state["normal_scale"] = kind, None, None, None
            program = self._programs[kind]
            if state["geometry"] is not geometry:
                self._bind(geometry, kind)
                state["geometry"] = geometry
            program.set_mat4("u_model", item.model)
            program.set_vec4("u_colour", item.colour)
            if kind == "mesh":
                if item.cull != state["cull"]:
                    (glEnable if item.cull else glDisable)(GL_CULL_FACE)
                    state["cull"] = item.cull
                if item.offset != state["offset"]:
                    (glEnable if item.offset else glDisable)(GL_POLYGON_OFFSET_FILL)
                    state["offset"] = item.offset
                if item.lit != state["lit"]:
                    program.set_float("u_lit", 1.0 if item.lit else 0.0)
                    state["lit"] = item.lit
                if item.lit and item.normal_scale != state["normal_scale"]:
                    program.set_vec3("u_normal_scale", item.normal_scale)
                    state["normal_scale"] = item.normal_scale
                glDrawArrays(GL_TRIANGLES, 0, geometry.vertex_count)
            else:
                if item.width != state["width"]:
                    glLineWidth(item.width)
                    state["width"] = item.width
                glDrawArrays(GL_LINES, 0, geometry.vertex_count)

    def _bind(self, geometry, kind):
        """Point the vertex attributes at ``geometry`` (its buffer, or memory if not static)."""
        glEnableVertexAttribArray(POSITION)
        if kind == "mesh":
            glEnableVertexAttribArray(NORMAL)
            if geometry.static:
                glBindBuffer(GL_ARRAY_BUFFER, self.buffers.buffer_for(
                    geometry, lambda: _interleave(geometry.positions, geometry.normals)))
                glVertexAttribPointer(POSITION, 3, GL_FLOAT, GL_FALSE, _MESH_STRIDE, ctypes.c_void_p(0))
                glVertexAttribPointer(NORMAL, 3, GL_FLOAT, GL_FALSE, _MESH_STRIDE, ctypes.c_void_p(12))
            else:
                glBindBuffer(GL_ARRAY_BUFFER, 0)
                glVertexAttribPointer(POSITION, 3, GL_FLOAT, GL_FALSE, 0, geometry.positions)
                glVertexAttribPointer(NORMAL, 3, GL_FLOAT, GL_FALSE, 0, geometry.normals)
            return
        has_colours = geometry.colours is not None
        if geometry.static:
            glBindBuffer(GL_ARRAY_BUFFER, self.buffers.buffer_for(geometry, lambda: _interleave(
                geometry.positions,
                geometry.colours if has_colours else np.ones((geometry.vertex_count, 4), np.float32))))
            glVertexAttribPointer(POSITION, 3, GL_FLOAT, GL_FALSE, _LINE_STRIDE, ctypes.c_void_p(0))
            glEnableVertexAttribArray(COLOUR)
            glVertexAttribPointer(COLOUR, 4, GL_FLOAT, GL_FALSE, _LINE_STRIDE, ctypes.c_void_p(12))
        else:
            glBindBuffer(GL_ARRAY_BUFFER, 0)
            glVertexAttribPointer(POSITION, 3, GL_FLOAT, GL_FALSE, 0, geometry.positions)
            if has_colours:
                glEnableVertexAttribArray(COLOUR)
                glVertexAttribPointer(COLOUR, 4, GL_FLOAT, GL_FALSE, 0, geometry.colours)
            else:
                glDisableVertexAttribArray(COLOUR)
                glVertexAttrib4f(COLOUR, 1.0, 1.0, 1.0, 1.0)

    def _draw_background(self, top, bottom):
        program = self._programs["background"]
        program.use()
        program.set_vec4("u_top", top)
        program.set_vec4("u_bottom", bottom)
        glDisable(GL_DEPTH_TEST)
        glDepthMask(GL_FALSE)
        glBindBuffer(GL_ARRAY_BUFFER, 0)
        glEnableVertexAttribArray(POSITION)
        glVertexAttribPointer(POSITION, 2, GL_FLOAT, GL_FALSE, 0, _SCREEN_QUAD)
        glDrawArrays(GL_TRIANGLE_STRIP, 0, 4)
        glDepthMask(GL_TRUE)
        glEnable(GL_DEPTH_TEST)
        glUseProgram(0)
