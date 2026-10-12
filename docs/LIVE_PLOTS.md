# Live plots in PlotJuggler

Drone Trainer can stream what it knows — object poses, setpoints, raw motion capture subjects and
MAVLink telemetry — to [PlotJuggler](https://plotjuggler.io) (3.x or 4.x) while you fly.

## Set up

1. In PlotJuggler: **Streaming** → pick **UDP Server** (or **WebSocket Server**) → **Start**.
   - Port **9870** for UDP, **9871** for WebSocket (PlotJuggler's defaults), protocol **JSON**.
   - Tick **use field as timestamp if available** and type `timestamp` (optional but recommended:
     samples then carry the time they were taken rather than the time they arrived).
2. In Drone Trainer: **Settings → Live plots** → tick **Send live data to PlotJuggler**. Choose the
   same transport and port; the host is the PC running PlotJuggler (`127.0.0.1` for this PC).
3. Drag series from PlotJuggler's list into a plot.

The status line under the settings shows the message rate; over WebSocket it says when it's still
waiting for PlotJuggler's server (it retries every 2 s, so start them in any order).

## What you get

Series are named by path. Positions are metres, angles degrees.

| Series | Meaning |
|---|---|
| `/objects/<name>/position/{x,y,z}` | Scene frame, as in the 3-D view (Y up) |
| `/objects/<name>/ned/{x,y,z}` | The same position in PX4's NED frame |
| `/objects/<name>/attitude_deg/{roll,pitch,yaw}` | Attitude in PX4's convention (FRD in NED) |
| `/objects/<name>/tracked`, `/objects/<name>/mocap_age_s` | Tracked by mocap, age of the last sample |
| `/setpoints/<name>/position/…`, `/ned/…`, `/yaw_deg` | Commanded setpoint |
| `/setpoints/<name>/error/{x,y,z,distance}` | Setpoint minus current position |
| `/mocap/<subject>/position/…`, `/rate_hz`, `/age_s`, `/visible` | Raw (calibrated) mocap subjects |
| `/mavlink/<connection>/attitude_deg/…`, `/rates_dps/…` | Vehicle attitude and rates (ATTITUDE) |
| `/mavlink/<connection>/ned/…`, `/velocity_ned/…` | Vehicle's own position estimate (LOCAL_POSITION_NED) |
| `/mavlink/<connection>/battery_v`, `/battery_pct`, `/armed` | SYS_STATUS / HEARTBEAT |

Comparing `/objects/quad1/ned/x` with `/mavlink/quad1/ned/x` shows how well PX4's estimate follows
motion capture.

## Without PlotJuggler

```bash
python scripts/fake_plotjuggler.py
```

listens like PlotJuggler's UDP (9870) and WebSocket (9871) servers and prints the message rate and
the series PlotJuggler would create.

The message format is documented in `models/plot_stream.py`, taken from PlotJuggler's sources
(`plotjuggler_app/nlohmann_parsers.cpp`, `plotjuggler_plugins/DataStreamUDP`,
`plotjuggler_plugins/DataStreamWebsocket`).
