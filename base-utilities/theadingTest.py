import threading
import time

def control_loop():
    while True:
        # Your Crazyflie control logic here
        print("Control loop running...")  # Print statement from the thread
        time.sleep(0.01)  # Simulate control loop running at 100Hz

# Start the control loop in a separate thread
control_thread = threading.Thread(target=control_loop)
control_thread.start()
