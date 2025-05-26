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

# For knowing time since start
us_start = int(time.time() * 1000 * 1000)
    

def micros():
    us_now = int(time.time() * 1000 * 1000)

    return int(us_now - us_start)

# VICON SETUP

class ViconInterface():

    def __init__(self, udp_ip="0.0.0.0", udp_port=51001):
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

        # Flag to end the main loop
        self.run_interface = True

        # Flag that the interface has heard from Vicon
        self.have_recv_packet = False

    # Ends main loop on closure
    def end(self):
        self.run_interface = False
        self.sock.close()
        
    def main_loop(self):
        try:
            while self.run_interface:
                # Block until there is a packet
                b, addr = self.sock.recvfrom(256)

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
                    ItemDataSize = int.from_bytes(b[byte_offset:byte_offset+2], byteorder='little')
                    byte_offset += 2

                    # Get this data
                    ItemData = b[byte_offset:byte_offset+ItemDataSize]
                    byte_offset += ItemDataSize

                    # If this is an object item
                    if(ItemID == 0):
                        # Process it
                        name = str(ItemData[0:24], 'utf-8').strip('\x00')
                        data = unpack( 'd d d d d d', b[32:80] )

                        #data_string = str(data)

                        # Rotate to NED
                        ned_x = (data[1] / 1000) # ned x = vicon y
                        ned_y = (data[0] / 1000) # ned y = vicon x
                        ned_z = -(data[2] / 1000) # ned z = - vicon z

                        ned_yaw = -(data[5]) # yaw inverted
                        ned_roll = data[4]
                        ned_pitch = data[3] # pitch inverted

                        self.have_recv_packet = True

                        # Store in public variable 
                        self.tracked_object[name] = [ned_x, ned_y, ned_z, ned_roll, ned_pitch, ned_yaw]

                        #print("p{:.3f},{:.3f},{:.3f},{:.3f},{:.3f},{:.3f}".format(ned_x, ned_y, ned_z, ned_roll, ned_pitch, ned_yaw))
        except Exception as e:
            pass
        finally:
            self.sock.close()

    def getLatestNED(self, name):
        try:
            return self.tracked_object[name]
        except:
            return None

def main():


    # For seeing when vicon connects and recieves a packet
    vicon_recv_state_last = False

    # VICON name of object to track (drone)
    object_track = 'mug'

    # For when gui conneceoxts
    # gui_last_state = False
    
    try:
        vicon = ViconInterface()
        vicon_thread = Thread(target=vicon.main_loop)

        vicon_thread.start()
        
        while True:

            # if vicon state changes
            if(vicon.have_recv_packet != vicon_recv_state_last):
                vicon_recv_state_last = vicon.have_recv_packet


            curr_pos = vicon.getLatestNED(object_track)

            if(curr_pos is not None):

                print(curr_pos)
            
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(e)

    finally:
        vicon.end()
        # gui.end()

if(__name__ == '__main__'):
    main()

