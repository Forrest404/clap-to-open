"""Read / serialise / validate the saved window layout for the editor.

``layout.json`` on disk is a plain list of entries
``{wm_class, title, argv, x, y, width, height, monitor, maximized}``. The web
editor wants two extra convenience fields per entry — a transient ``id`` and a
joined ``command`` string — which are added on read and stripped on write so the
on-disk schema never changes.
"""
import json
import shlex

from . import paths


def load():
    """Return the raw layout entries (list), or [] if missing/unreadable."""
    try:
        with open(paths.LAYOUT_PATH) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def to_api(entries):
    """Add ``id`` (the list index) and ``command`` (shlex-joined argv)."""
    out = []
    for i, e in enumerate(entries):
        argv = e.get("argv") or []
        item = {
            "id": str(i),
            "wm_class": e.get("wm_class") or "",
            "title": e.get("title") or "",
            "argv": argv,
            "command": shlex.join(argv) if argv else "",
            "run": e.get("run") or "",
            "x": e.get("x") or 0,
            "y": e.get("y") or 0,
            "width": e.get("width") or 0,
            "height": e.get("height") or 0,
            "monitor": e.get("monitor") or 0,
            "maximized": bool(e.get("maximized")),
        }
        # Carry the resolved replay fields so they survive an editor round-trip.
        for k in ("launch", "app_id", "desktop_id"):
            if e.get(k):
                item[k] = e[k]
        out.append(item)
    return out


def _as_int(value, name):
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be an integer (got {value!r})")


def clean(windows, monitor_count=None):
    """Validate editor windows and return clean on-disk entries.

    Rebuilds ``argv`` from ``command`` when ``argv`` is absent; drops ``id`` and
    ``command``. Raises ``ValueError`` with a human message on invalid input.
    """
    if not isinstance(windows, list):
        raise ValueError("windows must be a list")
    cleaned = []
    for n, w in enumerate(windows):
        if not isinstance(w, dict):
            raise ValueError(f"window {n} must be an object")

        # The editor's command string is authoritative when present (the user
        # may have edited it); fall back to a raw argv list otherwise.
        orig_argv = w.get("argv") if isinstance(w.get("argv"), list) else None
        cmd = (w.get("command") or "").strip()
        if cmd:
            try:
                argv = shlex.split(cmd)
            except ValueError:
                raise ValueError(f"window {n}: could not parse command")
        else:
            argv = orig_argv
        if (not isinstance(argv, list) or not argv
                or not all(isinstance(a, str) and a for a in argv)):
            raise ValueError(f"window {n}: argv/command is required")

        maximized = bool(w.get("maximized"))
        width = _as_int(w.get("width", 0), f"window {n} width")
        height = _as_int(w.get("height", 0), f"window {n} height")
        if not maximized and (width <= 0 or height <= 0):
            raise ValueError(f"window {n}: width and height must be > 0")

        monitor = _as_int(w.get("monitor", 0), f"window {n} monitor")
        if monitor_count and not (0 <= monitor < monitor_count):
            monitor = max(0, min(monitor, monitor_count - 1))

        entry = {
            "wm_class": (w.get("wm_class") or "").strip(),
            "title": w.get("title") or "",
            "argv": argv,
            "run": (w.get("run") or "").strip(),
            "x": _as_int(w.get("x", 0), f"window {n} x"),
            "y": _as_int(w.get("y", 0), f"window {n} y"),
            "width": width,
            "height": height,
            "monitor": monitor,
            "maximized": maximized,
        }
        # Keep the resolved replay fields only while argv is unchanged from
        # capture; once the user edits the command they'd be stale, so drop them
        # and let boot fall back to the edited argv.
        if orig_argv is not None and argv == orig_argv:
            for k in ("launch", "app_id", "desktop_id"):
                if w.get(k):
                    entry[k] = w[k]
        cleaned.append(entry)
    return cleaned
