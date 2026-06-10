"""Thin wrappers over ``systemctl --user`` for the listener service.

The web UI and CLI drive the listener purely through systemd: start/stop toggle
listening, enable/disable controls start-on-login, and restart re-reads the
config after the UI changes sensitivity or clap-count.
"""
import subprocess

from .paths import SERVICE_NAME


def _systemctl(*args, check=False):
    return subprocess.run(
        ["systemctl", "--user", *args, SERVICE_NAME],
        capture_output=True, text=True, check=check,
    )


def is_active():
    return _systemctl("is-active").stdout.strip() == "active"


def is_enabled():
    return _systemctl("is-enabled").stdout.strip() == "enabled"


def start():
    _systemctl("start")


def stop():
    _systemctl("stop")


def restart():
    """Restart so the listener picks up new config; no-op restart if stopped."""
    if is_active():
        _systemctl("restart")


def toggle():
    """Flip listening on/off. Returns the new active state."""
    if is_active():
        stop()
        return False
    start()
    return True


def set_autostart(on):
    _systemctl("enable" if on else "disable")


def status():
    return {"listening": is_active(), "autostart": is_enabled()}
