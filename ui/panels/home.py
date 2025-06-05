# home_panel.py
from ui.panels.base_panel import create_base_panel
import dearpygui.dearpygui as dpg

def create_home_panel(parent):
    panel = create_base_panel(parent, tag="home_panel")
    dpg.add_text("Home Content", parent=panel)
    return panel
