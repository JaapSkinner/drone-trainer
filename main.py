import dearpygui.dearpygui as dpg
from ui.layout import create_main_window
from ui.input_handler import init_input_handlers

dpg.create_context()
init_input_handlers()  # <- here
create_main_window()
dpg.create_viewport(title='DTRG Drone Trainer', width=1024, height=800)

dpg.setup_dearpygui()
dpg.show_viewport()
dpg.start_dearpygui()
dpg.destroy_context()