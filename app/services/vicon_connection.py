import pyvicon_datastream as pv
from pyvicon_datastream import tools
import math
from PyQt5.QtCore import QObject, pyqtSignal,QTimer
from multiprocessing import Process, Queue, TimeoutError as MPTimeoutError
from models.structs import PositionData
class ViconConnection(QObject):
    position_updated = pyqtSignal(PositionData)  # Define the signal, emitting a tuple for position
    finished = pyqtSignal()
    
    def __init__(self, vicon_tracker_ip, object_name):
        super().__init__()  # Properly initialize QObject
        self.vicon_tracker_ip = vicon_tracker_ip
        self.object_name = object_name
        self.vicon_client = pv.PyViconDatastream()
        self.mytracker = None
        self.connected = False
        self.tracking = False
        self.timer = QTimer()
        self.timer.timeout.connect(self.get_position)

    def _attempt_connection(self, queue):
        try:
            result = self.vicon_client.connect(self.vicon_tracker_ip)
            queue.put(result)
        except Exception as e:
            queue.put(e)

    def connect(self):
        timeout = 5  # Timeout in seconds
        queue = Queue()
        process = Process(target=self._attempt_connection, args=(queue,))
        process.start()
        
        try:
            result = queue.get(timeout=timeout)
            if isinstance(result, Exception):
                raise result
        except MPTimeoutError:
            print(f"Connection to {self.vicon_tracker_ip} timed out")
            process.terminate()  # Forcefully terminate the process
            process.join()  # Ensure the process has finished
            self.connected = False
            return False
        except Exception as e:
            print(f"Unexpected error: {e}")
            process.terminate()  # Ensure the process is terminated
            process.join()  # Ensure the process has finished
            self.connected = False
            return False
        
        process.join()  # Ensure the process has finished

        if result != pv.Result.Success:
            print(f"Connection to {self.vicon_tracker_ip} failed")
            self.connected = False
            return False
        else:
            print(f"Connection to {self.vicon_tracker_ip} successful")
            self.mytracker = tools.ObjectTracker(self.vicon_tracker_ip)
            self.connected = True
            return True
            
    def start_tracking(self):
        if not self.connected:
            print("Not connected to the Vicon Tracker. Please connect first.")
            return False
        self.tracking = True
        self.timer.start(10)  # Start the timer with 10ms intervals
        return True

    def stop_tracking(self):
        self.tracking = False
        self.timer.stop()

    def get_position(self):
        if self.connected and self.tracking:
            position = self.mytracker.get_position(self.object_name)
            if position and len(position[2]) > 0:
                obj_data = position[2][0]
                obj_name = obj_data[0]
                x, z, y = obj_data[2], obj_data[3], obj_data[4]
                x_rot, z_rot, y_rot  = math.degrees(obj_data[5]), math.degrees(obj_data[6]), math.degrees(obj_data[7])
                pos_data = PositionData(obj_name, x/1000, y/1000, z/1000, x_rot, y_rot, z_rot)
                self.position_updated.emit(pos_data)
        else:
            print("not tracking or connected")