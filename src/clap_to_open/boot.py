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
import subprocess

from . import config, paths, sound, windows


def _launch(argv):
    """Fire-and-forget launch, inheriting the session env (Wayland/DBus)."""
    return subprocess.Popen(list(argv))


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
        subprocess.run(["bash", "-lc", pre])

    sound.play(cfg)

    # Launch every saved window. A bad/unrunnable command (e.g. a sandbox-only
    # Flatpak path) is skipped so it doesn't abort the rest of the boot.
    for entry in layout:
        try:
            _launch(entry["argv"])
        except OSError as e:
            print(f"clap-to-open: could not launch {entry.get('wm_class')}: {e}",
                  flush=True)

    # Place each window as it appears.
    placed = set()
    for entry in layout:
        windows.place(entry, placed)


if __name__ == "__main__":
    main()
