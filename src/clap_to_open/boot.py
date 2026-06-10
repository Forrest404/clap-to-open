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
import os
import shlex

from . import config, paths, platforms, sound

# How common terminals run a command passed to them. Anything not listed falls
# back to "-e" (xterm/konsole-style), which most terminals accept.
_TERMINAL_RUN = {
    "ptyxis": ["--"], "gnome-terminal": ["--"], "kgx": ["--"],
    "kitty": [], "foot": [], "wezterm": ["start", "--"],
    "konsole": ["-e"], "xterm": ["-e"], "uxterm": ["-e"], "alacritty": ["-e"],
    "tilix": ["-e"], "terminator": ["-x"], "xfce4-terminal": ["-x"],
    "wt": [], "windows-terminal": [],
}


def _build_argv(entry):
    """Final launch argv, appending the optional ``run`` command for terminals."""
    argv = [a for a in (entry.get("argv") or [])
            if a != "--gapplication-service"]  # service flag never opens a window
    run = (entry.get("run") or "").strip()
    if run and argv:
        term = os.path.splitext(os.path.basename(argv[0]))[0].lower()
        sep = _TERMINAL_RUN.get(term, ["-e"])
        try:
            argv = argv + sep + shlex.split(run)
        except ValueError:
            argv = argv + sep + [run]
    return argv


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

    # Launch every saved window. A bad/unrunnable command (e.g. a sandbox-only
    # Flatpak path) is skipped so it doesn't abort the rest of the boot — and
    # we don't then waste time waiting for a window it could never have opened.
    launched = []
    for entry in layout:
        try:
            platforms.launch(_build_argv(entry))
            launched.append(entry)
        except OSError as e:
            print(f"clap-to-open: could not launch {entry.get('wm_class')}: {e}",
                  flush=True)

    # Place each successfully-launched window as it appears.
    placed = set()
    for entry in launched:
        platforms.place(entry, placed)


if __name__ == "__main__":
    main()
