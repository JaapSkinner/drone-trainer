# ui/viewport.py

import dearpygui.dearpygui as dpg

# Interaction state
zoom_level = 1.0
pan_offset = [0.0, 0.0]

def create_viewport(parent):
    """
    Sets up the interactive viewport.
    """

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
    """
    Mouse wheel: zoom in/out.
    app_data > 0 → wheel up → zoom in; else → zoom out.
    """
    global zoom_level
    zoom_level *= 1.1 if app_data > 0 else 0.9
    draw_scene()


def on_drag(sender, app_data, user_data):
    """
    Mouse drag: pan view.
    app_data = (button, delta_x, delta_y); we only need dx,dy.
    """
    global pan_offset
    _, dx, dy = app_data
    pan_offset[0] += dx
    pan_offset[1] += dy
    draw_scene()


def draw_scene():
    """
    1) Clear previous contents of viewport_node.
    2) Update clip space to match drawlist size.
    3) Build model, view, and projection matrices.
    4) Combine and apply transform to viewport_node.
    5) Draw grid & axes under that node.
    """

    dpg.delete_item("viewport_node", children_only=True)

    w = dpg.get_item_width("viewport_drawlist")
    h = dpg.get_item_height("viewport_drawlist")
    dpg.set_clip_space("viewport_layer", 0, 0, w, h, -1.0, 1.0)

    import math
    model = (
        dpg.create_rotation_matrix(math.radians(45), [1, 0, 0]) *
        dpg.create_rotation_matrix(math.radians(45), [0, 1, 0])
    )
    view = dpg.create_fps_matrix([0, 0, 100], 0.0, 0.0)
    proj = dpg.create_perspective_matrix(math.radians(45), w / h, 0.1, 1000.0)

    transform = proj * view * model
    dpg.apply_transform("viewport_node", transform)

    draw_grid()
    draw_axes()


def draw_grid():
    """
    Draws a grid on z=0, lines from –200 to +200 every 20 pixels.
    """
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
    """
    Draws X, Y, Z arrows in red, green, blue:
      • X: from (0,0,0) to (100,0,0)
      • Y: from (0,0,0) to (0,100,0)  (screen Y is down → positive y goes downwards)
      • Z: from (0,0,0) to (–70,70,70)
    """
    origin = (0.0, 0.0, 0.0)
    length = 100.0

    # X‐axis (red)
    dpg.draw_arrow(
        p1=origin, p2=( length,   0.0,   0.0),
        color=(255,   0,   0, 255),
        thickness=2,
        parent="viewport_node"
    )

    # Y‐axis (green)
    dpg.draw_arrow(
        p1=origin, p2=(  0.0, length,  0.0),
        color=(  0, 255,   0, 255),
        thickness=2,
        parent="viewport_node"
    )

    # Z‐axis (blue, diagonal)
    dpg.draw_arrow(
        p1=origin,
        p2=(-length * 0.7, length * 0.7, length * 0.7),
        color=(  0,   0, 255, 255),
        thickness=2,
        parent="viewport_node"
    )
