"""Project-relative path resolution.

Everything this tool needs at runtime lives inside the project folder so it
stays fully self-contained: the venv, ``config.json``, ``layout.json`` and the
bundled sounds. This module is the single place that knows where the project
root is, so nothing else has to compute ``../..`` chains.
"""
import os
import sys

IS_WINDOWS = sys.platform == "win32"

# src/clap_to_open/paths.py  ->  parents: clap_to_open, src, <project root>
PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

CONFIG_PATH = os.path.join(PROJECT_ROOT, "config.json")
LAYOUT_PATH = os.path.join(PROJECT_ROOT, "layout.json")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
SOUNDS_DIR = os.path.join(DATA_DIR, "sounds")
BRAVE_SOUND_PROFILE = os.path.join(DATA_DIR, "brave-sound")

# venv interpreter — Windows uses Scripts\pythonw.exe (no console window) for the
# detached background listener; Linux uses bin/python under the systemd service.
if IS_WINDOWS:
    VENV_PYTHON = os.path.join(PROJECT_ROOT, "venv", "Scripts", "pythonw.exe")
    VENV_CLAP = os.path.join(PROJECT_ROOT, "venv", "Scripts", "clap.exe")
else:
    VENV_PYTHON = os.path.join(PROJECT_ROOT, "venv", "bin", "python")
    VENV_CLAP = os.path.join(PROJECT_ROOT, "venv", "bin", "clap")

# Mutable runtime state. On Windows the listener has no systemd to track it, so
# we keep a PID file in %APPDATA%; on Linux state stays in the project folder.
if IS_WINDOWS:
    APP_DATA_DIR = os.path.join(os.environ.get("APPDATA", PROJECT_ROOT), "clap-to-open")
else:
    APP_DATA_DIR = PROJECT_ROOT
PID_FILE = os.path.join(APP_DATA_DIR, "listener.pid")

# systemd user unit name (installed into ~/.config/systemd/user/; Linux only).
SERVICE_NAME = "clap-to-open.service"


def resolve(path):
    """Expand ``~`` and make project-relative paths absolute against the root."""
    if not path:
        return path
    path = os.path.expanduser(path)
    if not os.path.isabs(path):
        path = os.path.join(PROJECT_ROOT, path)
    return path
