"""Load, merge, validate and save ``config.json`` — the single source of truth.

Both the listener and the boot sequence read their settings from here, and the
web UI writes here. Missing keys deep-merge against :data:`DEFAULTS`, so an old
or partial config never crashes a newer build.
"""
import copy
import json
import os
import shutil

from . import paths

DEFAULTS = {
    "version": 1,
    "sensitivity": {
        "threshold_bias": 1500,
        "lowcut": 200,
        "highcut": 2000,
        "reset_time": 0.6,
        "initial_volume_threshold": 2000,
        "input_device": -1,
    },
    "trigger": {
        "clap_count": 2,        # 2 or 3
        "cooldown_seconds": 5,
    },
    "sound": {
        "mode": "file",         # "file" | "url" | "off"
        # Empty = the bundled default sound (ironman.mp3 on Linux / boot.wav on
        # Windows, shipped inside the package). A non-empty path overrides it.
        "file": "",
        "url": "",
    },
    "boot": {
        # Optional shell command run once before any windows are launched, e.g.
        # to spin up a docker stack a saved app depends on. Empty = do nothing.
        "pre_launch_command": "",
    },
    # Set true once the user finishes (or skips) the first-run onboarding wizard.
    "onboarded": False,
}


def _deep_merge(base, override):
    """Recursively merge ``override`` onto a copy of ``base``."""
    out = copy.deepcopy(base)
    for key, val in (override or {}).items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def _validate(cfg):
    """Clamp/repair any values that would break the listener or boot."""
    trig = cfg["trigger"]
    if trig.get("clap_count") not in (2, 3):
        trig["clap_count"] = 2
    try:
        trig["cooldown_seconds"] = max(0, int(trig["cooldown_seconds"]))
    except (TypeError, ValueError):
        trig["cooldown_seconds"] = DEFAULTS["trigger"]["cooldown_seconds"]
    if cfg["sound"].get("mode") not in ("file", "url", "off"):
        cfg["sound"]["mode"] = "file"
    return cfg


def load():
    """Return the live config, deep-merged over defaults and validated."""
    raw = {}
    try:
        with open(paths.CONFIG_PATH) as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError):
        raw = {}
    return _validate(_deep_merge(DEFAULTS, raw))


def save(cfg):
    """Validate and atomically write the config (temp file + ``os.replace``)."""
    cfg = _validate(_deep_merge(DEFAULTS, cfg))
    os.makedirs(os.path.dirname(paths.CONFIG_PATH), exist_ok=True)
    tmp = paths.CONFIG_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")
    os.replace(tmp, paths.CONFIG_PATH)
    return cfg


def _migrate_legacy():
    """One-time: copy config/layout from the old in-repo location to the user dir.

    Earlier versions kept config.json/layout.json beside the source. When a
    cloned-repo install upgrades to the user-dir layout, bring those along so the
    user keeps their settings and captured layout.
    """
    paths.ensure_dirs()
    for src, dst in ((paths.LEGACY_CONFIG, paths.CONFIG_PATH),
                     (paths.LEGACY_LAYOUT, paths.LAYOUT_PATH)):
        try:
            if os.path.exists(src) and os.path.abspath(src) != os.path.abspath(dst):
                shutil.copy2(src, dst)
        except OSError:
            pass


def ensure_exists():
    """Seed ``config.json`` on first run (migrating a legacy repo config first)."""
    paths.ensure_dirs()
    if not os.path.exists(paths.CONFIG_PATH):
        if os.path.exists(paths.LEGACY_CONFIG):
            _migrate_legacy()
        else:
            save(DEFAULTS)
    return load()


def reset():
    """Restore all settings to defaults and return the fresh config.

    The toggle hotkey lives in GNOME settings (not here) and the onboarding flag
    isn't a "setting", so both are preserved across a reset.
    """
    fresh = copy.deepcopy(DEFAULTS)
    fresh["onboarded"] = load().get("onboarded", False)
    return save(fresh)
