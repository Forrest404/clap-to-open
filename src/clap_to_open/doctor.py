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


def check():
    """Return diagnostics as a list of {status: ok|warn|bad, label, hint}.

    Shared by the CLI (``clap doctor``) and the web onboarding wizard.
    """
    is_win = sys.platform == "win32"
    out = []

    def add(status, label, hint=""):
        out.append({"status": status, "label": label, "hint": hint})

    # --- audio ---
    try:
        import clapDetector  # noqa: F401
        add("ok", "Clap detector + microphone library installed")
    except Exception as e:
        add("bad", "clap-detector / PyAudio not importable",
            f"{e} — reinstall with the install script")
    try:
        import pyaudio
        with _silence_stderr():
            pa = pyaudio.PyAudio()
        try:
            name = pa.get_default_input_device_info().get("name", "?")
            add("ok", f"Microphone detected: {name}")
        except Exception:
            add("warn", "No default microphone", "Plug in or enable a mic")
        finally:
            pa.terminate()
    except Exception:
        pass

    # --- platform specifics ---
    if is_win:
        for mod in ("win32gui", "psutil"):
            try:
                __import__(mod)
                add("ok", f"{mod} available")
            except Exception:
                add("bad", f"{mod} missing", "Re-run scripts\\install.ps1")
    else:
        sess = os.environ.get("XDG_SESSION_TYPE", "unknown")
        if sess == "wayland":
            add("ok", "Wayland session")
        else:
            add("warn", f"Session type: {sess}",
                "Window placement is tuned for GNOME on Wayland")
        if shutil.which("gnome-extensions"):
            def _ext_list(*flags):
                try:
                    return subprocess.run(["gnome-extensions", "list", *flags],
                                          capture_output=True, text=True).stdout
                except Exception:
                    return ""
            if "window-calls" in _ext_list("--enabled"):
                add("ok", "GNOME window-calls extension enabled")
            elif "window-calls" in _ext_list():
                add("warn", "window-calls extension installed but disabled",
                    "Run: gnome-extensions enable window-calls@domandoman.xyz")
            else:
                add("bad", "GNOME window-calls extension is required but missing",
                    "Install it from extensions.gnome.org/extension/4724/window-calls/")
        else:
            add("warn", "gnome-extensions not found",
                "This tool targets GNOME — window placement needs window-calls")
        if shutil.which("paplay") or shutil.which("ffplay"):
            add("ok", "Sound player present")
        else:
            add("warn", "No paplay/ffplay", "The startup sound won't play")

    # --- monitors ---
    try:
        mons = platforms.list_monitors()
        add("ok" if mons else "warn", f"{len(mons)} monitor(s) detected")
    except Exception as e:
        add("bad", "Could not read monitors", str(e))

    # --- saved layout ---
    n = 0
    if os.path.exists(paths.LAYOUT_PATH):
        try:
            with open(paths.LAYOUT_PATH) as f:
                n = len(json.load(f))
        except Exception:
            n = 0
    if n:
        add("ok", f"Saved layout: {n} window(s)")
    else:
        add("warn", "No layout captured yet", "Capture one in the next step")

    return out


def run():
    print("Clap to Open — diagnostics\n")
    print(f"  .  Python {sys.version.split()[0]} on {sys.platform}")
    fn = {"ok": _ok, "warn": _warn, "bad": _bad}
    for c in check():
        msg = c["label"] + (f" — {c['hint']}" if c["hint"] else "")
        fn[c["status"]](msg)
    try:
        st = platforms.svc_status()
        _ok(f"listener: {'on' if st['listening'] else 'off'} | "
            f"autostart: {'on' if st['autostart'] else 'off'}")
    except Exception:
        pass
    print(f"\nLegend: {_mark('OK', '32')} good   "
          f"{_mark('!', '33')} optional/heads-up   {_mark('X', '31')} must fix")
