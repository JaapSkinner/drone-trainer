# settings_panel.py
from ui.panels.base_panel import create_base_panel
from ui.themes import create_base_panel_theme
import dearpygui.dearpygui as dpg

def create_settings_panel(parent):
    panel = create_base_panel(parent, tag="settings_panel")

    # General Settings
    dpg.add_text("General Settings", parent=panel, bullet=True)
    with dpg.group(parent=panel):
        with dpg.group(indent=10):
            dpg.add_text("Username")
            dpg.add_input_text()
            dpg.add_text("Enable Notifications")
            dpg.add_checkbox()
            dpg.add_text("Auto-Save")
            dpg.add_checkbox()
    dpg.add_separator(parent=panel)

    # Controls
    dpg.add_text("Controls", parent=panel, bullet=True)
    with dpg.group(parent=panel):
        with dpg.group(indent=10):
            dpg.add_text("Sensitivity")
            dpg.add_slider_float(default_value=0.5, max_value=1.0, min_value=0.0)
            dpg.add_text("Input Mode")
            dpg.add_combo(items=["Keyboard", "Mouse", "Controller"])
            dpg.add_text("Calibrate")
            dpg.add_button(label="Calibrate Controller")
    dpg.add_separator(parent=panel)

    # Display
    dpg.add_text("Display", parent=panel, bullet=True)
    with dpg.group(parent=panel):
        with dpg.group(indent=10):
            dpg.add_text("Theme Color")
            dpg.add_color_edit(default_value=(100, 150, 250, 255))
            dpg.add_text("Brightness")
            dpg.add_slider_int(default_value=75, max_value=100, min_value=0)
            dpg.add_text("Resolution")
            dpg.add_radio_button(items=["1080p", "1440p", "4K"])
    dpg.add_separator(parent=panel)

    # Audio
    dpg.add_text("Audio", parent=panel, bullet=True)
    with dpg.group(parent=panel):
        with dpg.group(indent=10):
            dpg.add_text("Master Volume")
            dpg.add_slider_float(default_value=0.8, max_value=1.0, min_value=0.0)
            dpg.add_text("Effects Volume")
            dpg.add_slider_float(default_value=0.7, max_value=1.0, min_value=0.0)
            dpg.add_text("Output Device")
            dpg.add_combo(items=["Default", "Speakers", "Headphones"])
    dpg.add_separator(parent=panel)

    # Advanced
    dpg.add_text("Advanced", parent=panel, bullet=True)
    with dpg.group(parent=panel):
        with dpg.group(indent=10):
            dpg.add_text("Max Threads")
            dpg.add_input_int(default_value=4)
            dpg.add_text("Enable Debug Mode")
            dpg.add_checkbox()
            dpg.add_text("Reset")
            dpg.add_button(label="Reset to Defaults")

    return panel

