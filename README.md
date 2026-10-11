# Drone Trainer

A PyQt5 + OpenGL ground-control and training app for the DTRG motion-capture lab. It shows a live 3D
scene of tracked objects and drones, streams motion-capture poses to PX4 over MAVLink, and lets an
operator command vehicles with a gamepad, keyboard or setpoint tools.

Project plan and status: [docs/ROADMAP.md](docs/ROADMAP.md). Input bindings:
[INPUT_CONTROLS.md](INPUT_CONTROLS.md).

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
| `scripts/` | Developer tools (MAVLink dialect build, fake mocap sender, render benchmark) |
| `cad_files/` | Meshes (STL/OBJ) |

## Architecture in brief

- **ObjectService** owns every scene object. Panels, the viewport, input and MAVLink all go through it.
- **Pose** is `(x, y, z, qw, qx, qy, qz)` in the scene frame: right-handed, Y up, metres. Conversions
  to and from Vicon, OptiTrack and PX4 NED live in `models/frames.py`.
- **Services** subclass `ServiceBase` and run on their own `QThread`. They talk to the UI only through
  Qt signals; cross-thread calls go through `ServiceBase.call_in_service_thread()`.

More detail for contributors (and AI agents) is in [AGENTS.md](AGENTS.md).

## Data and logs

Settings, saved connections and logs are written to `storage_data/` (git-ignored). Set
`DRONE_TRAINER_DATA_DIR` to use a different location. Press **F12** in the app for the live
application console.
