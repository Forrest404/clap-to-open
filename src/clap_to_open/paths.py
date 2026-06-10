r"""Where everything lives — works both as a cloned repo and a `pipx`/PyPI install.

User data (config, layout, the browser sound profile, the listener PID) lives in
a standard per-user directory (`~/.config/clap-to-open`, `%APPDATA%\clap-to-open`,
`~/Library/Application Support/clap-to-open`). The bundled startup sounds ship
**inside the package** (`clap_to_open/assets/sounds/`) and are read via
``importlib.resources``. Background processes (the listener, the hotkey agent)
are launched with the running interpreter (``sys.executable``), so it doesn't
matter whether that's a repo venv or the pipx venv.
"""
import os
import sys

IS_WINDOWS = sys.platform == "win32"


def _user_dir():
    if IS_WINDOWS:
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "clap-to-open")


# Per-user state directory (created on first run by config.ensure_exists()).
CONFIG_DIR = _user_dir()
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
LAYOUT_PATH = os.path.join(CONFIG_DIR, "layout.json")
BRAVE_SOUND_PROFILE = os.path.join(CONFIG_DIR, "brave-sound")
PID_FILE = os.path.join(CONFIG_DIR, "listener.pid")
APP_DATA_DIR = CONFIG_DIR  # back-compat alias

SERVICE_NAME = "clap-to-open.service"

# Legacy self-contained location (config beside the source), for one-time
# migration when upgrading a cloned-repo install to the user-dir layout.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LEGACY_CONFIG = os.path.join(_REPO_ROOT, "config.json")
LEGACY_LAYOUT = os.path.join(_REPO_ROOT, "layout.json")


def ensure_dirs():
    os.makedirs(CONFIG_DIR, exist_ok=True)


def background_python():
    """Interpreter for detached background processes (listener, hotkey agent).

    On Windows prefer ``pythonw.exe`` (no console) next to the current
    interpreter; everywhere else use ``sys.executable``.
    """
    exe = sys.executable
    if IS_WINDOWS:
        cand = os.path.join(os.path.dirname(exe), "pythonw.exe")
        return cand if os.path.exists(cand) else exe
    return exe


def bundled_sound(filename):
    """Absolute path to a startup sound shipped inside the package, or ""."""
    try:
        from importlib.resources import files
        return str(files("clap_to_open").joinpath("assets", "sounds", filename))
    except Exception:
        return ""


def resolve(path):
    """Expand ``~`` and make a relative path absolute against the user dir."""
    if not path:
        return path
    path = os.path.expanduser(path)
    if not os.path.isabs(path):
        path = os.path.join(CONFIG_DIR, path)
    return path
