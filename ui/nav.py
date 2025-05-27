import dearpygui.dearpygui as dpg

def nav_click(sender, app_data, user_data):
    dpg.set_value("main_text", f"Selected: {user_data}")

def create_nav_panel():
    with dpg.child_window(width=100, height=-1, border=False):
        dpg.add_button(label="A", width=80, callback=nav_click, user_data="Home")
        dpg.add_button(label="B", width=80, callback=nav_click, user_data="Settings")
        dpg.add_button(label="C", width=80, callback=nav_click, user_data="Files")
