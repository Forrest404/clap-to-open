"""Shared helpers around the GNOME **window-calls** extension (over ``gdbus``).

On Wayland this extension's D-Bus interface is the only reliable way to read a
window's geometry/monitor and to move/resize it to absolute logical
coordinates. Both :mod:`clap_to_open.save` (capture) and
:mod:`clap_to_open.boot` (replay) use these helpers, so they live in one place.
"""
import json
import os
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
    # argv is executable — but ONLY if the blob isn't itself a real file, so we
    # don't shatter an exe path that legitimately contains a space (e.g.
    # "/opt/Mullvad VPN/mullvad-gui").
    if len(argv) == 1 and " " in argv[0] and not os.path.exists(argv[0]):
        try:
            argv = shlex.split(argv[0])
        except ValueError:
            pass
    # Resolve a relative program path (e.g. "./blender") against the process's
    # working directory so it can be relaunched from anywhere.
    if argv and not os.path.isabs(argv[0]) and "/" in argv[0]:
        try:
            cwd = os.readlink(f"/proc/{pid}/cwd")
            cand = os.path.normpath(os.path.join(cwd, argv[0]))
            if os.path.exists(cand):
                argv[0] = cand
        except OSError:
            pass
    return argv


def _ppid(pid):
    """Parent PID from ``/proc/<pid>/stat`` (comm may contain spaces/parens)."""
    try:
        with open(f"/proc/{pid}/stat") as f:
            data = f.read()
    except OSError:
        return None
    try:
        # Fields after the final ')' are space-separated: state, ppid, ...
        rest = data[data.rfind(")") + 2:].split()
        return int(rest[1])
    except (ValueError, IndexError):
        return None


def _pid_related(win_pid, root_pid, depth=6):
    """True if ``win_pid`` is ``root_pid`` or descends from it within ``depth``."""
    cur = win_pid
    for _ in range(depth):
        if cur == root_pid:
            return True
        cur = _ppid(cur)
        if not cur or cur <= 1:
            break
    return False


def _pick(wins, pid, want_title):
    """Choose which candidate window (same class, unplaced) belongs to this entry.

    Prefer the window spawned by ``pid`` (or a child of it), then a title match,
    then the first unplaced one — so duplicate-class windows in save order get
    their own saved geometry instead of colliding on the first match.
    """
    if not wins:
        return None
    if pid:
        for w in wins:
            wp = w.get("pid")
            try:
                if wp and _pid_related(int(wp), int(pid)):
                    return w
            except (TypeError, ValueError):
                pass
    want = (want_title or "").strip()
    if want:
        for w in wins:
            if (w.get("title") or "").strip() == want:
                return w
        low = want.lower()
        for w in wins:
            t = (w.get("title") or "").lower()
            if t and (low in t or t in low):
                return w
    return wins[0]


def _geometry_ok(wid, entry, tol=12):
    """True if window ``wid``'s current geometry matches ``entry`` within ``tol`` px."""
    d = wc_json("Details", wid) or {}
    try:
        return (abs(int(d["x"]) - int(entry["x"])) <= tol
                and abs(int(d["y"]) - int(entry["y"])) <= tol
                and abs(int(d["width"]) - int(entry["width"])) <= tol
                and abs(int(d["height"]) - int(entry["height"])) <= tol)
    except (KeyError, TypeError, ValueError):
        return False


def assert_geometry(wid, entry, tries=6, delay=0.25):
    """(Re)apply ``entry``'s saved geometry to window ``wid`` until it sticks.

    Many apps (Electron, GTK) move/resize themselves a moment after their window
    maps, overriding a single MoveResize — so we re-issue it a few times over a
    short settle window and stop once the window actually reports the saved rect.
    Returns True if the geometry was achieved (or the entry is maximized).
    """
    if entry.get("maximized"):
        wc("Maximize", wid)
        return True
    # A window that opened maximized ignores MoveResize until it's unmaximized.
    d = wc_json("Details", wid) or {}
    if d.get("maximized_horizontally") or d.get("maximized_vertically"):
        wc("Unmaximize", wid)
    for _ in range(tries):
        wc("MoveResize", wid, entry["x"], entry["y"],
           entry["width"], entry["height"])
        if _geometry_ok(wid, entry):
            return True
        time.sleep(delay)
    return _geometry_ok(wid, entry)


def place(entry, placed, timeout=12, pid=None):
    """Wait for an unplaced window matching ``entry``'s wm_class, then position it.

    ``placed`` is a shared set of window ids already assigned this run, so two
    windows of the same class get their two distinct saved geometries instead of
    both landing on the first match. ``pid`` (the launched process, when known)
    lets us tie a window back to the process that opened it. Only windows that
    actually launched are placed, so this never burns the timeout on a failure.

    Returns the matched window id (for a later re-assert pass), or None if no
    matching window appeared within ``timeout``.
    """
    match = (entry.get("wm_class") or "").lower()
    deadline = time.time() + timeout
    while time.time() < deadline:
        wins = [w for w in win_list()
                if w["id"] not in placed
                and match and (w.get("wm_class") or "").lower() == match]
        win = _pick(wins, pid, entry.get("title"))
        if win is not None:
            wid = win["id"]
            placed.add(wid)
            assert_geometry(wid, entry)
            return wid
        time.sleep(0.3)
    print(f"clap-to-open: window '{match}' did not appear in {timeout}s",
          flush=True)
    return None
