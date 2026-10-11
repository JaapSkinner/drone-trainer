"""Send synthetic Vicon Tracker UDP object-stream packets (no lab required).

    python scripts/fake_vicon.py                      # to 127.0.0.1:51001 at 100 Hz
    python scripts/fake_vicon.py --host 192.168.1.20 --rate 200 --subjects 3

Subjects (positions in the *lab* frame, Vicon axes: X forward, Y left, Z up, mm):
  quad1, quad2, …  fly circles around the lab origin, nose along the path
  wand             sits at (500, -500, 200), or steps along --wand-path

Practising calibration — pretend the Vicon world is rotated 30° and its origin
sits 2 m / 1 m away from the lab origin, and walk the wand from the lab origin
to a point 1.5 m along lab +X, pausing 4 s at each:

    python scripts/fake_vicon.py --frame-yaw 30 --frame-offset 2000,1000,0 \\
        --wand-path "0,0,0;1500,0,0" --wand-dwell 4

In the app use Motion Capture → Calibrate… → "Origin & direction" with the wand:
the quads' circles should end up centred on the scene origin.
"""
import argparse
import math
import os
import socket
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.motion_capture.vicon_udp import build_packet  # noqa: E402


def lab_frame(t: float, quads: int, wand_path=None, wand_dwell=4.0):
    """Subjects as (name, position_mm, (roll, pitch, yaw)) in the lab frame."""
    objects = []
    for i in range(quads):
        radius_mm = 1500.0 + 400.0 * i
        speed = 0.6 / (1 + i)              # rad/s
        a = speed * t + i * math.pi / max(1, quads)
        x, y = radius_mm * math.cos(a), radius_mm * math.sin(a)
        z = 1000.0 + 300.0 * i + 150.0 * math.sin(2 * a)
        yaw = a + math.pi / 2              # face along the direction of travel
        objects.append((f"quad{i + 1}", (x, y, z), (0.05 * math.sin(a), 0.0, yaw)))
    if wand_path:
        wand = wand_path[int(t // wand_dwell) % len(wand_path)]
    else:
        wand = (500.0, -500.0, 200.0)
    objects.append(("wand", wand, (0.0, 0.0, 0.3)))
    return objects


def to_vicon_frame(objects, yaw_deg: float, offset_mm):
    """Express lab-frame samples in a Vicon world rotated by ``yaw_deg`` about Z with its
    origin at ``offset_mm`` (lab coordinates) — i.e. an uncalibrated Vicon system."""
    if not yaw_deg and not any(offset_mm):
        return objects
    yaw = math.radians(yaw_deg)
    c, s = math.cos(yaw), math.sin(yaw)
    out = []
    for name, (x, y, z), (roll, pitch, heading) in objects:
        dx, dy, dz = x - offset_mm[0], y - offset_mm[1], z - offset_mm[2]
        # Inverse rotation about Z: lab vector → Vicon axes.
        out.append((name, (c * dx + s * dy, -s * dx + c * dy, dz), (roll, pitch, heading - yaw)))
    return out


def _triple(text):
    values = [float(v) for v in text.split(",")]
    if len(values) != 3:
        raise argparse.ArgumentTypeError("expected x,y,z")
    return tuple(values)


def _path(text):
    return [_triple(p) for p in text.split(";") if p.strip()]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=51001)
    parser.add_argument("--rate", type=float, default=100.0, help="packets per second")
    parser.add_argument("--subjects", type=int, default=2, help="number of circling quads")
    parser.add_argument("--duration", type=float, default=0.0, help="seconds to run (0 = forever)")
    parser.add_argument("--frame-yaw", type=float, default=0.0,
                        help="rotate the simulated Vicon world by this many degrees about vertical")
    parser.add_argument("--frame-offset", type=_triple, default=(0.0, 0.0, 0.0),
                        help="simulated Vicon origin in lab coordinates, mm: x,y,z")
    parser.add_argument("--wand-path", type=_path, default=None,
                        help='lab positions (mm) the wand steps between, e.g. "0,0,0;1500,0,0"')
    parser.add_argument("--wand-dwell", type=float, default=4.0, help="seconds at each wand position")
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
            objects = to_vicon_frame(lab_frame(t, args.subjects, args.wand_path, args.wand_dwell),
                                     args.frame_yaw, args.frame_offset)
            sock.sendto(build_packet(frame, objects), (args.host, args.port))
            frame += 1
            time.sleep(max(0.0, start + frame * period - time.monotonic()))
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()
    print(f"Sent {frame} packets")


if __name__ == "__main__":
    main()
