# home_panel.py
from ui.panels.base_panel import create_base_panel
import dearpygui.dearpygui as dpg

def create_settings_panel(parent):
    panel = create_base_panel(parent, tag="settings_panel")
    dpg.add_text("Settings Content", parent=panel)
    return panel
