"""Windows 10/11 backend.

Implements the same interface as ``linux.py`` using Win32 (``pywin32``),
``psutil`` and a little ``ctypes`` for DPI / monitor DPI / MCI sound. All
OS-specific imports are done lazily inside functions so this module imports
cleanly on any OS (it's only *selected* when running on Windows); that keeps the
Linux test/CI green.

CANNOT be verified on the Linux dev box — see the project plan. Treat window
placement, sound, the detached listener, autostart and the hotkey as
best-effort until exercised on real Windows.
"""
import os
import re
import subprocess
import time

from .. import paths

DEFAULT_SOUND_FILENAME = "boot.wav"

# RegisterHotKey modifier bits (winuser.h)
_MOD = {"control": 0x0002, "primary": 0x0002, "ctrl": 0x0002,
        "alt": 0x0001, "shift": 0x0004, "super": 0x0008, "meta": 0x0008, "win": 0x0008}
_MOD_NOREPEAT = 0x4000


# ---------------------------------------------------------------- DPI awareness
_dpi_done = False


def _ensure_dpi():
    """Make this process Per-Monitor-DPI-Aware so all geometry is physical px."""
    global _dpi_done
    if _dpi_done:
        return
    import ctypes
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # PMv2
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
    _dpi_done = True


# ------------------------------------------------------------- window enumerate
def _exe_basename(pid):
    import psutil
    try:
        return os.path.basename(psutil.Process(pid).exe()).lower()
    except Exception:
        return ""


def win_list():
    """Top-level app windows as [{id(hwnd), pid, wm_class, title, window_type}].

    wm_class is the process EXE basename (lowercased) — the stable key that also
    matches what ``launch(argv)`` starts; Win32 class names are too generic.
    """
    import win32gui
    import win32con
    import win32process
    _ensure_dpi()
    out = []

    def _cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        if win32gui.GetWindow(hwnd, win32con.GW_OWNER):
            return True
        ex = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        if ex & win32con.WS_EX_TOOLWINDOW:
            return True
        title = win32gui.GetWindowText(hwnd)
        if not title:
            return True
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        out.append({
            "id": hwnd, "pid": pid, "wm_class": _exe_basename(pid),
            "title": title, "window_type": 0,
        })
        return True

    win32gui.EnumWindows(_cb, None)
    return out


def window_details(win_id):
    """Normalized geometry/state: {x, y, width, height, monitor, maximized}."""
    import win32gui
    import win32con
    _ensure_dpi()
    hwnd = int(win_id)
    try:
        l, t, r, b = win32gui.GetWindowRect(hwnd)
    except Exception:
        return None
    try:
        maximized = win32gui.GetWindowPlacement(hwnd)[1] == win32con.SW_SHOWMAXIMIZED
    except Exception:
        maximized = False
    return {"x": l, "y": t, "width": r - l, "height": b - t,
            "monitor": _monitor_index_for_point((l + r) // 2, (t + b) // 2),
            "maximized": maximized}


def window_cmdline(pid):
    import psutil
    try:
        p = psutil.Process(pid)
        return p.cmdline() or [p.exe()]
    except Exception:
        return None


def place(entry, placed, timeout=12):
    """Match entry's wm_class (exe basename) to an unplaced window and position it."""
    import win32gui
    import win32con
    _ensure_dpi()
    match = (entry.get("wm_class") or "").lower()
    deadline = time.time() + timeout
    while time.time() < deadline:
        for w in win_list():
            if w["id"] in placed:
                continue
            if match and match == (w.get("wm_class") or "").lower():
                hwnd = w["id"]
                placed.add(hwnd)
                try:
                    if entry.get("maximized"):
                        win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
                    else:
                        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                        win32gui.SetWindowPos(
                            hwnd, 0, int(entry["x"]), int(entry["y"]),
                            int(entry["width"]), int(entry["height"]),
                            win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE)
                except Exception as e:
                    print(f"clap-to-open: place failed for {match}: {e}", flush=True)
                return True
        time.sleep(0.4)
    print(f"clap-to-open: window '{match}' did not appear in {timeout}s", flush=True)
    return False


# ------------------------------------------------------------------- monitors
def list_monitors():
    import ctypes
    import win32api
    _ensure_dpi()
    out = []
    try:
        handles = win32api.EnumDisplayMonitors()
    except Exception:
        return []
    for i, mon in enumerate(handles):
        hmon = mon[0]
        try:
            info = win32api.GetMonitorInfo(hmon)
        except Exception:
            continue
        l, t, r, b = info["Monitor"]
        primary = bool(info.get("Flags", 0) & 1)  # MONITORINFOF_PRIMARY
        device = (info.get("Device") or "").replace("\\\\.\\", "").replace("\\.\\", "")
        scale = 1.0
        try:
            dx, dy = ctypes.c_uint(), ctypes.c_uint()
            ctypes.windll.shcore.GetDpiForMonitor(
                int(hmon), 0, ctypes.byref(dx), ctypes.byref(dy))  # MDT_EFFECTIVE_DPI
            scale = round(dx.value / 96.0, 4)
        except Exception:
            pass
        out.append({
            "index": i, "connector": device or f"DISPLAY{i + 1}",
            "x": l, "y": t, "width": r - l, "height": b - t,
            "scale": scale, "primary": primary,
        })
    return out


def _monitor_index_for_point(x, y):
    for m in list_monitors():
        if m["x"] <= x < m["x"] + m["width"] and m["y"] <= y < m["y"] + m["height"]:
            return m["index"]
    return 0


# ----------------------------------------------------------------- installed apps
def list_apps():
    import glob
    try:
        import win32com.client
        shell = win32com.client.Dispatch("WScript.Shell")
    except Exception:
        return []
    roots = [
        os.path.join(os.environ.get("PROGRAMDATA", ""),
                     "Microsoft", "Windows", "Start Menu", "Programs"),
        os.path.join(os.environ.get("APPDATA", ""),
                     "Microsoft", "Windows", "Start Menu", "Programs"),
    ]
    seen, apps = set(), []
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        for lnk in glob.glob(os.path.join(root, "**", "*.lnk"), recursive=True):
            try:
                sc = shell.CreateShortcut(lnk)
                target = sc.TargetPath
            except Exception:
                continue
            # Skip non-exe / Store apps (no resolvable filesystem target).
            if not target or not target.lower().endswith(".exe") or not os.path.exists(target):
                continue
            args = sc.Arguments or ""
            key = (target.lower(), args)
            if key in seen:
                continue
            seen.add(key)
            argv = [target] + _split(args)
            apps.append({
                "name": os.path.splitext(os.path.basename(lnk))[0],
                "exec": argv,
                "icon": (sc.IconLocation or target).split(",")[0],
                "wm_class": os.path.basename(target).lower(),
                "wm_class_guessed": True,
                "desktop_id": lnk,
            })
    apps.sort(key=lambda a: a["name"].lower())
    return apps


def _split(s):
    import shlex
    try:
        return shlex.split(s, posix=False)
    except ValueError:
        return s.split()


# ----------------------------------------------------------------------- launch
def launch(argv):
    return subprocess.Popen(list(argv))


def run_pre_launch(command):
    subprocess.run(["cmd", "/c", command])


# ------------------------------------------------------------------------ sound
def _mci(command):
    import ctypes
    ctypes.windll.winmm.mciSendStringW(command, None, 0, 0)


def play_file(path):
    """Play a wav/mp3 via the Windows MCI API (fire-and-forget)."""
    p = paths.resolve(path)
    if not p or not os.path.exists(p):
        print(f"clap-to-open: sound file not found: {p}", flush=True)
        return
    try:
        _mci("close clapsnd")
        _mci(f'open "{p}" alias clapsnd')
        _mci("play clapsnd")
    except Exception as e:
        print(f"clap-to-open: sound failed: {e}", flush=True)


def play_url(url):
    if not url:
        return
    import shutil
    browser = None
    for name in ("chrome", "brave", "msedge"):
        browser = shutil.which(name) or shutil.which(name + ".exe")
        if browser:
            break
    if not browser:
        for cand in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                     r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
                     r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"):
            if os.path.exists(cand):
                browser = cand
                break
    if not browser:
        print("clap-to-open: no Chromium browser found for URL sound", flush=True)
        return
    subprocess.Popen([
        browser, f"--user-data-dir={paths.BRAVE_SOUND_PROFILE}",
        f"--app={url}", "--autoplay-policy=no-user-gesture-required",
        "--no-first-run", "--no-default-browser-check",
    ])


# ------------------------------------------------------- listener (PID-file)
def _read_pid():
    try:
        with open(paths.PID_FILE) as f:
            return int(f.read().strip())
    except Exception:
        return None


def svc_is_active():
    import psutil
    pid = _read_pid()
    if not pid:
        return False
    try:
        return "clap_to_open.listener" in " ".join(psutil.Process(pid).cmdline())
    except Exception:
        return False


def svc_start():
    if svc_is_active():
        return
    os.makedirs(paths.APP_DATA_DIR, exist_ok=True)
    # DETACHED_PROCESS | CREATE_NO_WINDOW so the listener runs headless.
    flags = 0x00000008 | 0x08000000
    p = subprocess.Popen(
        [paths.background_python(), "-m", "clap_to_open.listener"],
        cwd=paths.CONFIG_DIR, creationflags=flags, close_fds=True)
    with open(paths.PID_FILE, "w") as f:
        f.write(str(p.pid))


def svc_stop():
    import psutil
    pid = _read_pid()
    if pid:
        try:
            psutil.Process(pid).terminate()
        except Exception:
            pass
    try:
        os.remove(paths.PID_FILE)
    except OSError:
        pass


def svc_restart():
    if svc_is_active():
        svc_stop()
        time.sleep(0.5)
        svc_start()


def svc_toggle():
    if svc_is_active():
        svc_stop()
        return False
    svc_start()
    return True


def _startup_dir():
    return os.path.join(os.environ.get("APPDATA", ""),
                        "Microsoft", "Windows", "Start Menu", "Programs", "Startup")


def _make_shortcut(path, target, args, workdir):
    import win32com.client
    sc = win32com.client.Dispatch("WScript.Shell").CreateShortcut(path)
    sc.TargetPath = target
    sc.Arguments = args
    sc.WorkingDirectory = workdir
    sc.Save()


def _listener_lnk():
    return os.path.join(_startup_dir(), "Clap to Open Listener.lnk")


def svc_is_enabled():
    return os.path.exists(_listener_lnk())


def svc_set_autostart(on):
    if on:
        os.makedirs(_startup_dir(), exist_ok=True)
        _make_shortcut(_listener_lnk(), paths.background_python(),
                       "-m clap_to_open.listener", paths.CONFIG_DIR)
    else:
        try:
            os.remove(_listener_lnk())
        except OSError:
            pass


def svc_status():
    return {"listening": svc_is_active(), "autostart": svc_is_enabled()}


# -------------------------------------------------------------------- hotkey
def _parse_accel(accel):
    """GNOME-style accel (e.g. '<Control><Alt>j') -> (mods_bitmask, vk) or (0, None)."""
    mods = 0
    for m in re.findall(r"<([^>]+)>", accel or ""):
        mods |= _MOD.get(m.lower(), 0)
    key = re.sub(r"<[^>]+>", "", accel or "").strip()
    vk = None
    if len(key) == 1 and key.isalnum():
        vk = ord(key.upper())
    elif re.match(r"^[Ff]([1-9]|1[0-9]|2[0-4])$", key):
        vk = 0x70 + int(key[1:]) - 1  # VK_F1 == 0x70
    return mods, vk


def hk_available():
    return True


def _hotkey_lnk():
    return os.path.join(_startup_dir(), "Clap to Open Hotkey.lnk")


def hk_status():
    from .. import config
    return {"available": True,
            "binding": config.load().get("hotkey", {}).get("accel", "")}


def _agent_restart():
    """Restart the always-on hotkey agent so it picks up the new accel."""
    # Best-effort: a fresh agent process; the previous one exits when its lnk/
    # config change is detected, but to be safe we just spawn a new one. The
    # agent self-guards against double-registration via the accel in config.
    flags = 0x00000008 | 0x08000000
    try:
        subprocess.Popen([paths.background_python(), "-m", "clap_to_open.hotkey_agent"],
                         cwd=paths.CONFIG_DIR, creationflags=flags, close_fds=True)
    except Exception:
        pass


def hk_set_binding(accel):
    from .. import config
    if not accel:
        return hk_clear()
    mods, vk = _parse_accel(accel)
    if not mods or vk is None:
        return {"ok": False, "available": True,
                "error": "use a modifier (Ctrl/Alt/Win) plus a letter/F-key"}
    cfg = config.load()
    cfg.setdefault("hotkey", {})["accel"] = accel
    config.save(cfg)
    os.makedirs(_startup_dir(), exist_ok=True)
    _make_shortcut(_hotkey_lnk(), paths.background_python(),
                   "-m clap_to_open.hotkey_agent", paths.CONFIG_DIR)
    _agent_restart()
    return {"ok": True, "binding": accel, "available": True}


def hk_clear():
    from .. import config
    cfg = config.load()
    cfg.setdefault("hotkey", {})["accel"] = ""
    config.save(cfg)
    try:
        os.remove(_hotkey_lnk())
    except OSError:
        pass
    return {"ok": True, "binding": "", "available": True}
