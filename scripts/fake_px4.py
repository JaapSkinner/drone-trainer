"""A stand-in PX4 flight controller for testing the app without hardware.

    python scripts/fake_px4.py                 # system ID 1, sends to 127.0.0.1:14550
    python scripts/fake_px4.py --sysid 2 --port 14551

It sends PX4 quadrotor heartbeats to the app (as a drone's MAVLink link does),
answers the app's heartbeats, and reports how much motion capture
(ATT_POS_MOCAP) it receives and the latest position. Use it to try the
"Add a drone" setup or a MAVLink connection end to end.

In the app the matching connection address is ``udpin:0.0.0.0:<port>``.
"""
import argparse
import math
import os
import sys
import time

os.environ.setdefault("MAVLINK20", "1")
from pymavlink import mavutil  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="127.0.0.1", help="PC running the app")
    parser.add_argument("--port", type=int, default=14550, help="UDP port the app listens on")
    parser.add_argument("--sysid", type=int, default=1, help="MAV_SYS_ID of this fake vehicle")
    parser.add_argument("--duration", type=float, default=0.0, help="seconds to run (0 = forever)")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    link = mavutil.mavlink_connection(f"udpout:{args.host}:{args.port}", source_system=args.sysid,
                                      source_component=1)
    mav = mavutil.mavlink
    start = last_heartbeat = last_report = time.monotonic()
    mocap_count, last_mocap = 0, None
    if not args.quiet:
        print(f"Fake PX4 (system {args.sysid}) sending to {args.host}:{args.port} — Ctrl+C to stop", flush=True)
    try:
        while not args.duration or time.monotonic() - start < args.duration:
            now = time.monotonic()
            if now - last_heartbeat >= 1.0:
                link.mav.heartbeat_send(mav.MAV_TYPE_QUADROTOR, mav.MAV_AUTOPILOT_PX4,
                                        mav.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, 0, mav.MAV_STATE_STANDBY)
                last_heartbeat = now
            msg = link.recv_match(blocking=True, timeout=0.05)
            if msg is not None and msg.get_type() == "ATT_POS_MOCAP":
                mocap_count += 1
                last_mocap = msg
            if now - last_report >= 2.0:
                if not args.quiet:
                    if last_mocap is not None:
                        yaw = math.degrees(math.atan2(2 * (last_mocap.q[0] * last_mocap.q[3] + last_mocap.q[1] * last_mocap.q[2]),
                                                      1 - 2 * (last_mocap.q[2] ** 2 + last_mocap.q[3] ** 2)))
                        print(f"mocap {mocap_count / (now - last_report):5.1f} Hz  NED ({last_mocap.x:+.2f}, "
                              f"{last_mocap.y:+.2f}, {last_mocap.z:+.2f}) m  yaw {yaw:+.0f}°", flush=True)
                    else:
                        print("no mocap received", flush=True)
                mocap_count, last_report = 0, now
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
