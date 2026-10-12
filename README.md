# Drone Trainer

A PyQt5 + OpenGL ground-control and training app for motion-capture drone labs. It shows a live 3D
scene of tracked objects and drones, streams motion-capture poses to PX4 over MAVLink, and lets an
operator command vehicles with a gamepad, keyboard or setpoint tools.

Sponsored by the [Drone Technology Research Group](https://dtrg.org) (DTRG).

Project plan and status: [docs/ROADMAP.md](docs/ROADMAP.md). Input bindings:
[INPUT_CONTROLS.md](INPUT_CONTROLS.md).

## What it does today

- **3D viewport** of the lab: grid, boxes, spheres and STL/OBJ meshes, translucency, orbit/zoom,
  lock the camera onto any object. A soft shadow under each object and a line down from each drone
  show where it is over the floor and how high (Settings → Viewport). **Click** an object to select it
  (its card opens in Objects), **double-click** to fly it, **right-click** for fly / follow / show /
  drone setup. Selecting never changes which drone you're flying by itself.
- **Objects panel**: every object is a card — edit pose, size, colour and opacity, and attach
  *features*: **Motion capture** (follow a Vicon/OptiTrack subject, lock pose), **MAVLink vehicle**
  (stream the pose to a PX4 connection as mocap) and **Controllable** (drive it from the Command panel).
  Scenes are kept between sessions and can be saved/loaded as JSON.
- **Motion capture**: Vicon Tracker UDP object stream or OptiTrack Motive (NatNet), with live
  subject list, rates and status.
- **MAVLink**: multiple PX4 connections, discovery, telemetry, console, mocap streaming.
- **Command panel**: jog / target / home / gamepad & keyboard control of the selected object's
  *setpoint*, drawn as a red ball in the viewport (a dashed line joins the object to it while it
  travels). **Ghost mode** previews the next move as a translucent ball until you press *Send
  Position*. Objects not tracked by motion capture fly to their setpoint as simulated vehicles.
- **Motion capture calibration**: align the mocap origin/axes with the lab by hand or by moving an
  object around (see below).

- **Live plots**: stream object poses, setpoints, motion capture and MAVLink telemetry to PlotJuggler
  (UDP or WebSocket, JSON) — Settings → Live plots. See [docs/LIVE_PLOTS.md](docs/LIVE_PLOTS.md).

- **Look and feel**: a native Qt desktop UI with light and dark themes (Settings → Appearance), the
  Inter typeface, Lucide icons and short animations (wizard steps, panel switches, confirmations).

- **Trainer**: pick a game, set it up and play, flying either a simulated drone (Command panel /
  gamepad) or a real mocap-tracked one. *Gate race* — fly numbered gates in order for N laps against
  the clock (one click creates a sample course; any object can be a gate via the *Race gate* feature).
  *Hover hold* — hold the drone inside a target zone. A status line in the viewport shows progress.
- **Leaderboard**: best results per game, per pilot. Set your pilot name by clicking the profile block
  at the bottom of the navbar.

Still to come (see the roadmap): sending Command-panel setpoints to PX4 (and LAND).

## Requirements

- Python 3.10–3.12
- OpenGL-capable graphics driver
- Optional: a gamepad (anything SDL recognises), a Vicon or OptiTrack system, PX4 vehicles

## Setup

```bash
make init
```

This initialises the `libs/dtrg-mavlink` submodule, installs `requirements.txt` and builds the DTRG
MAVLink dialect. If you can't access the submodule, `make install` is enough — the app falls back to
the standard MAVLink dialect.

Using a virtual environment is recommended:

```bash
python -m venv .venv
```

```bash
source .venv/bin/activate
```

## Run

```bash
make run
```

## Setting up a drone

Press **Add a drone** (Home panel, Objects panel or Command panel) and follow the four steps:
model → motion capture subject → flight controller connection → review. The Command panel then
shows a live checklist (tracking / vehicle / mocap → vehicle) for the selected drone, with
**Drone setup…** to change it. Full guide: [docs/DRONE_SETUP.md](docs/DRONE_SETUP.md).

## Motion capture quick start (manual route)

1. Open **Motion Capture** in the navbar and pick the source.
   - **Vicon**: in Vicon Tracker enable the *UDP Object Stream* and send it to this PC's IP on the
     port shown (default 51001).
   - **OptiTrack**: in Motive enable NatNet streaming; enter Motive's IP and this PC's IP.
2. Press **Connect**. Subjects appear in the table with their rate and position.
3. Select a subject and **Assign to object…** (or **Create object**). That object now follows it;
   give it the *MAVLink vehicle* feature in the Objects panel to stream its pose to PX4.

4. If the mocap origin or axes don't match the lab (origin in a corner, "forward" rotated), press
   **Calibrate…**. Either type a rotation/offset, or use an object: *Origin & direction* (put it where
   the origin should be, then move it along the new +X) or *Reference points* (capture it on marks
   with known positions; reports the fit error). Changes preview live; **Apply** saves them, and the
   calibration then applies to everything — the viewport, tracked objects and mocap sent to PX4.

No lab handy? Send a synthetic Vicon stream from another terminal:

```bash
python scripts/fake_vicon.py --subjects 2
```

To practise calibrating, make the fake Vicon frame mis-aligned and walk the wand between two marks:

```bash
python scripts/fake_vicon.py --frame-yaw 30 --frame-offset 2000,1000,0 --wand-path "0,0,0;1500,0,0" --wand-dwell 4
```

## Test

```bash
make test
```

Tests run headlessly (offscreen Qt, dummy SDL drivers) and include a smoke test that boots the full
main window. CI runs the same command on every pull request.

## Project layout

| Path | What lives there |
|---|---|
| `main.py` | Entry point |
| `models/` | Scene objects (`SceneObject` and subclasses), dataclasses, coordinate frames |
| `services/` | Long-running services (input, MAVLink, motion capture, storage, status), each on its own thread |
| `ui/` | Main window, navbar, dock panels, 3D viewport (`ui/gl_widget/`), status overlay |
| `tests/` | Unit and smoke tests |
| `scripts/` | Developer tools (see below) |
| `cad_files/` | Meshes (STL/OBJ) |

### Developer scripts

| Script | Purpose |
|---|---|
| `scripts/fake_vicon.py` | Synthetic Vicon UDP stream (circling quads + a wand) |
| `scripts/fake_plotjuggler.py` | Stand-in PlotJuggler UDP/WebSocket server: prints the series it receives |
| `scripts/fake_px4.py` | Stand-in PX4: sends heartbeats, reports the motion capture it receives |
| `scripts/render_snapshot.py` | Render the scene headlessly to a PNG; `--check` runs the renderer pixel tests |
| `scripts/bench_render.py` | Frame-time benchmark with many moving meshes (renderer only) |
| `scripts/bench_app.py` | Frame rate of the whole app with N tracked meshes and live (fake) Vicon; `--profile` shows where GUI time goes |
| `scripts/build_mavlink.py` | Build the DTRG MAVLink dialect (`make mavlink`) |

## Architecture in brief

- **ObjectService** owns every scene object. Panels, the viewport, input and MAVLink all go through it.
- **Pose** is `(x, y, z, qw, qx, qy, qz)` in the scene frame: right-handed, Y up, metres. Conversions
  to and from Vicon, OptiTrack and PX4 NED live in `models/frames.py`.
- **Services** subclass `ServiceBase` and run on their own `QThread`. They talk to the UI only through
  Qt signals; cross-thread calls go through `ServiceBase.call_in_service_thread()`.
- **MotionCaptureService** publishes scene-frame poses by subject name; `ObjectService` applies them to
  objects whose `tracking_id` matches. **MavlinkService** streams linked objects' poses to PX4.
- **Rendering** (`ui/gl_widget/scene_renderer.py`) uploads geometry to the GPU once and draws each
  object with its pose matrix; meshes over 50k triangles are simplified on load.

More detail for contributors (and AI agents) is in [AGENTS.md](AGENTS.md).

## Data and logs

Settings, saved connections, the last scene (`scene.json`), saved scenes (`scenes/`), training
results (`results.json`) and logs are
written to `storage_data/` (git-ignored). Set
`DRONE_TRAINER_DATA_DIR` to use a different location. Press **F12** in the app for the live
application console.

## Credits

- Fonts: [Inter](https://rsms.me/inter/) and [JetBrains Mono](https://www.jetbrains.com/lp/mono/), both
  under the SIL Open Font License (`ui/assets/fonts/`).
- Icons: [Lucide](https://lucide.dev), ISC licence (`ui/assets/lucide/`).
