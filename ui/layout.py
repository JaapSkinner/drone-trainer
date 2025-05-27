from ui.nav import create_nav_panel
from ui.panels.home import create_home_panel

import dearpygui.dearpygui as dpg

def create_main_window():
    with dpg.window(label="App", tag="main_window", no_title_bar=True, no_resize=True, no_move=True,
                    no_close=True, no_collapse=True, width=1024, height=768):

        with dpg.group(horizontal=True, tag="main_group"):
            create_nav_panel()
            create_home_panel()

    # Optional: Track viewport resizing
    def resize_callback():
        width, height = dpg.get_viewport_client_width(), dpg.get_viewport_client_height()
        dpg.set_item_width("main_window", width)
        dpg.set_item_height("main_window", height)
        dpg.set_item_height("main_group", height)

    dpg.set_viewport_resize_callback(lambda s, a: resize_callback())
