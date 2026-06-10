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

    # Place each successfully-launched window as it appears.
    placed = set()
    matched = []
    for entry, pid in launched:
        wid = platforms.place(entry, placed, pid=pid)
        if wid is not None:
            matched.append((entry, wid))

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
