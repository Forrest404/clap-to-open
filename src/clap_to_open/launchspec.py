"""Turn a captured window into a launch command that actually reopens it.

Two failure modes made boot silently drop windows:

  * **Flatpak apps** record a sandbox-internal ``/proc`` cmdline (``/app/...``)
    that doesn't exist on the host, so relaunching threw ``FileNotFoundError``.
    The host-valid command is ``flatpak run <app-id>``.
  * **Single-instance / D-Bus-activated apps** (Ptyxis, Cursor, Chromium
    browsers) just re-focus their existing instance when relaunched, so a
    second saved window of the same app never opened. They need an explicit
    "new window" flag.

:func:`resolve_capture` runs at *save* time and records a replayable ``launch``
argv (plus ``app_id``/``desktop_id``) by reusing :mod:`clap_to_open.apps`
(``Gio.DesktopAppInfo`` — already Flatpak-aware) and ``/proc``. :func:`apply_strategy`
runs at *boot* time and turns a layout entry into the final argv, injecting the
new-window flag and folding in the terminal "run a command" feature.

Everything degrades gracefully: with no resolution, ``launch`` falls back to the
raw cmdline and behaviour matches the pre-fix code.
"""
import os
import shlex
import shutil
import urllib.parse

# How common terminals run a command passed to them. Anything not listed falls
# back to "-e" (xterm/konsole-style), which most terminals accept.
_TERMINAL_RUN = {
    "ptyxis": ["--"], "gnome-terminal": ["--"], "kgx": ["--"],
    "kitty": [], "foot": [], "wezterm": ["start", "--"],
    "konsole": ["-e"], "xterm": ["-e"], "uxterm": ["-e"], "alacritty": ["-e"],
    "tilix": ["-e"], "terminator": ["-x"], "xfce4-terminal": ["-x"],
    "wt": [], "windows-terminal": [],
}

# Apps that re-focus their existing instance instead of opening a second window;
# keyed by exe basename or flatpak app-id. The value is the flag that forces a
# new, separately-placeable window. Only flags I've confirmed are listed — a
# wrong flag would make the app error out and open nothing, which is worse than
# the single-instance behaviour we're fixing.
_NEW_WINDOW = {
    "ptyxis": ["--new-window"], "org.gnome.ptyxis": ["--new-window"],
    "gnome-terminal": ["--window"],
    "cursor": ["--new-window"],
    "code": ["--new-window"], "codium": ["--new-window"],
}

# Chromium-family browsers get URL/window handling of their own (see
# _chromium_argv) rather than a plain new-window flag.
_CHROMIUM_BASENAMES = {
    "brave", "brave-browser", "chrome", "google-chrome", "google-chrome-stable",
    "chromium", "chromium-browser", "msedge", "microsoft-edge",
    "vivaldi", "vivaldi-stable",
}
_CHROMIUM_APP_IDS = {
    "com.brave.browser", "com.google.chrome", "org.chromium.chromium",
    "com.github.eloston.ungoogled_chromium", "com.microsoft.edge",
}
# wm_classes that denote an ordinary browser window (vs. a PWA/--app window,
# whose class is app-specific like "brave-localhost__-Default").
_GENERIC_BROWSER_CLASSES = {
    "brave-browser", "google-chrome", "chromium", "chromium-browser", "chrome",
    "microsoft-edge", "vivaldi-stable",
}

_SERVICE_FLAG = "--gapplication-service"  # a service process flag — never opens a window


# --------------------------------------------------------------- capture (save)
def _flatpak_app_id(pid):
    """App-id of the Flatpak that owns ``pid`` (``[Application] name=``), or None."""
    if not pid:
        return None
    try:
        section = None
        with open(f"/proc/{pid}/root/.flatpak-info") as f:
            for raw in f:
                line = raw.strip()
                if line.startswith("[") and line.endswith("]"):
                    section = line[1:-1]
                elif section == "Application" and line.startswith("name="):
                    return line[len("name="):].strip() or None
    except OSError:
        pass
    try:  # fallback: the FLATPAK_ID env var
        with open(f"/proc/{pid}/environ", "rb") as f:
            for kv in f.read().split(b"\x00"):
                if kv.startswith(b"FLATPAK_ID="):
                    return kv[len(b"FLATPAK_ID="):].decode(errors="replace") or None
    except OSError:
        pass
    return None


def _app_id_from_exec(argv):
    """If ``argv`` is a ``flatpak run …`` line, recover the app-id (last dotted arg)."""
    if not argv or os.path.basename(argv[0]).lower() != "flatpak":
        return None
    for a in reversed(argv):
        if "." in a and not a.startswith("-") and "/" not in a:
            return a
    return None


def _desktop_for_wm_class(wm_class, prefer_native):
    """A .desktop app whose StartupWMClass matches ``wm_class``, or None.

    Only entries with a real StartupWMClass (not a guessed basename) are
    considered, to avoid mismatching on a coincidental name. When an app is
    installed both natively and as a Flatpak under the same class,
    ``prefer_native`` picks the non-Flatpak entry (used once /proc has already
    ruled out a Flatpak process).
    """
    if not wm_class:
        return None
    try:
        from . import apps
        cands = [a for a in apps.list_apps()
                 if not a.get("wm_class_guessed")
                 and (a.get("wm_class") or "").lower() == wm_class.lower()
                 and a.get("exec")]
    except Exception:
        return None
    if not cands:
        return None
    if prefer_native:
        native = [a for a in cands
                  if os.path.basename((a["exec"] or [""])[0]).lower() != "flatpak"]
        if native:
            return native[0]
    return cands[0]


def _host_runnable(argv):
    """True if ``argv`` can actually be executed from boot's working directory.

    A relative program path (``./blender``) or a Flatpak sandbox path
    (``/app/bin/...``) that doesn't exist on the host is *not* runnable and needs
    resolving to a host-valid command first.
    """
    if not argv:
        return False
    prog = argv[0]
    if os.path.basename(prog).lower() == "flatpak":
        return True                      # `flatpak run <app-id>`
    if os.path.isabs(prog):
        return os.path.exists(prog)
    if "/" in prog:
        return False                     # relative path — won't resolve at boot
    return shutil.which(prog) is not None


def _desktop_launch_for(wm_class, raw_argv):
    """Best-effort host-valid launch argv for ``wm_class`` via the .desktop db.

    Looser than :func:`_desktop_for_wm_class` (it allows a guessed wm_class and
    matches on desktop-id / exec basename too). Used only as a fallback when the
    captured command can't run on the host, so a slightly fuzzy match still beats
    an entry that opens nothing.
    """
    if not wm_class:
        return None
    try:
        from . import apps
        cands = apps.list_apps()
    except Exception:
        return None
    wc = wm_class.lower()
    base = os.path.splitext(os.path.basename((raw_argv or [""])[0] or ""))[0].lower()

    def score(a):
        ax = (a.get("wm_class") or "").lower()
        did = (a.get("desktop_id") or "").lower()
        if did.endswith(".desktop"):
            did = did[:-len(".desktop")]
        ex = os.path.splitext(os.path.basename((a.get("exec") or [""])[0] or ""))[0].lower()
        if ax == wc and not a.get("wm_class_guessed"):
            return 4                     # explicit StartupWMClass match
        if ax == wc:
            return 3
        if did == wc or did.endswith("." + wc):
            return 2                     # desktop-id (e.g. com.bambulab.BambuStudio)
        if base and (ex == base or did.split(".")[-1] == base):
            return 1                     # exe basename match
        return 0

    best = max(cands, key=score, default=None)
    if best and score(best) > 0 and best.get("exec"):
        return list(best["exec"])
    return None


def resolve_capture(win, raw_argv):
    """Extra layout fields that make ``win`` replayable: ``launch``/``app_id``/``desktop_id``.

    Resolution order: a Flatpak process (``flatpak run <app-id>``) → a matching
    .desktop Exec → a looser .desktop lookup when the raw cmdline can't run on the
    host → the raw cmdline. Only fields that differ from / add to the raw argv are
    returned, so an app that already replays verbatim adds nothing.
    """
    raw_argv = list(raw_argv or [])
    out = {}

    app_id = _flatpak_app_id(win.get("pid"))
    if app_id:
        out["app_id"] = app_id
        out["launch"] = ["flatpak", "run", app_id]
        return out

    match = _desktop_for_wm_class(win.get("wm_class"), prefer_native=True)
    if match:
        launch = list(match["exec"])
        if launch != raw_argv:
            out["launch"] = launch
        if match.get("desktop_id"):
            out["desktop_id"] = match["desktop_id"]
        fid = _app_id_from_exec(launch)
        if fid:
            out["app_id"] = fid

    # Fallback: the raw cmdline isn't runnable on the host (relative path like
    # ./blender, or a Flatpak sandbox path like /app/bin/...) and the strict
    # StartupWMClass match found nothing. A looser .desktop lookup still lets the
    # entry replay instead of being silently dropped at boot.
    if not out.get("launch") and not _host_runnable(raw_argv):
        launch = _desktop_launch_for(win.get("wm_class"), raw_argv)
        if launch:
            out["launch"] = launch
            fid = _app_id_from_exec(launch)
            if fid:
                out["app_id"] = fid
    return out


# ------------------------------------------------------------------ boot launch
_LOCALHOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


def _urls(argv):
    """Yield http(s) URLs in argv, including ones tucked into ``--flag=<url>``."""
    for a in argv or []:
        s = a.split("=", 1)[1] if a.startswith("--") and "=" in a else a
        if s.startswith("http://") or s.startswith("https://"):
            yield s


def _first_url(argv):
    for u in _urls(argv):
        return u
    return None


def is_control_panel(argv, ports):
    """True if argv opens Clap to Open's own control panel (localhost:<port>).

    Matched by the specific serve port so other localhost apps the user wants
    (a dev server, a separate dashboard) are left alone.
    """
    if not ports:
        return False
    for u in _urls(argv):
        try:
            parsed = urllib.parse.urlparse(u)
        except ValueError:
            continue
        if (parsed.hostname or "").lower() in _LOCALHOSTS and parsed.port in ports:
            return True
    return False


def _launcher_prefix(argv):
    """The bare program to launch, dropping stale positionals/flags.

    Keeps a ``flatpak run <app-id>`` prefix intact; otherwise just the program.
    """
    if argv and os.path.basename(argv[0]).lower() == "flatpak":
        fid = _app_id_from_exec(argv)
        return ["flatpak", "run", fid] if fid else argv[:2]
    return [argv[0]] if argv else []


def _chromium_argv(launch_argv, raw_argv, wm_class):
    """Open a Chromium browser as a positionable window (not a tab).

    A PWA/``--app`` window (its wm_class is app-specific, not the generic browser
    class) is reopened with ``--app=<url> --class=<wm_class>`` so it gets the same
    class placement waits on. An ordinary browser window uses ``--new-window``
    (carrying the URL when one was saved).
    """
    launcher = _launcher_prefix(launch_argv)
    url = _first_url(raw_argv) or _first_url(launch_argv)
    cls = (wm_class or "").lower()
    if url and cls and cls not in _GENERIC_BROWSER_CLASSES:
        return launcher + [f"--app={url}", f"--class={wm_class}"]
    if url:
        return launcher + ["--new-window", url]
    return launcher + ["--new-window"]


def apply_strategy(entry):
    """Final launch argv for a layout ``entry`` (prefers ``launch`` over ``argv``).

    Strips the service flag, forces a new window for single-instance apps, and
    appends the optional terminal ``run`` command. Safe on any OS — it only
    rewrites argv.
    """
    argv = [a for a in (entry.get("launch") or entry.get("argv") or [])
            if a != _SERVICE_FLAG]
    if not argv:
        return argv

    wm_class = entry.get("wm_class") or ""
    # Last-chance resolution: a layout captured before this fix (or by older
    # code) may hold a command that can't run on the host. Resolve it from the
    # wm_class's .desktop entry so the window still opens instead of erroring out.
    if not _host_runnable(argv):
        fallback = _desktop_launch_for(wm_class, argv)
        if fallback:
            argv = [a for a in fallback if a != _SERVICE_FLAG]

    app_id = (entry.get("app_id") or "").strip().lower()
    base = os.path.splitext(os.path.basename(argv[0]))[0].lower()

    if app_id in _CHROMIUM_APP_IDS or base in _CHROMIUM_BASENAMES:
        return _chromium_argv(argv, entry.get("argv") or [], wm_class)

    for key in (app_id, base):
        if key in _NEW_WINDOW:
            argv = argv + _NEW_WINDOW[key]
            break

    run = (entry.get("run") or "").strip()
    if run:
        sep = _TERMINAL_RUN.get(base, ["-e"])
        try:
            argv = argv + sep + shlex.split(run)
        except ValueError:
            argv = argv + sep + [run]
    return argv
