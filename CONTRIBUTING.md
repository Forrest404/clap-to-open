# Contributing to Clap to Open

Thanks for your interest! Contributions of all sizes are welcome — bug reports,
docs, a new platform backend, or a feature.

## Getting set up

```bash
git clone https://github.com/Forrest404/clap-to-open.git
cd clap-to-open
./scripts/install.sh          # Linux  (or: scripts\install.ps1 on Windows)
venv/bin/python tests/smoke.py
```

`clap doctor` will tell you what your machine is missing.

## Project layout

- `src/clap_to_open/` — the package.
  - `platforms/` — OS backends behind one interface (`linux.py`, `windows.py`,
    `base.py`, selected by `__init__.py`). **Adding macOS = add `macos.py` here.**
  - `listener.py` mic loop · `boot.py` replay · `save.py` capture ·
    `config.py`/`layout.py` data · `web/` Flask UI + vanilla-JS editor.
- `tests/smoke.py` — cross-platform import/validation/endpoint check (run in CI).

## Guidelines

- Keep OS-specific code inside a `platforms/` backend; everything else stays
  cross-platform. OS libraries (`gi`, `win32gui`, …) are imported **lazily**
  inside functions so every module imports on any OS (keeps CI green).
- Match the surrounding style; no new dependencies without discussion (Windows
  deps are gated with `; sys_platform == 'win32'`).
- Run `python tests/smoke.py` and add a test for pure logic where you can.
- Note in your PR which OS/desktop you tested on.

## Good first issues

Check the [`good first issue`](https://github.com/Forrest404/clap-to-open/labels/good%20first%20issue)
label. Docs, a macOS backend, more app-picker sources, and tests are all great
starting points.
