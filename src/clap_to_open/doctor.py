"""``clap doctor`` — diagnose the local setup and say exactly what to fix.

Cross-platform. Catches the common silent failures (missing GNOME window-calls
extension, no mic, missing sound player, missing Win32 deps) so a new user gets
a clear checklist instead of a tool that quietly does nothing.
"""
import contextlib
import json
import os
import shutil
import subprocess
import sys

from . import paths, platforms

_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


@contextlib.contextmanager
def _silence_stderr():
    """Hide the C-level ALSA/JACK chatter PyAudio prints when it initialises."""
    try:
        fd = sys.stderr.fileno()
    except Exception:
        yield
        return
    saved = os.dup(fd)
    devnull = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(devnull, fd)
        yield
    finally:
        os.dup2(saved, fd)
        os.close(devnull)
        os.close(saved)


def _mark(sym, color):
    return f"\033[{color}m{sym}\033[0m" if _COLOR else sym


def _ok(msg):
    print(f"  {_mark('OK ', '32')} {msg}")


def _warn(msg):
    print(f"  {_mark('!  ', '33')} {msg}")


def _bad(msg):
    print(f"  {_mark('X  ', '31')} {msg}")


def run():
    is_win = sys.platform == "win32"
    print("Clap to Open — diagnostics\n")
    print(f"  .  Python {sys.version.split()[0]} on {sys.platform}")

    # --- audio ---
    try:
        import clapDetector  # noqa: F401
        _ok("clap-detector + PyAudio importable")
    except Exception as e:
        _bad(f"clap-detector/PyAudio not importable ({e}) — reinstall: pip install -e .")
    try:
        import pyaudio
        with _silence_stderr():
            pa = pyaudio.PyAudio()
        try:
            name = pa.get_default_input_device_info().get("name", "?")
            _ok(f"default microphone: {name}")
        except Exception:
            _warn("no default input device — plug in / enable a microphone")
        finally:
            pa.terminate()
    except Exception:
        pass  # already reported above

    # --- platform specifics ---
    if is_win:
        for mod in ("win32gui", "psutil"):
            try:
                __import__(mod)
                _ok(f"{mod} available")
            except Exception:
                _bad(f"{mod} missing — run scripts\\install.ps1")
    else:
        sess = os.environ.get("XDG_SESSION_TYPE", "unknown")
        (_ok if sess == "wayland" else _warn)(f"session type: {sess}")
        if shutil.which("gnome-extensions"):
            def _ext_list(*flags):
                try:
                    return subprocess.run(["gnome-extensions", "list", *flags],
                                          capture_output=True, text=True).stdout
                except Exception:
                    return ""
            if "window-calls" in _ext_list("--enabled"):
                _ok("GNOME window-calls extension installed & enabled")
            elif "window-calls" in _ext_list():
                _warn("window-calls installed but not enabled — "
                      "run: gnome-extensions enable window-calls@domandoman.xyz")
            else:
                _bad("GNOME window-calls extension MISSING — install it: "
                     "https://extensions.gnome.org/extension/4724/window-calls/")
        else:
            _warn("gnome-extensions not found — this tool targets GNOME")
        if shutil.which("paplay") or shutil.which("ffplay"):
            _ok("sound player present (paplay/ffplay)")
        else:
            _warn("no paplay/ffplay — the local startup sound won't play")

    # --- window backend / monitors ---
    try:
        mons = platforms.list_monitors()
        (_ok if mons else _warn)(f"monitors detected: {len(mons)}")
    except Exception as e:
        _bad(f"could not read monitors: {e}")

    # --- config / layout ---
    if os.path.exists(paths.CONFIG_PATH):
        _ok(f"config: {paths.CONFIG_PATH}")
    else:
        _warn("no config yet (created on first run)")
    if os.path.exists(paths.LAYOUT_PATH):
        try:
            with open(paths.LAYOUT_PATH) as f:
                n = len(json.load(f))
            (_ok if n else _warn)(f"saved layout: {n} window(s)")
        except Exception:
            _warn("layout.json is unreadable")
    else:
        _warn("no layout captured yet — open the panel and capture one")

    # --- listener ---
    try:
        st = platforms.svc_status()
        _ok(f"listener: {'on' if st['listening'] else 'off'} | "
            f"autostart: {'on' if st['autostart'] else 'off'}")
    except Exception as e:
        _warn(f"could not query listener: {e}")

    print(f"\nLegend: {_mark('OK', '32')} good   "
          f"{_mark('!', '33')} optional/heads-up   {_mark('X', '31')} must fix")
