import time
import socket
import orjson
import logging
import math

class UDP_Client:
    """send data to UDP server, used for plotting with plotjuggler"""

    def __init__(self, host: str = "10.104.144.161", port: int = 5005):
        self.start_time = time.time()
        self._host = host
        self._port = port
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        self._log = logging.getLogger(self.__class__.__name__)

    def send(self, data):
        """send data to UDP server"""
        try:
            if not isinstance(data, dict):
                data = {"data": data}
            data["ts"] = round(time.time() - self.start_time, 3)
            self._sock.sendto(orjson.dumps(data), (self._host, self._port))
        except Exception as e:  # pylint: disable=broad-except
            self._log.error(f"Failed to send data: {e}")


    def close(self):
        """close socket"""
        self._sock.close()

    def __del__(self):
        self.close()

if __name__ == "__main__":
    client = UDP_Client()
    time_interval = 0.01
    num_points = 10000

    for i in range(num_points):
        t = i * time_interval
        sine_value = math.sin(4 * math.pi * 1 * t)  # Frequency: 1, Amplitude: 1
        cosine_value = math.cos(5 * math.pi * 0.5 * t)  # Frequency: 0.5, Amplitude: 1

        # test different data types
        test_data = {"int": 5,
                "float": 5.5,
                "string": "hello",
                "list": [1, 2, 3],
                "dict": {"a": 1, "b": 2},
                "sine": sine_value,
                "cosine": cosine_value
                }
        client.send(test_data)
        time.sleep(time_interval)

    client.close()



