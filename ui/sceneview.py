import dearpygui.dearpygui as dpg
import math
from stl import mesh
import numpy as np
from ui.input_handler import add_input_handler, handler_registry_id
import os

# Interaction state
zoom_level = 1.0
pan_offset = [0.0, 0.0]
x_rot = 0.0
y_rot = 0.0
_last_pan_x = 0.0
_last_pan_y = 0.0
_last_rot_dx = 0.0
_last_rot_dy = 0.0
camera_z = 600.0

def create_sceneview(parent):
    init_input_handlers()
    def finish_setup():
        width, height = dpg.get_item_rect_size(parent)
        with dpg.drawlist(parent=parent, width=width, height=height, tag="sceneview_drawlist"):
            with dpg.draw_layer(
                tag="sceneview_layer",
                depth_clipping=True,
                perspective_divide=True,
                cull_mode=dpg.mvCullMode_Back
            ):
                with dpg.draw_node(tag="sceneview_node"):
                    draw_grid()
                    draw_axes()
                    # draw_stl(os.path.join("assets", "models", "drone.stl"), "sceneview_node")
        draw_scene()

    dpg.set_frame_callback(1, finish_setup)

def on_scroll(sender, app_data):
    if dpg.is_item_hovered("sceneview_drawlist"):
        global camera_z
        camera_z -= app_data * camera_z/10
        camera_z = max(400, min(1400, camera_z))
        print(f"Camera Z: {camera_z}")
        draw_scene()

def pan_callback(sender, app_data):
    if dpg.is_item_hovered("sceneview_drawlist"):
        global pan_offset
        _, dx, dy = app_data
        pan_offset[0] = _last_pan_x - dx * camera_z / 2500
        pan_offset[1] = _last_pan_y + dy * camera_z / 2500
        draw_scene()

def pan_capture(sender, app_data):
    global _last_pan_x, _last_pan_y
    _last_pan_x = pan_offset[0]
    _last_pan_y = pan_offset[1]

def rotate_capture(sender, app_data):
    global _last_rot_dx, _last_rot_dy
    _last_rot_dx = x_rot
    _last_rot_dy = y_rot

def rotate_callback(sender, app_data):
    if dpg.is_item_hovered("sceneview_drawlist"):
        global x_rot, y_rot
        _, dx, dy = app_data
        x_rot = max(-179, min(-1, _last_rot_dy + dy))
        y_rot = _last_rot_dx + dx
        draw_scene()

def init_input_handlers():
    add_input_handler(dpg.add_mouse_wheel_handler, callback=on_scroll)
    add_input_handler(dpg.add_mouse_drag_handler, callback=pan_callback, button=dpg.mvMouseButton_Left, threshold=1)
    add_input_handler(dpg.add_mouse_release_handler, callback=pan_capture, button=dpg.mvMouseButton_Left)
    add_input_handler(dpg.add_mouse_drag_handler, callback=rotate_callback, button=dpg.mvMouseButton_Middle)
    add_input_handler(dpg.add_mouse_release_handler, callback=rotate_capture, button=dpg.mvMouseButton_Middle)

def draw_scene():
    w = dpg.get_item_width("sceneview_drawlist")
    h = dpg.get_item_height("sceneview_drawlist")

    proj = dpg.create_perspective_matrix(fov=math.radians(90), aspect=w/h, zNear=100, zFar=2500)
    view = dpg.create_fps_matrix([pan_offset[0], pan_offset[1], camera_z], pitch=0.0, yaw=0.0)

    model = (
        dpg.create_rotation_matrix(math.pi*x_rot/180.0, [1, 0, 0]) *  # pitch
        dpg.create_rotation_matrix(math.pi*y_rot/180.0, [0, 0, 1])    # yaw (around Z)
    )

    transform = proj * view * model

    dpg.set_clip_space("sceneview_layer", 0, 0, w, h, 0.0, 1.0)
    dpg.apply_transform("sceneview_node", transform)

def draw_grid():
    spacing = 10
    count = 20
    half = spacing * count // 2
    gray = (100, 100, 100, 255)
    z_offset = -0.1  # Push grid slightly below 0 to avoid z-fighting

    for i in range(-count // 2, count // 2 + 1):
        x = i * spacing
        dpg.draw_line(( x, -half, z_offset), ( x,  half, z_offset), color=gray, parent="sceneview_node")
        dpg.draw_line((-half,  x, z_offset), ( half,  x, z_offset), color=gray, parent="sceneview_node")


def draw_axes():
    origin = (0.0, 0.0, 0.0)
    length = 100.0
    dpg.draw_arrow(p1=(length, 0.0, 0.0), p2=origin, color=(255, 0, 0, 255), thickness=2, parent="sceneview_node")
    dpg.draw_arrow(p1=(0.0, length, 0.0), p2=origin, color=(0, 255, 0, 255), thickness=2, parent="sceneview_node")
    dpg.draw_arrow(p1=origin, p2=(0.0, 0.0, length), color=(0, 0, 255, 255), thickness=2, parent="sceneview_node")

def draw_stl(filename, parent_node):
    your_mesh = mesh.Mesh.from_file(filename)
    for tri in your_mesh.vectors.astype(np.float32):
        dpg.draw_triangle(tuple(tri[0]), tuple(tri[2]), tuple(tri[1]), color=(0, 0, 0, 255),fill=[155,155,155] , parent=parent_node)