from crazyflie_connection import CrazyflieConnection
import time
import random
# Example usage:
uris = ['radio://0/80/250K', 'radio://0/81/250K']
cf_connection = CrazyflieConnection(uris)
cf_connection.connect()

while True:
    cf_connection.send_setpoint((random.uniform(-1, 1), random.uniform(-1, 1), random.uniform(-1, 1)))
    print("Sent setpoint")
    time.sleep(1)
