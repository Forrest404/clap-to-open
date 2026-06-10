"""Boot sequence: replay the saved window layout (and optional startup sound).

Reads ``layout.json`` (written by :mod:`clap_to_open.save`), relaunches each
captured app and places its window back at the saved position/size/monitor via
the window-calls helpers in :mod:`clap_to_open.windows`. Sound and the odysseus
auto-start are driven by ``config.json``.

Notes / limitations:
  * Multi-window single-process apps (e.g. Ptyxis: one PID, several windows)
    replay the shared process cmdline; same-class windows are assigned saved
    spots in save order.
  * Flatpak/wrapped apps may record a cmdline that doesn't replay verbatim.
"""
import json

from . import config, launchspec, paths, platforms, sound

# How long to keep trying to place launched windows. Generous because some apps
# open slowly — e.g. a launcher that first brings up a docker stack and waits for
# a server before showing its window. The loop exits as soon as everything is
# placed, so this only bounds the wait for a window that never appears.
PLACE_TIMEOUT = 60


def main():
    try:
        with open(paths.LAYOUT_PATH) as f:
            layout = json.load(f)
    except (OSError, json.JSONDecodeError):
        print(f"clap-to-open: no layout at {paths.LAYOUT_PATH} -- capture one "
              "first with your windows arranged as you want them.", flush=True)
        return

    if not layout:
        print("clap-to-open: layout is empty -- capture one first.", flush=True)
        return

    cfg = config.load()

    # Optional user-defined pre-launch step (e.g. start a docker stack a saved
    # app depends on). Runs through the login shell so ~ and PATH resolve.
    pre = (cfg["boot"].get("pre_launch_command") or "").strip()
    if pre:
        platforms.run_pre_launch(pre)

    sound.play(cfg)

    # Snapshot the windows already open before we relaunch anything. These are
    # never moved: a single-instance app (Ptyxis, a browser) would otherwise have
    # an existing window yanked to a saved spot while its freshly-launched window
    # is left at the default — the classic "the terminal didn't move" bug.
    pre_existing = {w.get("id") for w in platforms.win_list()}

    # Launch every saved window, then place them. Launching all first lets apps
    # start in parallel; we remember each spawned PID so placement can tie a
    # window back to the process that opened it. A launch that fails is logged
    # and skipped — and, crucially, not waited on — so it can't stall the boot.
    ports = paths.control_panel_ports()
    launched = []
    for entry in layout:
        # Never relaunch Clap to Open's own control panel (skips it even in
        # layouts captured before it was excluded).
        if launchspec.is_control_panel(entry.get("argv"), ports):
            continue
        argv = launchspec.apply_strategy(entry)
        if not argv:
            continue
        try:
            proc = platforms.launch(argv)
            launched.append((entry, getattr(proc, "pid", None)))
        except OSError as e:
            print(f"clap-to-open: could not launch {entry.get('wm_class')}: {e}",
                  flush=True)

    # Place windows as they appear, in a single polling loop rather than a
    # blocking wait per entry. A slow-to-open app (e.g. one whose launcher first
    # starts a docker stack) then doesn't hold up the others — every still-pending
    # entry is retried each tick and placed the moment its window shows up.
    placed = set()
    matched = []
    pending = list(launched)
    deadline = time.time() + PLACE_TIMEOUT
    while pending and time.time() < deadline:
        still = []
        for entry, pid in pending:
            wid = platforms.place_once(entry, placed, pre_existing, pid)
            if wid is not None:
                matched.append((entry, wid))
            else:
                still.append((entry, pid))
        pending = still
        if pending:
            time.sleep(0.5)

    # Last resort for anything still unplaced: the app may be single-instance and
    # have just re-focused a window it already had open, so no new window ever
    # appeared. Allow matching one of those pre-existing windows now (the old
    # behaviour) rather than leaving the entry unplaced entirely.
    for entry, pid in pending:
        wid = platforms.place_once(entry, placed, frozenset(), pid)
        if wid is not None:
            matched.append((entry, wid))
        else:
            print(f"clap-to-open: no window found for "
                  f"{entry.get('wm_class')!r}; left unplaced", flush=True)

    # Many apps finish their own window layout a second or several after we first
    # placed them, drifting off the saved spot — most visibly when the target is
    # a non-primary monitor, which the WM and the app both keep pulling the window
    # away from. A single reassert loses that race, so keep reasserting on a short
    # poll until every window holds its saved rect. Bounded so a slow app can't
    # stall the boot indefinitely.
    if matched:
        platforms.settle_geometry(matched)


if __name__ == "__main__":
    main()
