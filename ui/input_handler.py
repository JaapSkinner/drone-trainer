import dearpygui.dearpygui as dpg

handler_registry_id = "global_input_handler"

def init_input_handlers():
    if not dpg.does_item_exist(handler_registry_id):
        with dpg.handler_registry(tag=handler_registry_id):
            pass

def add_input_handler(handler_func, *args, **kwargs):
    if not dpg.does_item_exist(handler_registry_id):
        init_input_handlers()
    kwargs["parent"] = handler_registry_id
    return handler_func(*args, **kwargs)