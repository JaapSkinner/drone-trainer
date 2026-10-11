# Notes for AI agents (and humans) working on Drone Trainer

Read `README.md` for what the app is and `docs/ROADMAP.md` for the plan and work packages.

## Ground rules

- Run `make test` before finishing. Add or update tests under `tests/` for any behaviour you add or
  change; prefer extending existing test files.
- `tests/test_app_boot.py` builds the real `MainWindow` headlessly. If you touch wiring in
  `ui/main_window.py`, a panel, or a service, it must stay green.
- When fixing a bug, first write a test that reproduces it and show that it fails.
- Never invent wire formats. Protocol code (Vicon UDP, NatNet, MAVLink) must come from a real
  reference — see `services/motion_capture/` and the links in its module docstrings.

## Architecture rules

- **Objects live in `ObjectService`.** Never keep your own list of scene objects, and never reach for
  `gl_widget.objects` (it doesn't exist). Use `object_service.get_objects()` / `get_object(name)`.
- **Pose** is a 7-tuple `(x, y, z, qw, qx, qy, qz)` in the **scene frame**: right-handed, **Y up**,
  metres, quaternion `(w, x, y, z)`. Set it with `SceneObject.set_pose()`.
- **Frame conversions** (Vicon / OptiTrack / PX4 NED ↔ scene) go through `models/frames.py` only.
  Don't hand-roll axis swaps elsewhere.
- **Threading.** Each `ServiceBase` subclass runs on its own `QThread` after `start()`.
  - Anything that touches a service's timers, sockets or pygame must run on the service thread:
    expose a public method that calls `self.call_in_service_thread(self._do_thing, ...)`.
  - Services never touch widgets. Emit a signal and connect it to a `@pyqtSlot` on the widget; Qt
    queues it onto the GUI thread.
- Qt warnings such as `Timers cannot be stopped from another thread` are bugs, not noise.
  `tests/qt_test_utils.QtMessageCapture` can assert they don't happen.
- Don't swallow exceptions with bare `except: pass`. Log them (`logger.exception(...)`) or let them
  propagate.

## Running headless

The app and tests run without a display:

```bash
QT_QPA_PLATFORM=offscreen SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python -m unittest discover -s tests
```

`make test` sets these for you. Set `DRONE_TRAINER_DATA_DIR` to keep settings and logs out of the repo.
