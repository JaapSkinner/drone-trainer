
import dearpygui.dearpygui as dpg

def create_base_panel_theme():
    with dpg.theme() as theme:
        with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 12, 12)  # inner padding of window
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 10, 8)      # spacing between widgets
                dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 6, 4)      # padding within widgets (like input boxes)
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg, (30, 30, 30, 255))
    return theme