# Setting up a drone

The quickest way to get a drone tracked, connected and flyable is **Add a drone** — on the Home
panel, at the top of the Objects panel, or "Add a drone…" in the Command panel. It walks through
four steps:

1. **Drone** — name and model (built-in quadcopter, marker ball or your own STL/OBJ).
2. **Tracking** — pick its motion capture subject from the live list (move the drone and watch its
   position change to be sure), or choose *Not tracked* for a simulated drone. If motion capture
   isn't connected yet there's a button to connect it.
3. **Vehicle** — pick an existing MAVLink connection or make a new one (a free UDP port is
   suggested; *Find vehicles* scans for heartbeats; *Connect now* tries it on the spot), or choose
   *No* to only show/track it. Tick *Send motion capture to the vehicle* to give PX4 its position.
4. **Review** — a checklist of what's ready, plus *Fly it now* (select it in the Command panel)
   and *Follow it with the camera*.

To change a drone later, select it in the Command panel and press **Drone setup…** — the same
steps, prefilled. Everything can also still be done by hand: the object's card in the **Objects**
panel (features: Motion capture, MAVLink vehicle, Controllable, Race gate), the **Motion Capture**
panel (subjects → objects, calibration) and the **MAVLink** panel (connections).

## The readiness checklist

The Command panel shows, for the selected drone:

| Line | Green means | If not |
|---|---|---|
| Tracking | its subject is arriving (rate shown) | *waiting* — subject not received (a near-miss name is suggested); *lost* — the cameras can't see it; *not connected* — connect motion capture |
| Vehicle | its MAVLink connection has a heartbeat | *connecting / retrying* — it will connect when the vehicle appears |
| Mocap → vehicle | PX4 is getting fresh motion capture | *paused: tracking lost* — sending stops so PX4's own failsafe takes over |

## Safety behaviour

- Motion capture is only sent to a vehicle while the drone is **tracked, not pose-locked, and the
  last sample is under 0.25 s old**. A simulated or lost drone never feeds PX4 a made-up position.
  (A *simulation / SITL only* override exists on the MAVLink feature for testing.)
- Each vehicle needs its own UDP port and a **unique `MAV_SYS_ID`**; a second vehicle with the same
  ID is refused with a message rather than silently replacing the first.
- Connections that were working reconnect automatically on the next launch and are retried while
  missing (Settings → MAVLink → Auto Reconnect). Pressing **Disconnect** stops that until you connect
  again.

## Practising without the lab

```bash
python scripts/fake_vicon.py --subjects 2
```

```bash
python scripts/fake_px4.py --port 14550
```

Then *Add a drone*: name it `quad1`, connect motion capture (Vicon, port 51001) and pick `quad1`,
and use a new connection `udpin:0.0.0.0:14550`. The fake PX4 prints the motion capture it receives.

## Troubleshooting

- **No subjects** — check the Motion Capture source/port, and that Vicon Tracker / Motive streams to
  this PC's IP. For OptiTrack also check the up axis.
- **No heartbeat** — the vehicle must send MAVLink to this PC on the connection's port
  (`udpin:0.0.0.0:<port>` listens on all interfaces). Firewalls can block UDP.
- **Drone in the wrong place / rotated** — Motion Capture → *Calibrate…* aligns the mocap frame
  with the lab.
