"""Manage a GNOME global keyboard shortcut that toggles the listener.

GNOME stores user shortcuts as "custom keybindings": a list of object paths in
``org.gnome.settings-daemon.plugins.media-keys custom-keybindings``, each path
carrying ``name``/``command``/``binding`` on a relocatable schema. We own one
entry (``clap-to-open``) and point it at ``clap ctl toggle``.

All gsettings work happens through the ``gsettings`` CLI so we need no GObject
bindings. On non-GNOME systems these calls simply no-op and the API reports the
feature as unavailable.
"""
import ast
import shutil
import subprocess
import sys

_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
_CUSTOM = _SCHEMA + ".custom-keybinding"
_SLUG = "clap-to-open"
_PATH = ("/org/gnome/settings-daemon/plugins/media-keys/"
         f"custom-keybindings/{_SLUG}/")
# Prefer the installed `clap` launcher; fall back to the running interpreter so
# it works under pipx, a repo venv, or anything else.
_COMMAND = (f"{shutil.which('clap')} ctl toggle" if shutil.which("clap")
            else f"{sys.executable} -m clap_to_open.cli ctl toggle")

# The legacy binding the old standalone script created; migrated away on setup.
_LEGACY_PATH = ("/org/gnome/settings-daemon/plugins/media-keys/"
                "custom-keybindings/clap-toggle/")


def available():
    return shutil.which("gsettings") is not None


def _get(schema, key, path=None):
    target = f"{schema}:{path}" if path else schema
    return subprocess.run(["gsettings", "get", target, key],
                          capture_output=True, text=True).stdout.strip()


def _set(schema, key, value, path=None):
    target = f"{schema}:{path}" if path else schema
    subprocess.run(["gsettings", "set", target, key, value],
                   capture_output=True, text=True)


def _unquote(gvalue):
    """Turn a gsettings string value like "'<Super>j'" into "<Super>j"."""
    try:
        return ast.literal_eval(gvalue)
    except (ValueError, SyntaxError):
        return gvalue.strip().strip("'")


def _list_paths():
    raw = _get(_SCHEMA, "custom-keybindings")
    if not raw or raw in ("@as []", "[]"):
        return []
    try:
        return list(ast.literal_eval(raw))
    except (ValueError, SyntaxError):
        return []


def _write_list(paths_list):
    _set(_SCHEMA, "custom-keybindings", str(paths_list) if paths_list else "[]")


def get():
    """Return the current accelerator for our toggle binding, or ""."""
    if not available() or _PATH not in _list_paths():
        return ""
    return _unquote(_get(_CUSTOM, "binding", _PATH))


def set_binding(accel):
    """Create/update our toggle shortcut to ``accel`` (e.g. ``<Super><Alt>j``)."""
    if not available():
        return {"ok": False, "error": "gsettings not available (GNOME only)"}
    if not accel:
        return clear()
    lst = _list_paths()
    # Drop the legacy standalone-script binding so it can't fight ours.
    changed = False
    if _LEGACY_PATH in lst:
        lst = [p for p in lst if p != _LEGACY_PATH]
        changed = True
    if _PATH not in lst:
        lst.append(_PATH)
        changed = True
    if changed:
        _write_list(lst)
    _set(_CUSTOM, "name", "Clap to Open: toggle listening", _PATH)
    _set(_CUSTOM, "command", _COMMAND, _PATH)
    _set(_CUSTOM, "binding", accel, _PATH)
    return {"ok": True, "binding": accel, "available": True}


def clear():
    """Remove our toggle shortcut entirely."""
    if not available():
        return {"ok": False, "error": "gsettings not available (GNOME only)"}
    lst = [p for p in _list_paths() if p != _PATH]
    _write_list(lst)
    for key in ("name", "command", "binding"):
        subprocess.run(["gsettings", "reset", f"{_CUSTOM}:{_PATH}", key],
                       capture_output=True, text=True)
    return {"ok": True, "binding": "", "available": True}


def status():
    return {"available": available(), "binding": get()}
