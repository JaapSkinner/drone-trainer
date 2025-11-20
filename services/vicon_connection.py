## VICON INTERFACE FOR UOA MOCAP LAB
## Written by Angus Lynch (alyn649@aucklanduni.ac.nz)
##
## Configuration Notes:
##  - UDP object stream on vicon setup under local vicon system, IP must be the computer this code runs on

import socket
import time
import builtins
from struct import unpack
from enum import Enum
from datetime import datetime
import math
from random import randint
import queue
from threading import Thread
import traceback

us_start = int(time.time() * 1000 * 1000)


def micros():
    us_now = int(time.time() * 1000 * 1000)

    return int(us_now - us_start)


class ViconInterface():

    def __init__(self, udp_ip="0.0.0.0", udp_port=51001, filter_frequency=2):
        # Port and IP to bind UDP listener
        self.udp_port = udp_port
        self.udp_ip = udp_ip

        # Bind the listener
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((udp_ip, udp_port))

        # Used to time packet frequency to ensure FPS
        self.time_last_packet = 0
        self.FPS = 0

        # Array of dictionaries to store the tracked objects being recieved
        self.tracked_object = {}
        self.tracked_object['test'] = []
        self.tracked_object['error'] = []

        # Flag to end the main loop
        self.run_interface = True

        # Flag that the interface has heard from Vicon
        self.have_recv_packet = False

        self.filter_frequency = filter_frequency

    # Ends main loop on closure
    def end(self):
        self.run_interface = False
        self.sock.close()

    def lpf(self, prev_filtered, prev_value, value, dt, filter_freq):

        alpha = (2 - dt * filter_freq) / (2 + dt * filter_freq)
        beta = dt * filter_freq / (2 + dt * filter_freq)
        return alpha * prev_filtered + beta * (prev_value + value)

    def main_loop(self):
        try:
            self.tracked_object["test"].append("test")
            while self.run_interface:
                # Block until there is a packet
                self.tracked_object['test'].append("here b")
                b, addr = self.sock.recvfrom(512)
                self.tracked_object['test'].append("here a")
                self.tracked_object["test"].append(b)

                # First 5 bytes are the frame # and # of items in frame
                FrameNumber = int.from_bytes(b[0:4], byteorder='little')
                ItemsInBlock = b[4]

                byte_offset = 5

                # Loop for each item
                for i in range(0, ItemsInBlock):
                    # Read item id
                    ItemID = b[byte_offset]
                    byte_offset += 1

                    # Read item data size
                    ItemDataSize = int.from_bytes(b[byte_offset:byte_offset + 2], byteorder='little')
                    byte_offset += 2

                    # Get this data
                    ItemData = b[byte_offset:byte_offset + ItemDataSize]
                    byte_offset += ItemDataSize

                    # If this is an object item
                    if (ItemID == 0):
                        # Process it
                        name = str(ItemData[0:24], 'utf-8').strip('\x00')
                        data = unpack('d d d d d d', ItemData[24:72])
                        # data = unpack( 'd d d d d d', b[32:80] )

                        # data_string = str(data)

                        x = (data[0] / 1000)  # DEPRECATED: ned x = vicon y
                        y = (data[1] / 1000)  # DEPRECATED: ned y = vicon x
                        z = (data[2] / 1000)  # DEPRECATED: ned z = - vicon z

                        # yaw = (data[5]) # DEPRECATED: yaw inverted
                        roll = data[3]
                        pitch = data[4]  # DEPRECATED: pitch inverted

                        if name in self.tracked_object:
                            # yaw = self.tracked_object[name][5] + (((data[5] - self.tracked_object[name][5]+math.pi)%(2*math.pi))-math.pi)
                            l = 1
                            yaw_diff = data[5] - self.tracked_object[name][5]
                            if yaw_diff > math.pi:
                                yaw_diff -= 2 * math.pi
                            elif yaw_diff < -math.pi:
                                yaw_diff += 2 * math.pi
                            dt = (datetime.now() - self.tracked_object[name][-1]).total_seconds()
                            unwrapped_yaw = self.tracked_object[name][17] + yaw_diff
                            yaw = self.lpf(self.tracked_object[name][5], self.tracked_object[name][17], unwrapped_yaw,
                                           dt, self.filter_frequency)

                            x = self.lpf(self.tracked_object[name][0], self.tracked_object[name][12], x, dt,
                                         self.filter_frequency)
                            y = self.lpf(self.tracked_object[name][1], self.tracked_object[name][13], y, dt,
                                         self.filter_frequency)
                            z = self.lpf(self.tracked_object[name][2], self.tracked_object[name][14], z, dt,
                                         self.filter_frequency)

                            x_vel = (x - self.tracked_object[name][0]) / (dt)
                            y_vel = (y - self.tracked_object[name][1]) / (dt)
                            z_vel = (z - self.tracked_object[name][2]) / (dt)

                            x_vel = max(min(x_vel, 5), -5)
                            y_vel = max(min(y_vel, 5), -5)

                            roll_rate = (((roll - self.tracked_object[name][3] + math.pi) % (
                                        2 * math.pi)) - math.pi) / (dt)
                            pitch_rate = (((pitch - self.tracked_object[name][4] + math.pi) % (
                                        2 * math.pi)) - math.pi) / (dt)
                            # yaw_rate = (yaw - self.tracked_object[name][5])/dt

                            unfiltered_yaw_rate = (yaw - self.tracked_object[name][5]) / dt
                            yaw_rate = self.lpf(self.tracked_object[name][11], self.tracked_object[name][18],
                                                unfiltered_yaw_rate, dt, self.filter_frequency)
                        else:
                            l = 2
                            yaw = data[5]
                            unwrapped_yaw = data[5]
                            x_vel = 0
                            y_vel = 0
                            z_vel = 0
                            roll_rate = 0
                            pitch_rate = 0
                            yaw_rate = 0
                            unfiltered_yaw_rate = 0

                        self.have_recv_packet = True
                        # Store in public variable
                        self.tracked_object[name] = [x, y, z, roll, pitch, yaw, x_vel, y_vel, z_vel, roll_rate,
                                                     pitch_rate, yaw_rate, data[0] / 1000, data[1] / 1000,
                                                     data[2] / 1000, data[3], data[4], unwrapped_yaw,
                                                     unfiltered_yaw_rate, datetime.now()]
                        # print("p{:.3f},{:.3f},{:.3f},{:.3f},{:.3f},{:.3f}".format(ned_x, ned_y, ned_z, ned_roll, ned_pitch, ned_yaw))
        except Exception as e:
            print(traceback.format_exc())
            self.tracked_object['error'].append(traceback.format_exc())
        finally:
            self.sock.close()

    def getObjectsData(self):
        try:
            return self.tracked_object
        except Exception as e:
            # full exception trace
            print(traceback.format_exc())
            return None

    def getPos(self, name):
        try:
            return self.tracked_object[name][0:6]
        except Exception as e:
            # full exception trace
            # print(traceback.format_exc())
            return None

    def getVel(self, name):
        try:
            return self.tracked_object[name][6:12]
        except Exception as e:
            return None

    def getUF(self, name):
        try:
            return self.tracked_object[name][12:18]
        except Exception as e:
            return None