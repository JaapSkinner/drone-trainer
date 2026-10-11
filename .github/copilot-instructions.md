# Copilot instructions

Follow `AGENTS.md` in the repository root — it covers the architecture rules (scene objects, pose and
coordinate frames, service threading) and testing expectations.

## Testing requirements for code changes

- Always run `make test` before finalizing changes.
- If you add or change behavior, add or update Python unit tests under `tests/` to cover that behavior.
- Keep tests focused and minimal, and prefer extending existing test files where possible.
- `tests/test_app_boot.py` must stay green; it boots the real main window headlessly.
