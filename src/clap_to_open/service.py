"""Linux listener service via ``systemctl --user``.

The unit is generated on demand from the running interpreter (``sys.executable``)
so it works whether installed as a cloned-repo venv or via ``pipx`` — no
install-time templating needed. start/stop toggle listening, enable/disable
control start-on-login, restart re-reads config after a settings change.
"""
import os
import subprocess
import sys

from . import paths
from .paths import SERVICE_NAME

_UNIT = """[Unit]
Description=Clap to Open - clap listener
After=graphical-session.target pipewire.service
PartOf=graphical-session.target

[Service]
ExecStart={python} -m clap_to_open.listener
WorkingDirectory={workdir}
Restart=on-failure
RestartSec=3

[Install]
WantedBy=graphical-session.target
"""


def _unit_path():
    return os.path.join(os.path.expanduser("~/.config/systemd/user"), SERVICE_NAME)


def _ensure_unit():
    """Write/refresh the user unit to point at the current interpreter."""
    paths.ensure_dirs()
    path = _unit_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    content = _UNIT.format(python=sys.executable, workdir=paths.CONFIG_DIR)
    try:
        current = open(path).read()
    except OSError:
        current = None
    if current != content:
        with open(path, "w") as f:
            f.write(content)
        subprocess.run(["systemctl", "--user", "daemon-reload"],
                       capture_output=True, text=True)


def _systemctl(*args):
    return subprocess.run(["systemctl", "--user", *args, SERVICE_NAME],
                          capture_output=True, text=True)


def is_active():
    return _systemctl("is-active").stdout.strip() == "active"


def is_enabled():
    return _systemctl("is-enabled").stdout.strip() == "enabled"


def start():
    _ensure_unit()
    _systemctl("start")


def stop():
    _systemctl("stop")


def restart():
    """Restart so the listener picks up new config; no-op if stopped."""
    if is_active():
        _ensure_unit()
        _systemctl("restart")


def toggle():
    """Flip listening on/off. Returns the new active state."""
    if is_active():
        stop()
        return False
    start()
    return True


def set_autostart(on):
    if on:
        _ensure_unit()
    _systemctl("enable" if on else "disable")


def status():
    return {"listening": is_active(), "autostart": is_enabled()}
