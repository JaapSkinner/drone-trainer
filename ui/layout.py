from ui.nav import create_nav_panel
from ui.panels.home import create_home_panel
from ui.panels.settings import create_settings_panel
from ui.panels.config import create_config_panel
from ui.panels.panel_registry import panel_tags
from ui.panels.trainer import create_trainer_panel
import dearpygui.dearpygui as dpg



def create_main_window():
    with dpg.window(label="App", tag="main_window", no_title_bar=True, no_resize=True, no_move=True,
                    no_close=True, no_collapse=True, width=1024, height=768):
        # Create a theme
        with dpg.theme() as no_padding_theme:
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 0, 0)
                dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 0, 0)
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 0, 0)
                dpg.add_theme_style(dpg.mvStyleVar_WindowBorderSize, 0)

        # Bind theme to the main window
        dpg.bind_item_theme("main_window", no_padding_theme)
   
        with dpg.group(horizontal=True, tag="main_group") as main_group:
            create_nav_panel(parent=main_group)
            
        content_group = dpg.add_group(tag="content_group", parent=main_group)

        # Create all panels (stacked)
        create_home_panel(parent=content_group)
        create_settings_panel(parent=content_group)
        create_config_panel(parent=content_group)
        create_trainer_panel(parent=content_group)

        # Initially show Home, hide others
        for tag in panel_tags.values():
            dpg.hide_item(tag)
        dpg.show_item("home_panel")

        
    def resize_callback():
        width, height = dpg.get_viewport_client_width(), dpg.get_viewport_client_height()
        dpg.set_item_width("main_window", width)
        dpg.set_item_height("main_window", height)
        # dpg.set_item_height("main_group", height)

    dpg.set_viewport_resize_callback(lambda s, a: resize_callback())

