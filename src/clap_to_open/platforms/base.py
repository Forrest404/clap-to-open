"""No-op platform backend for unsupported OSes (e.g. macOS, BSD).

Everything degrades gracefully: listings are empty, actions do nothing, and the
service/hotkey report themselves unavailable. This keeps the app importable and
the web UI functional (read-only) anywhere, rather than crashing on an
unsupported platform.
"""

DEFAULT_SOUND_FILENAME = "boot.ogg"


def win_list():
    return []


def window_details(win_id):
    return None


def window_cmdline(pid):
    return None


def place(entry, placed, timeout=12):
    return False


def list_monitors():
    return []


def list_apps():
    return []


def launch(argv):
    import subprocess
    return subprocess.Popen(list(argv))


def run_pre_launch(command):
    import subprocess
    subprocess.run(command, shell=True)


def play_file(path):
    pass


def play_url(url):
    pass


# --- listener service ---
def svc_is_active():
    return False


def svc_is_enabled():
    return False


def svc_start():
    pass


def svc_stop():
    pass


def svc_restart():
    pass


def svc_toggle():
    return False


def svc_set_autostart(on):
    pass


def svc_status():
    return {"listening": False, "autostart": False}


# --- hotkey ---
def hk_available():
    return False


def hk_status():
    return {"available": False, "binding": ""}


def hk_set_binding(accel):
    return {"ok": False, "error": "hotkeys not supported on this platform"}


def hk_clear():
    return {"ok": False, "error": "hotkeys not supported on this platform"}
