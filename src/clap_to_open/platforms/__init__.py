"""Platform backend selector.

Picks the OS-specific implementation once at import time and re-exports its
flat function interface so callers can do ``from .. import platforms`` and call
``platforms.win_list()``, ``platforms.svc_toggle()``, etc. regardless of OS.

Backends (``linux``, ``windows``, ``base``) all expose the same names; OS-only
libraries are imported lazily inside the backend functions, so importing this
package never fails on the "wrong" OS — only calling a function that needs the
absent OS would.
"""
import sys

if sys.platform == "win32":
    from . import windows as _backend
elif sys.platform.startswith("linux"):
    from . import linux as _backend
else:
    from . import base as _backend

# The complete backend interface, re-exported from the selected module.
_NAMES = [
    "DEFAULT_SOUND_FILENAME",
    "win_list", "window_details", "window_cmdline", "place", "reassert_geometry",
    "settle_geometry",
    "list_monitors", "list_apps",
    "launch", "run_pre_launch",
    "play_file", "play_url",
    "svc_is_active", "svc_is_enabled", "svc_start", "svc_stop",
    "svc_restart", "svc_toggle", "svc_set_autostart", "svc_status",
    "hk_available", "hk_status", "hk_set_binding", "hk_clear",
]

for _name in _NAMES:
    globals()[_name] = getattr(_backend, _name)

__all__ = list(_NAMES)
