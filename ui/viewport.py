import dearpygui.dearpygui as dpg
import math

# Interaction state
zoom_level = 1.0
pan_offset = [0.0, 0.0]

def create_viewport(parent):
    # Stage for mouse input
    with dpg.stage(tag="viewport_stage"):
        dpg.add_mouse_wheel_handler(callback=on_scroll, parent="viewport_stage")
        dpg.add_mouse_drag_handler(callback=on_drag, threshold=1, parent="viewport_stage")
        dpg.add_item_clicked_handler(callback=on_click, parent="viewport_stage")

    # Get parent size after layout and use it for drawlist
    def finish_setup():
        width, height = dpg.get_item_rect_size(parent)
        print(f"Creating viewport drawlist with size: {width}x{height}")
        with dpg.drawlist(parent=parent, width=width, height=height, tag="viewport_drawlist"):
            with dpg.draw_layer(
                tag="viewport_layer",
                depth_clipping=False,
                perspective_divide=True,
                cull_mode=dpg.mvCullMode_Back
            ):
                with dpg.draw_node(tag="viewport_node"):
                    pass
        draw_scene()

    dpg.set_frame_callback(1, finish_setup)


def on_click(sender, app_data, user_data):
    # Placeholder for picking logic
    pass


def on_scroll(sender, app_data, user_data):
    global zoom_level
    zoom_level *= 1.1 if app_data > 0 else 0.9
    draw_scene()


def on_drag(sender, app_data, user_data):
    global pan_offset
    _, dx, dy = app_data
    pan_offset[0] += dx
    pan_offset[1] += dy
    draw_scene()


def draw_scene():
    # Example rotations
    x_rot, y_rot, z_rot = -45, 0, 45

    w = dpg.get_item_width("viewport_drawlist")
    h = dpg.get_item_height("viewport_drawlist")

    # Perspective and view
    proj = dpg.create_perspective_matrix(fov=math.radians(90), aspect=w/h, zNear=0.1, zFar=1000)
    view = dpg.create_fps_matrix([0, 0, 100], pitch=0.0, yaw=0.0)

    # Model rotation
    model = (
        dpg.create_rotation_matrix(math.pi*x_rot/180.0, [1, 0, 0]) *
        dpg.create_rotation_matrix(math.pi*y_rot/180.0, [0, 1, 0]) *
        dpg.create_rotation_matrix(math.pi*z_rot/180.0, [0, 0, 1])
    )

    transform = proj * view * model

    dpg.set_clip_space("viewport_layer", 0, 0, w, h, -1.0, 1.0)
    dpg.apply_transform("viewport_node", transform)
    cull_mode=dpg.mvCullMode_None

    draw_grid()
    draw_axes()


def draw_grid():
    spacing = 20
    count = 20
    half = spacing * count // 2
    gray = (100, 100, 100, 255)

    for i in range(-count // 2, count // 2 + 1):
        x = i * spacing
        # Vertical line (x, y from –half to +half, z=0)
        dpg.draw_line(( x, -half, 0.0), ( x,  half, 0.0), color=gray, parent="viewport_node")
        # Horizontal line (y constant)
        dpg.draw_line((-half,  x, 0.0), ( half,  x, 0.0), color=gray, parent="viewport_node")


def draw_axes():
    origin = (0.0, 0.0, 0.0)
    length = 100.0
    # X-axis (red)
    dpg.draw_arrow(
        p1=(length, 0.0, 0.0), p2=origin,
        color=(255, 0, 0, 255), thickness=2, parent="viewport_node"
    )

    # Y-axis (green)
    dpg.draw_arrow(
        p1=(0.0, length, 0.0), p2=origin,
        color=(0, 255, 0, 255), thickness=2, parent="viewport_node"
    )

    # Z‐axis (blue)
    dpg.draw_arrow(
        p1=origin,
        p2=(0.0, 0.0, length),
        color=(0, 0, 255, 255),
        thickness=2,
        parent="viewport_node"
    )
