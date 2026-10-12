# Drone Trainer — Completion Plan

_Analysis date: 2026-10-11. Last real activity on the repo: 2026-03-19._

This plan has two jobs: record the state the project was left in, and break the remaining work into
**work packages (WPs)** that can each be handed to an AI agent (Copilot coding agent, Claude, etc.) as a
single issue → single PR. Every WP lists its context, files, tasks, acceptance criteria and dependencies.

---

## 0. Progress — 2026-10-12

Phases 0, 1, 2, 3 and 5 are done on branch `claude/project-analysis-plan-fc019a` (not yet pushed),
plus the remaining board items #33 and #6 and a motion capture calibration tool. 165 tests, including
a headless boot of the full main window and real-pixel render checks.

| Since the first pass | Status | Commit |
|---|---|---|
| Motion capture calibration (manual / origin & direction / reference points) | Done; verified live against a deliberately mis-aligned fake Vicon | `142f3ff` |
| NatNet multicast on Linux | Fixed (SDK bound to the interface IP) | `8b3ddad` |
| WP4.1 + WP4.2 / #33 Setpoint model, rendering, ghost mode | Done; untracked objects fly to setpoints as simulated vehicles | `795e1ce` |
| Phase 6 / #6 Trainer games (gate race, hover hold), leaderboard, pilot name | Done (first version) | `8fb44cd` |
| WP4.3 Setpoints → PX4, LAND, arm/offboard | **Not started** — safety critical, needs SITL first | — |

| WP | Status | Commit |
|---|---|---|
| 0.1 Branch & PR clean-up | **Open — needs you** (GitHub access): close #41 and #42, archive the playground branch | — |
| 0.2 Thread-safe services (#40) | Done. Also fixed StatusService/InputService touching widgets from worker threads | `4beca53` |
| 0.3 Headless CI, smoke test, README, AGENTS.md | Done. Also fixed an intermittent segfault at exit | `57c59ad` |
| 0.4 Legacy paths, navigation | Done | `d84ffcb` |
| 1.1 Coordinate frames | Done; mocap → PX4 attitude bug fixed | `9a4b00f` |
| 1.2 Reactive ObjectService, scene serialisation | Done | `75c8738` |
| 2.1 MotionCaptureService (Vicon + OptiTrack) | Done; `scripts/fake_vicon.py` for lab-free testing | `e54d1d6` |
| 2.2 Motion Capture panel | Done | `7b07d69` |
| 3.1 Card-based Objects panel (#23) | Done | `4c73309` |
| 3.2 Scene save / load | Done, plus automatic restore of the last session | `9a683b5` |
| 5.1 Mesh pipeline (#26) | Done: ~12 s/frame → ~1.4 ms/frame for 10 moving quads | `0e5bfad` |
| 5.2 Drop GLUT | Done (and GLU) | `0e5bfad` |

Found and fixed along the way (not in the original list):
- Object ↔ MAVLink links never streamed mocap, and disabling MAVLink on an object didn't stop it (`c7609f8`).
- MAVLink rates saved in settings were ignored at start-up.
- Gamepad reconnect probing re-initialised SDL every 16 ms with no controller attached.
- The MAVLink panel never received the object service ("Link Object" always failed).
- MainWindow shutdown could run twice (`75e9025`).

### Human checkpoints before relying on this in the lab

1. **Vicon**: connect to the real Tracker stream. Confirm subject names match, positions read in metres
   with height on scene Y, and the Euler convention (roll/pitch/yaw signs) in `models/frames.py`. Also
   confirm occluded objects arrive as all-zero samples (`services/motion_capture/vicon_udp.py`).
2. **Which way is North?** `models/frames.py` treats Vicon +X as North (FLU → FRD). Check this against
   how PX4's heading is set up in the lab before streaming mocap to a vehicle.
3. **OptiTrack**: untested against a real Motive server (unit-tested against the SDK's data structures only).
4. **Gamepad** on the lab PC: SDL now uses its dummy video driver; check a controller still works,
   especially on Windows.
5. **Real GPU window**: run `make run` and `python scripts/bench_render.py --min-fps 60` on the lab PC.

### Next: WP4.3 (commanding real vehicles)

Setpoints now live in `services/control_service.py` (per object, plus the ghost). What's left is
streaming the setpoint of a MAVLink-linked object to PX4 (`MavlinkService.register_setpoint_source`,
converted with `models/frames.scene_pose_to_ned`), wiring LAND/ARM/OFFBOARD with confirmation, and
stopping setpoints when mocap goes stale — tested in PX4 SITL before any real flight.

Game ideas waiting on your input (Section 2): what other games, whether trainees fly real or virtual
drones, and whether obstacles should be real tracked objects.

### Phase 4 groundwork notes (from the first pass)

- `Sphere` objects, a translucent render pass (single-layer, depth-sorted) and `gl_buffers.draw_lines`
  cover the red setpoint ball, its ghost copy, the object→setpoint line, and making an object translucent
  when it overlaps its setpoint (#33).
- Setpoints still live inside `CommandPanel` as plain lists. WP4.1 moves them into a model.
  `InputService` already delivers pose deltas to the panel on the GUI thread
  (`setpoint_delta_requested`).
- Still missing (B2/B3): nothing sends Command-panel setpoints to PX4, and LAND is not connected. Use
  `MavlinkService.link_object` / the object's `mavlink_config.linked_connection_name` to find the
  vehicle, and `models/frames.scene_pose_to_ned` for the conversion.
- Remaining hardening for WP7.1: `main_window.py` is still large, with many blanket `except: pass`
  blocks. Several MavlinkService methods are still called directly from the GUI thread; they're safe
  today because they don't touch timers.

---

## 1. Where things stand

### What works (verified)

- App boots, all panels construct, services start and shut down cleanly (verified headless with
  `QT_QPA_PLATFORM=offscreen` + SDL dummy drivers).
- `make test` → 9/9 tests pass on `main`.
- 3D viewport: orbit/zoom, camera lock-to-object, grid/axes/cubes/STL quad rendering.
- Input: gamepad (pygame), WASD and arrow keys, sensitivity.
- MAVLink service (largest, most complete subsystem, ~1.8k lines): multiple connections, heartbeats,
  telemetry, discovery, connection test, MAVLink console tab, setpoint sanitisation, mocap send loop.
- Persistent storage (settings + connections JSON), import/export, rotating file logs, in-app console (F12).
- Settings panel refresh (#39) is merged.

### What's broken or missing (verified in code)

| # | Problem | Where | Severity |
|---|---------|-------|----------|
| B1 | **Bug #40 has the wrong fix in PR #41.** The `killTimer/startTimer from another thread` warning comes from `MavlinkService.update_global_settings()` calling `setInterval()` on QTimers owned by the MAVLink thread from the UI thread — not from StorageService. Reproduced: 3 warning pairs per MAVLink settings change, and the new rates don't apply. | `services/mavlink_service.py:749` | High |
| B2 | **Command panel never commands a drone.** `register_setpoint_source()` / `send_setpoint()` have no callers. Jog/Target/Home/Joystick only move the *virtual* object. | `ui/dock/panels/command_panel.py`, `services/mavlink_service.py:1073` | High (core feature) |
| B3 | **LAND button does nothing** — `land_requested` is emitted but never connected. | `command_panel.py:777` | High (safety) |
| B4 | **Mocap → PX4 orientation not converted to NED.** Position is remapped `(x, z, -y)` but the quaternion is passed through unchanged. Will feed PX4 a wrong attitude once real mocap is used. | `mavlink_service.py:1784` | High (flight safety) |
| B5 | **No working motion capture on `main`.** `services/vicon_connection.py` is fully commented out; panel is not registered; navbar "Vicon" button maps to no panel. | `services/vicon_connection.py`, `ui/dock/dock_manager.py`, `ui/navbar/navbar.py` | High (core feature) |
| B6 | **Object panel edits silently do nothing.** It writes to `self.gl_widget.objects[i].x_pos` — neither `GLWidget.objects` nor `x_pos` exist any more (objects live in `ObjectService`, pose is a 7-tuple). Bare `except: pass` hides the AttributeError. `refresh()` is a stub that returns immediately. `MainWindow.update_vicon_position` has the same legacy bug. | `ui/dock/panels/object_panel.py:332`, `ui/main_window.py:472` | Medium |
| B7 | **Mesh rendering perf (#26) root cause:** `CadMesh` caches display lists keyed by *pose*, transforms every vertex on the CPU in Python, and never frees lists. Every move compiles a new list → slow + unbounded GPU memory growth. | `models/cad_mesh.py:131` | Medium |
| B8 | `pygame.init()` initialises **all** SDL subsystems (audio/video) on a worker thread when only joystick is needed. In this WSL environment it hangs startup forever. | `services/input_service.py:149` | Medium |
| B9 | Trainer panel exists but has no navbar button; Leaderboard and Trainer are placeholder labels. | `ui/navbar/navbar.py`, `ui/dock/panels/trainer_panel.py` | — (unbuilt) |
| B10 | Hygiene: no README; `INPUT_CONTROLS.md` refers to the removed Config panel; `cflib` in requirements but unused; Home panel GitHub link points at `jski306/drone-trainer`; window title "Collaborative Control Interface"; 69 bare/blanket `except … pass` blocks (41 in `main_window.py`); `main_window.py` is a 1,000-line god object; GLUT dependency (hard to install on Windows). | various | Low |

### Branches and open PRs — triage

| Branch / PR | What it is | Recommendation |
|---|---|---|
| **PR #41** `copilot/fix-storage-service-timer-error` | Removes `storage_service.start()` to "fix" #40. | **Close.** Targets the wrong cause (see B1). Replace with WP0.2. |
| **PR #42** `copilot/refactor-motion-capture-service` (Mar 2026) | Copilot's `MotionCaptureService`, Motion Capture panel, status + settings wiring. Merge-conflicted with `main`. | **Close after salvaging the scaffold.** Its UDP parser invents a format (CSV / 6×float32) that is not the Vicon UDP object stream; OptiTrack is a stub using a pip `natnet` package; it iterates `self.glWidget.objects` (doesn't exist); writes Euler angles into quaternion slots; uses hard-coded `dock.panels[N]` indices that #39 invalidated. Keep: service/config shape, panel layout, settings fields, status wiring. |
| **`feature/13-motion-capture-service-refactor-and-optitrack-support`** (your branch, Nov 2025) | Real Vicon UDP decoder (Angus Lynch's lab interface: frame header, 24-byte subject names, 6 doubles in mm/rad, LPF + velocity) and the vendored official NatNet SDK client in `services/optitrack/`. 86 commits behind. | **Source of truth for protocol code.** Don't merge — cherry-pick the decoder + `services/optitrack/` into WP2.1. Delete afterwards. |
| `playground/jaap-dearpygui` (Jun 2025) | Early experiments; superseded by the PyQt app. Contains committed `.pyc` files. | **Tag as `archive/dearpygui-playground` and delete the branch.** |

---

## 2. Decisions only you can make

These block Phase 6 and shape Phases 3–4. Everything before that can start now.

1. **What is a "training game"?** (#6) Examples: timed gate/hoop race, hover-in-box hold, waypoint
   sequence, follow-the-ghost. Who is the trainee — a human pilot flying a real drone in the mocap
   lab, a human flying a virtual drone with a gamepad, or both?
2. **Leaderboard & profiles:** per-pilot accounts, or just name entry per run? Local JSON is fine?
3. **Obstacle course** (Connor's comment on #23): are gates/obstacles real tracked objects, virtual
   objects, or both?
4. **Target platform:** Which OS do the lab PCs run? (Decides whether we drop GLUT and how we package.)
5. **Hardware access for verification:** Who can run tests against the real Vicon/OptiTrack and a PX4
   (SITL or real)? AI agents cannot verify these — see "human checkpoints" below.

---

## 3. Work packages

Sizes: **S** ≈ a focused PR, **M** ≈ a solid day for an agent, **L** ≈ split further if an agent struggles.

### Phase 0 — Stabilise (do first, mostly serial)

#### WP0.1 Branch & PR clean-up — S, _you (needs GitHub access)_
- Close PR #41 with a link to WP0.2. Close PR #42 with a note that the scaffold is being salvaged in WP2.1.
- `git tag archive/dearpygui-playground origin/playground/jaap-dearpygui && git push origin archive/dearpygui-playground`, then delete the branch.
- Keep `feature/13-…` until WP2.1 merges.

#### WP0.2 Fix #40 properly: thread-safe MAVLink settings updates — S
- **Context:** B1. `ServiceBase` moves services to their own `QThread`; QTimers created in `on_start()` live there.
- **Tasks:** Make `MavlinkService.update_global_settings()` safe to call from any thread — store the
  settings, then apply timer intervals on the service thread (e.g. a private signal connected with
  `Qt.QueuedConnection`, or `QMetaObject.invokeMethod(..., Qt.QueuedConnection)`). Audit the other public
  `MavlinkService` methods that touch timers/sockets for the same pattern and fix them the same way.
- **Acceptance:** A test that starts `MavlinkService`, calls `update_global_settings()` from the main
  thread, processes events, and asserts (via `qInstallMessageHandler`) that no "Timers cannot be"
  messages were emitted **and** the timer intervals changed. Closes #40.

#### WP0.3 Dev environment, headless CI, agent instructions — S
- **Tasks:**
  - `InputService._init_controller`: replace `pygame.init()` with `pygame.joystick.init()` (plus only
    what's needed for event pumping) (B8).
  - `make test` and CI: set `QT_QPA_PLATFORM=offscreen`, `SDL_AUDIODRIVER=dummy`, `SDL_VIDEODRIVER=dummy`.
  - Add a **boot smoke test**: build `MainWindow` offscreen with `glutInit` stubbed, switch to every
    navbar tag, close, assert no exceptions and no Qt thread warnings. This catches the class of bugs
    that past AI PRs introduced (non-existent attributes, wrong panel indices).
  - Remove `cflib` from `requirements.txt`; add `requirements-dev.txt` if needed.
  - Write `README.md` (what it is, setup incl. `make init`, run, test, architecture overview) and
    extend `.github/copilot-instructions.md` (and an `AGENTS.md`/`CLAUDE.md`) with: service/thread
    model, "objects live in ObjectService", pose = `(x, y, z, qw, qx, qy, qz)` in scene Y-up metres,
    "never call service internals across threads", "run `make test`".
- **Acceptance:** CI green with the smoke test; a fresh clone can follow README to a running app.

#### WP0.4 Remove legacy `gl_widget.objects` / `x_pos` paths and dead navigation — S
- **Tasks:** Route object edits through `ObjectService` + `SceneObject.set_pose()` (B6); delete or fix
  `MainWindow.update_vicon_position`; make every navbar button map to a real panel (hide "Vicon" until
  WP2.2, add "Trainer"); fix the Home panel GitHub URL and window title; update `INPUT_CONTROLS.md`.
- **Acceptance:** Editing X/Y/Z in the Live Data panel moves the object; smoke test covers every tag.

### Phase 1 — Core model (foundation for Phases 2–4)

#### WP1.1 Coordinate frames & pose maths module — M
- **Context:** Three frames are in play and conversions are scattered/missing: Vicon (Z-up, mm, Euler
  rad), scene/OpenGL (Y-up, m, quaternion), PX4 (NED, m). B4 is a live bug.
- **Tasks:** Create `models/frames.py` with tested functions: euler↔quat, quat normalise/multiply,
  `vicon_to_scene(pos_mm, euler)`, `scene_to_ned(pose)`, `ned_to_scene(...)` (position **and**
  orientation). Replace the inline conversion in `MavlinkService._process_mocap` with it (fixes B4).
- **Acceptance:** Unit tests with known rotations (e.g. 90° yaw in Vicon → expected scene and NED
  quaternions), round-trip tests, determinant/handedness checks.

#### WP1.2 Reactive ObjectService — M
- **Tasks:** Add signals `object_added`, `object_removed`, `object_changed(obj)`; panels subscribe
  instead of polling/no-op `refresh()`. Move appearance (`colour`, opacity) and tracking
  (`tracking_id`, `tracked`, `pose_locked`) onto `SceneObject` consistently. Add
  `to_dict()/from_dict()` per object type for scene save/load. Stop emitting a status signal for
  every debug-text update every frame and the "not found" warning on first creation.
- **Acceptance:** Tests for add/remove/change signals and serialisation round-trip for each object type.

### Phase 2 — Motion capture (#13) — can run in parallel with Phases 3 and 5 after Phase 1

#### WP2.1 MotionCaptureService (Vicon + OptiTrack) — L
- **Context:** Combine the two branches: **protocol code from `feature/13`**, **service/UI/settings
  shape from PR #42**. Do *not* use PR #42's parser.
- **Tasks:**
  - New `services/motion_capture_service.py` on `ServiceBase`, receive loop on the service thread
    (non-blocking socket or a dedicated reader thread feeding a queue).
  - Vicon backend: port `ViconInterface` packet decoding from `feature/13:services/vicon_connection.py`
    (strip the debug `tracked_object['test']` appends; keep the LPF as an option).
  - **Multi-subject**: emit one pose per subject per frame, keyed by Vicon subject name; convert with
    `models/frames.py`; ObjectService applies it to objects whose `tracking_id` matches (respect
    `pose_locked`).
  - OptiTrack backend: vendored `services/optitrack/NatNetClient.py` from `feature/13` (official SDK),
    rigid-body ID/name → same pose signal. Degrade gracefully if unavailable.
  - Status: connected / receiving at N Hz / stale (>2 s) → StatusService "motion_capture" target.
    Log state transitions only.
  - Settings persisted: source, bind address, port, filter on/off/frequency.
  - `scripts/fake_vicon.py`: sends synthetic Vicon-format packets (moving subjects) so the feature can be
    developed and demoed without the lab.
- **Acceptance:** Unit tests decode hand-built Vicon packets (1 and N subjects, name padding, mm→m);
  integration test sends packets over loopback and asserts poses arrive on the main thread; with
  `fake_vicon.py` running, a tracked object moves in the viewport. Closes #13.
- **Human checkpoint:** verify against the real Vicon (and OptiTrack if available) in the lab.

#### WP2.2 Motion Capture panel — M (after WP2.1)
- Source selector, address/port/filter inputs, connect/disconnect, start/stop; **live table of
  received subjects** (name, rate, last pose) with "assign to object" / "create object from subject".
  Replace the old `vicon_panel.py`; navbar entry "Motion Capture".

### Phase 3 — Object Manager GUI (#23) — after Phase 1

#### WP3.1 Card-based object manager — L
- **Context:** Connor's sketch on #23: each object is a card; "features" are attached like Blender
  modifiers (Mocap tracked, MAVLink link, Controllable, Appearance, later: Gate/Obstacle role).
- **Tasks:** Replace `object_panel.py` with a card list driven by `ObjectService` signals; each card
  shows pose (editable, locked while tracked), colour/opacity, controllable toggle, feature list with
  "add feature" menu; create-object dialog (type: cube, mesh from file, marker, …); delete; clear all.
  Move the existing per-object MAVLink group into a "MAVLink" feature.
- **Acceptance:** Every checkbox in #23 except save/load works; tests at the ObjectService level for
  each action; smoke test still green.

#### WP3.2 Scene save / load — S (after WP3.1)
- "Save scene" / "Load scene" buttons using WP1.2 serialisation, separate from app settings.

### Phase 4 — Setpoints, ghost mode, real offboard control (#33 + B2/B3) — after Phase 1 (+2 for live test)

#### WP4.1 Setpoint model out of the panel — M
- **Context:** `setpoint` / `next_setpoint` currently live as lists inside `CommandPanel`.
- **Tasks:** Per-object setpoint state (current setpoint, ghost/next setpoint, home, hover height) in
  a `ControlService` or on the object via ObjectService. Command panel and InputService manipulate it;
  rendering and MAVLink read it.
- **Acceptance:** Command panel behaviour unchanged from the user's point of view; tests on the model.

#### WP4.2 Setpoint & ghost rendering — M
- Red sphere at setpoint; translucent copy for ghost/next setpoint; yellow/black line from a tracked
  object to its setpoint; object becomes transparent when overlapping its setpoint. Closes #33.

#### WP4.3 Wire setpoints and commands to MAVLink — M, **safety critical**
- **Tasks:** When an object is linked to a connection, register its setpoint as a setpoint source
  (scene → NED via `models/frames.py`); implement LAND (`MAV_CMD_NAV_LAND`) and add explicit
  ARM / OFFBOARD / KILL controls with confirmation; geofence on top of existing sanitisation; stop
  streaming setpoints if mocap goes stale.
- **Acceptance:** Unit tests on the produced `SET_POSITION_TARGET_LOCAL_NED` values; a documented
  PX4 SITL procedure in `docs/` showing a vehicle following jog commands and landing on LAND.
- **Human checkpoint:** SITL first, then tethered/low-altitude real flight in the lab.

### Phase 5 — Rendering performance (#26) — independent, can start any time after Phase 0

#### WP5.1 Fix mesh pipeline — M
- Compile each mesh **once** in model space (display list or VBO via numpy arrays), apply the pose
  with `glMultMatrixf` at draw time, free GL resources on removal. Add a triangle-count limiter on
  load (warn + decimate or refuse above N). Closes #26.
- **Acceptance:** Benchmark script: 10 moving quad meshes holds ≥ 60 FPS on a lab PC; display-list
  count stays constant while objects move.

#### WP5.2 Drop GLUT — S/M (only if the lab PCs are Windows, or install pain is real)
- Replace `glutSolidCube` with own geometry, `glutBitmapCharacter` debug text with a QPainter overlay
  on the GL widget; remove `glutInit` from `main.py`.

#### WP5.3 Renderer v2 (draw items + shaders) — done on `claude/rendering-engine`
- Scene objects describe themselves as `DrawItem`s (`models/render_items.py`) instead of calling GL;
  the renderer draws them with GLSL 1.20 programs (per-pixel key + fill + hemisphere light), batches
  meshes by geometry, shares one GPU copy per mesh file, frees buffers when geometry is collected, and
  draws the background gradient in a shader. 4× multisampling in the viewport. Per-mocap-sample maths
  moved off numpy (decode + calibrate 23.5 → 5.5 µs). PyOpenGL error checks off in the app.
- **Measured** (`scripts/bench_app.py`, GTX 1060 via WSL D3D12, 1280×720, tracked 14k-triangle
  quads at 100 Hz): 20 drones 4.3 → 1.9 ms/frame, 40 drones 5.2 → 2.5 ms/frame. On `main` (old
  immediate-mode meshes) moving meshes ran at ~3 FPS.
- **Next ideas:** level of detail for meshes far from the camera, instancing for many identical
  drones, ground shadows / altitude lines under drones (helps judge height), picking objects with
  the mouse.

### Phase 6 — Trainer & Leaderboard (#6) — needs Section 2 answers; after Phases 3–4

#### WP6.1 Training game framework + Trainer panel — M
- `TrainerGame` base: `setup(scene)`, `tick(dt)`, `score`, `is_finished`, declarative settings schema
  → auto-generated settings form. Registry; Trainer panel with game dropdown, settings, start/stop,
  HUD (timer/score) in the viewport.

#### WP6.2 First game — M
- Pick from Section 2 (suggested: gate race — gates are objects with a "Gate" feature from WP3.1;
  timer starts on first gate, records splits).

#### WP6.3 Leaderboard & pilot profiles — M
- Results persisted via StorageService; Leaderboard panel filterable by game; replace the hard-coded
  "Jaap" profile block in the navbar with a pilot selector.

### Phase 7 — Hardening & release

- **WP7.1 Split `MainWindow`** — move service construction/wiring into an `AppController`, settings
  persistence into a binder; replace blanket `except … pass` with logged handling. (M)
- **WP7.2 Packaging** — PyInstaller (or similar) build for the lab OS, documented release process. (M)
- **WP7.3 User docs** — operator guide for a lab session: connect mocap, link drone, run a game. (S)

---

## 4. Order of work

```
Phase 0  WP0.1 → WP0.2 ─┬─ WP0.3 ─ WP0.4
                        │
Phase 1                 └─ WP1.1 ─ WP1.2
                                     │
              ┌──────────────────────┼─────────────────────┐
Phase 2   WP2.1 → WP2.2       Phase 3 WP3.1 → WP3.2     Phase 5 WP5.1 (→ WP5.2)
              │                      │                  (can start after Phase 0)
Phase 4   WP4.1 → WP4.2 → WP4.3 ─────┤
                                     │
Phase 6                       WP6.1 → WP6.2 → WP6.3
Phase 7                       WP7.x (ongoing / at the end)
```

Parallel lanes once Phase 1 lands: **mocap (2)**, **object manager (3)**, **rendering (5)**, then
**control (4)**. Keep at most one agent per lane touching `main_window.py` at a time — it's the main
merge-conflict hotspot (PR #42 went stale exactly this way).

---

## 5. How to hand this to AI agents

Lessons from the existing Copilot PRs: agents produced plausible code against attributes that no longer
exist, invented a Vicon packet format, and fixed a symptom in the wrong service. To avoid repeats:

1. **One WP = one issue = one PR.** Paste the WP section as the issue body.
2. **Give agents the real reference code.** For WP2.1, point explicitly at
   `feature/13-…:services/vicon_connection.py` and `services/optitrack/`.
3. **Require tests + the boot smoke test** (from WP0.3) on every PR; CI must be green.
4. **Ask for a reproduction first on bug fixes** — "show the failing test before the fix" would have
   caught PR #41.
5. **Human checkpoints** (agents can't do these): real Vicon/OptiTrack (WP2.1), PX4 SITL and real
   flight (WP4.3), lab-PC performance (WP5.1), game design sign-off (Phase 6).
6. Merge Phase 0 before starting parallel lanes, and rebase lanes on `main` often.
