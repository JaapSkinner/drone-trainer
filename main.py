import dearpygui.dearpygui as dpg
from ui.layout import create_main_window

dpg.create_context()
create_main_window()
dpg.create_viewport(title='My App', width=1024, height=768)
dpg.setup_dearpygui()
dpg.show_viewport()
dpg.start_dearpygui()
dpg.destroy_context()
