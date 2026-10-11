"""Send synthetic Vicon Tracker UDP object-stream packets (no lab required).

    python scripts/fake_vicon.py                      # to 127.0.0.1:51001 at 100 Hz
    python scripts/fake_vicon.py --host 192.168.1.20 --rate 200 --subjects 3

Subjects:
  quad1, quad2, …  fly circles at different heights, nose along the path
  wand             sits still at (0.5 m, -0.5 m, 0.2 m)

Then in the app: Motion Capture → Vicon, port 51001 → Connect, and assign a
subject to an object (or "Create object" from the subject list).
"""
import argparse
import math
import os
import socket
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.motion_capture.vicon_udp import build_packet  # noqa: E402


def make_frame(t: float, quads: int):
    objects = []
    for i in range(quads):
        radius_mm = 1500.0 + 400.0 * i
        speed = 0.6 / (1 + i)              # rad/s
        a = speed * t + i * math.pi / max(1, quads)
        x, y = radius_mm * math.cos(a), radius_mm * math.sin(a)
        z = 1000.0 + 300.0 * i + 150.0 * math.sin(2 * a)
        yaw = a + math.pi / 2              # face along the direction of travel
        objects.append((f"quad{i + 1}", (x, y, z), (0.05 * math.sin(a), 0.0, yaw)))
    objects.append(("wand", (500.0, -500.0, 200.0), (0.0, 0.0, 0.3)))
    return objects


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=51001)
    parser.add_argument("--rate", type=float, default=100.0, help="packets per second")
    parser.add_argument("--subjects", type=int, default=2, help="number of circling quads")
    parser.add_argument("--duration", type=float, default=0.0, help="seconds to run (0 = forever)")
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    period = 1.0 / args.rate
    start = time.monotonic()
    frame = 0
    print(f"Sending {args.subjects} quad(s) + wand to {args.host}:{args.port} at {args.rate:.0f} Hz (Ctrl+C to stop)")
    try:
        while True:
            t = time.monotonic() - start
            if args.duration and t > args.duration:
                break
            sock.sendto(build_packet(frame, make_frame(t, args.subjects)), (args.host, args.port))
            frame += 1
            time.sleep(max(0.0, start + frame * period - time.monotonic()))
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()
    print(f"Sent {frame} packets")


if __name__ == "__main__":
    main()
