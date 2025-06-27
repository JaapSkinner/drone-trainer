import time
import threading
import queue
import cflib.crtp  # type: ignore
from cflib.crazyflie.swarm import CachedCfFactory  # type: ignore
from cflib.crazyflie.swarm import Swarm  # type: ignore


class CrazyflieConnection:
    def __init__(self, uris):
        self.uris = uris
        self.swarm = None
        self.setpoint_queue = queue.Queue()
        self.thread = threading.Thread(target=self.run_swarm)
        self.stop_event = threading.Event()

    def update_uris(self, uris):
        self.uris = uris

    def connect(self):
        self.thread.start()

    def run_swarm(self):
        # cflib.crtp.init_drivers()
        # factory = CachedCfFactory(rw_cache='./cache')
        # self.swarm = Swarm(self.uris, factory=factory)
        # self.swarm.parallel_safe(self.light_check)
        # self.swarm.reset_estimators()

        while not self.stop_event.is_set():
            try:
                setpoint = self.setpoint_queue.get(timeout=2)  # Wait for a setpoint
                # self.set_position(setpoint)
                print(setpoint)
            except queue.Empty:
                print("No setpoint")
                continue

    def light_check(self, scf):
        scf.cf.param.set_value('led.bitmask', 255)
        time.sleep(2)
        scf.cf.param.set_value('led.bitmask', 0)
        time.sleep(2)

    def set_position(self, setpoint):
        def _set_position(scf):
            commander = scf.cf.high_level_commander
            x, y, z = setpoint
            commander.go_to(x, y, z, 0.0, 2.0)
            time.sleep(2)

        self.swarm.parallel_safe(_set_position)

    def send_setpoint(self, setpoint):
        self.setpoint_queue.put(setpoint)

    def disconnect(self):
        self.stop_event.set()
        self.thread.join()
        if self.swarm:
            self.swarm.close_links()