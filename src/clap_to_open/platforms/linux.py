"""Linux / GNOME backend.

Delegates to the existing, tested GNOME-specific modules (window-calls over
gdbus, Mutter DisplayConfig, Gio.DesktopAppInfo, systemd, gsettings, paplay/
ffplay). Those modules already import their OS libraries lazily, so this file
imports cleanly anywhere; it's only selected when running on Linux.
"""
import subprocess

from .. import apps as _apps
from .. import hotkey as _hotkey
from .. import monitors as _monitors
from .. import service as _service
from .. import sound as _sound
from .. import windows as _windows

DEFAULT_SOUND_FILENAME = "boot.ogg"


# --- windows: enumerate / inspect / place ---
def win_list():
    return _windows.win_list()


def window_details(win_id):
    """Normalized geometry/state: {x, y, width, height, monitor, maximized}."""
    d = _windows.wc_json("Details", win_id) or {}
    return {
        "x": d.get("x"), "y": d.get("y"),
        "width": d.get("width"), "height": d.get("height"),
        "monitor": d.get("monitor"),
        "maximized": bool(d.get("maximized_horizontally")
                          and d.get("maximized_vertically")),
    }


def window_cmdline(pid):
    return _windows.cmdline(pid)


def place(entry, placed, timeout=12):
    return _windows.place(entry, placed, timeout)


# --- monitors / apps ---
def list_monitors():
    return _monitors.list_monitors()


def list_apps():
    return _apps.list_apps()


# --- launch ---
def launch(argv):
    """Fire-and-forget launch, inheriting the session env (Wayland/DBus)."""
    return subprocess.Popen(list(argv))


def run_pre_launch(command):
    """Run the user's pre-launch command through the login shell."""
    subprocess.run(["bash", "-lc", command])


# --- sound ---
def play_file(path):
    _sound._play_file(path)


def play_url(url):
    _sound._play_url(url)


# --- listener service (systemd --user) ---
def svc_is_active():
    return _service.is_active()


def svc_is_enabled():
    return _service.is_enabled()


def svc_start():
    _service.start()


def svc_stop():
    _service.stop()


def svc_restart():
    _service.restart()


def svc_toggle():
    return _service.toggle()


def svc_set_autostart(on):
    _service.set_autostart(on)


def svc_status():
    return _service.status()


# --- hotkey (gsettings) ---
def hk_available():
    return _hotkey.available()


def hk_status():
    return _hotkey.status()


def hk_set_binding(accel):
    return _hotkey.set_binding(accel)


def hk_clear():
    return _hotkey.clear()
