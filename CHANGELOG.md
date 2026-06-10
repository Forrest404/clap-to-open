# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/), and this
project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]
### Added
- `clap doctor` — diagnoses the local setup (mic, GNOME extension, sound player,
  Win32 deps, monitors, listener) and says what to fix.
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

[Unreleased]: https://github.com/Forrest404/clap-to-open/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/Forrest404/clap-to-open/releases/tag/v1.0.0
