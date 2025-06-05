import dearpygui.dearpygui as dpg

def create_base_panel(parent, tag, width=300):
    with dpg.child_window(parent=parent, tag=tag, border=False, width=width, autosize_y=True) as panel:
        with dpg.theme() as panel_theme:
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 10, 10)
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 6, 6)
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg, (30, 30, 30, 255))
        dpg.bind_item_theme(panel, panel_theme)
    return panel


