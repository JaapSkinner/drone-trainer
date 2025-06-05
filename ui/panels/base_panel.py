import dearpygui.dearpygui as dpg
from ui.themes import create_base_panel_theme
import os

def create_base_panel(parent, tag):
    with dpg.child_window(parent=parent, tag=tag, border=False, width=300, autosize_y=True) as panel:
        # Load font (only once)
        if not dpg.does_item_exist("panel_font"):
            with dpg.font_registry():
                dpg.add_font(os.path.join("assets", "fonts", "Roboto-VariableFont_wdth,wght.ttf"), 18, tag="panel_font")
        dpg.bind_item_font(panel, "panel_font")
        base_panel_theme = create_base_panel_theme()
        dpg.bind_item_theme(panel, base_panel_theme)

    return panel