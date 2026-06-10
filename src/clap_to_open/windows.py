"""Shared helpers around the GNOME **window-calls** extension (over ``gdbus``).

On Wayland this extension's D-Bus interface is the only reliable way to read a
window's geometry/monitor and to move/resize it to absolute logical
coordinates. Both :mod:`clap_to_open.save` (capture) and
:mod:`clap_to_open.boot` (replay) use these helpers, so they live in one place.
"""
import json
import shlex
import subprocess
import time

_WC_ARGS = [
    "gdbus", "call", "--session", "--dest", "org.gnome.Shell",
    "--object-path", "/org/gnome/Shell/Extensions/Windows",
    "--method",
]


def wc_json(method, *args):
    """Call a window-calls method and parse the JSON blob from its output."""
    out = subprocess.run(
        _WC_ARGS + [f"org.gnome.Shell.Extensions.Windows.{method}"]
        + [str(a) for a in args],
        capture_output=True, text=True,
    ).stdout
    # gdbus wraps the payload as ('...json...',); find the outermost [] or {}.
    for open_c, close_c in (("[", "]"), ("{", "}")):
        start, end = out.find(open_c), out.rfind(close_c)
        if start != -1 and end != -1:
            try:
                return json.loads(out[start:end + 1])
            except json.JSONDecodeError:
                pass
    return None


def wc(method, *args):
    """Call a window-calls method for side effects (move/resize/maximize)."""
    subprocess.run(
        _WC_ARGS + [f"org.gnome.Shell.Extensions.Windows.{method}"]
        + [str(a) for a in args],
        capture_output=True, text=True,
    )


def win_list():
    """Return the current window list (possibly empty)."""
    return wc_json("List") or []


def cmdline(pid):
    """Recover the launch argv from ``/proc/<pid>/cmdline``, or None."""
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            raw = f.read()
    except OSError:
        return None
    argv = [a.decode(errors="replace") for a in raw.split(b"\x00") if a]
    if not argv:
        return None
    # Chromium-based apps (Brave/Cursor helper) rewrite their cmdline into a
    # single space-joined blob with no null separators. Re-split it so the saved
    # argv is actually executable instead of one path-with-spaces.
    if len(argv) == 1 and " " in argv[0]:
        try:
            argv = shlex.split(argv[0])
        except ValueError:
            pass
    return argv


def place(entry, placed, timeout=12):
    """Wait for an unplaced window matching ``entry``'s wm_class, then position it.

    ``placed`` is a shared set of window ids already assigned this run, so two
    windows of the same class get their two distinct saved geometries instead of
    both landing on the first match.
    """
    match = (entry.get("wm_class") or "").lower()
    deadline = time.time() + timeout
    while time.time() < deadline:
        for win in win_list():
            if win["id"] in placed:
                continue
            cls = (win.get("wm_class") or "").lower()
            if match and match == cls:
                wid = win["id"]
                placed.add(wid)
                if entry.get("maximized"):
                    wc("Maximize", wid)
                else:
                    wc("MoveResize", wid, entry["x"], entry["y"],
                       entry["width"], entry["height"])
                return True
        time.sleep(0.4)
    print(f"clap-to-open: window '{match}' did not appear in {timeout}s",
          flush=True)
    return False
