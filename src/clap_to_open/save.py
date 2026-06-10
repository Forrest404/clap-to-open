"""Snapshot the current window layout for :mod:`clap_to_open.boot` to replay.

Captures every normal app window open right now — its launch command (from
``/proc/<pid>/cmdline``), geometry, monitor and maximized state — into
``layout.json``. Re-run any time you rearrange your desktop.
"""
import json
import os

from . import paths, platforms


def capture():
    """Return the list of layout entries for the currently open normal windows."""
    entries = []
    for w in platforms.win_list():
        if w.get("window_type") != 0:          # keep only NORMAL windows
            continue
        argv = platforms.window_cmdline(w["pid"])
        if not argv:
            print(f"  skip {w.get('wm_class')}: no readable cmdline")
            continue
        d = platforms.window_details(w["id"]) or {}
        entries.append({
            "wm_class": w.get("wm_class"),
            "title": w.get("title"),
            "argv": argv,
            "x": d.get("x"),
            "y": d.get("y"),
            "width": d.get("width"),
            "height": d.get("height"),
            "monitor": d.get("monitor"),
            "maximized": bool(d.get("maximized")),
        })
    return entries


def save(entries):
    os.makedirs(os.path.dirname(paths.LAYOUT_PATH), exist_ok=True)
    with open(paths.LAYOUT_PATH, "w") as f:
        json.dump(entries, f, indent=2)


def main():
    entries = capture()
    save(entries)
    print(f"Saved {len(entries)} window(s) to {paths.LAYOUT_PATH}:")
    for e in entries:
        geo = "maximized" if e["maximized"] else \
            f"{e['width']}x{e['height']} @ {e['x']},{e['y']}"
        print(f"  {str(e['wm_class']):30} mon={e['monitor']}  {geo}")


if __name__ == "__main__":
    main()
