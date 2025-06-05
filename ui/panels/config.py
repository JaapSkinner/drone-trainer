# home_panel.py
from ui.panels.base_panel import create_base_panel
import dearpygui.dearpygui as dpg

def create_config_panel(parent):
    panel = create_base_panel(parent, tag="config_panel")
    dpg.add_text("Config", parent=panel)
    return panel
