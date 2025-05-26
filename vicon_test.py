import time
import numpy as np
import math
from vicon_connection_class import ViconInterface as vi
from threading import Thread
from datetime import datetime as dt
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

OBJECT_NAME = "mug"

# Initialize variables for plotting
last_values = []
max_points = 100  # Maximum number of points to display on the live plot

def plot_update(frame):
    global last_values
    if True:
        vel = vicon.getPos(OBJECT_NAME)
        if vel:
            last_value = vel[-1]  # Get the last element of the velocity list
            last_values.append(last_value)
            if len(last_values) > max_points:
                last_values.pop(0)  # Maintain a fixed number of points in the list
        line.set_ydata(last_values)
        line.set_xdata(range(len(last_values)))
        ax.relim()
        ax.autoscale_view()
    return line,

vicon = vi()
try:
    # Create the Vicon connection and start its thread
    vicon_thread = Thread(target=vicon.main_loop)
    vicon_thread.start()

    # Set up the plot
    fig, ax = plt.subplots()
    ax.set_title("Live Plot of Last Velocity Component")
    ax.set_xlabel("Time Steps")
    ax.set_ylabel("Velocity")
    line, = ax.plot([], [], lw=2)

    # Animate the plot
    ani = FuncAnimation(fig, plot_update, interval=5)
    plt.show()

except KeyboardInterrupt:
    pass
except Exception as e:
    print(e)
finally:
    vicon.end()
