# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/), and this
project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]
### Added
- **Run a command in a launched terminal** — each window has an optional
  "Run in terminal" field (e.g. `claude`); boot appends it with the right syntax
  for the terminal (ptyxis/gnome-terminal `--`, konsole/xterm `-e`, kitty, …).

### Fixed
- **Some windows silently didn't reopen on boot.** Two causes, both fixed:
  - *Flatpak apps* (Brave, Spotify, Blender, Bambu Studio, …) were captured with
    a sandbox-internal path (`/app/...`) that doesn't exist on the host, so the
    relaunch failed. Capture now records `flatpak run <app-id>` (detected via
    `/proc` and the app's `.desktop` Exec, reusing the app picker's resolution).
  - *Single-instance apps* (Ptyxis, Cursor/VS Code, Chromium browsers) just
    re-focused their existing instance, so a second saved window never opened.
    Boot now injects the right new-window flag, and opens browser windows as a
    placeable window (`--new-window`, or `--app=<url> --class=<wm_class>` for a
    PWA/app window) instead of a tab.
- Window capture: stop splitting an exe path that contains a space (Mullvad),
  resolve relative program paths (`./blender`) via the process cwd, and skip the
  `--gapplication-service` flag that never opens a window.
- Boot no longer waits on windows whose launch failed, and ties each launched
  window back to its process so duplicate-class windows (two terminals, two
  browser windows) land on their own saved geometry.

## [1.1.0] - 2026-06-10
### Changed
- **Installable via `pipx`/PyPI.** User data now lives in a standard per-user
  directory (`~/.config/clap-to-open`, `%APPDATA%\clap-to-open`) instead of beside
  the source; an existing in-repo config/layout is migrated automatically on
  first run. Startup sounds are bundled inside the package, and the listener /
  systemd unit now use the running interpreter (`sys.executable`) so it works
  from a pipx venv. On Linux, `pipx install --system-site-packages` exposes
  PyGObject for the monitor map & app picker.

### Added
- **First-run onboarding wizard** in the control panel: welcome → live system
  check → capture your layout → turn on listening & test. Shown once, skippable.
- `clap doctor` — diagnoses the local setup (mic, GNOME extension, sound player,
  Win32 deps, monitors, listener) and says what to fix. The same checks power
  the onboarding system-check step (`GET /api/doctor`).
- Contributor docs: CONTRIBUTING, CHANGELOG, SECURITY, Code of Conduct, and
  issue/PR templates.
- README **Privacy** section (audio is processed locally, never recorded/uploaded).

## [1.0.0] - 2026-06-10
### Added
- Double-/triple-clap to relaunch a saved workspace, each window placed at its
  exact saved position/size/monitor.
- Local **web control panel** (Flask + vanilla JS) with live status, sensitivity,
  trigger, startup sound, autostart, and a global toggle hotkey.
- **Visual layout editor**: to-scale multi-monitor canvas with drag/resize, plus
  an app picker (installed apps / open windows / manual command).
- **Linux/GNOME-Wayland** backend (window-calls, Mutter, Gio, systemd, gsettings)
  and a **Windows 10/11** backend (Win32 via pywin32/psutil) behind a platform
  abstraction layer.
- One-line installers (`bootstrap.sh`, `bootstrap.ps1`); MIT license; CI matrix.

[Unreleased]: https://github.com/Forrest404/clap-to-open/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/Forrest404/clap-to-open/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/Forrest404/clap-to-open/releases/tag/v1.0.0
