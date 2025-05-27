import dearpygui.dearpygui as dpg

def create_home_panel():
    with dpg.child_window(autosize_x=True, height=-1):
        dpg.add_text("Welcome", tag="main_text")
