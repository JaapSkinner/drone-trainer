import dearpygui.dearpygui as dpg
from ui.panels.panel_registry import panel_tags
import os

# def create_button_theme():
#     with dpg.theme() as theme:
#         with dpg.theme_component(dpg.mvButton):
#             dpg.add_theme_color(dpg.mvThemeCol_Button, (30, 30, 30, 255))
#             dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (50, 50, 50, 255))
#             dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (70, 70, 70, 255))
#     return theme

# button_theme = create_button_theme()

def nav_click(sender, app_data, user_data):
    for tag in panel_tags.values():
        dpg.hide_item(tag)
    dpg.show_item(panel_tags[user_data])


def create_nav_panel(parent):
    BTN_SIZE = 45  # Size of each button
    BTN_PADDING = 10  # Padding around buttons

    buttons = [
        ("home.png", "Home"),
        ("config.png", "Configuration"),
        ("trainer.png", "Trainer"),
        ("settings.png", "Settings"),
    ]
    
    # Create a vertical group within the parent container
    grp = dpg.add_group(parent=parent, tag="nav_group", horizontal=False, width=BTN_SIZE)
    print(os.getcwd())
    for filename, user_data in buttons:
        path = os.path.join("./assets/icons", filename)
        image_id = dpg.load_image(path)
        if image_id is None:
            # handle failure to load image
            raise RuntimeError(f"Failed to load image: {path}")
        with dpg.texture_registry():
            width, height, channels, data = dpg.load_image(path)
            texture_id = dpg.add_static_texture(width, height, data)
        
        btn = dpg.add_image_button(
            texture_tag=texture_id,       
            height=BTN_SIZE,
            callback=nav_click,
            user_data=user_data,
            parent=grp,
            frame_padding=BTN_PADDING,
        )
        # dpg.bind_item_theme(btn, button_theme)

