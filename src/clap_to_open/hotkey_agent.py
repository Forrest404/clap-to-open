"""Windows global-hotkey agent.

Runs as a detached ``pythonw`` process (autostarted from the Startup folder by
``platforms.windows.hk_set_binding``). It reads the chosen accelerator from
``config.json``, registers it with Win32 ``RegisterHotKey``, and runs
``clap ctl toggle`` whenever it fires. This mirrors the GNOME model where the
keybinding simply runs ``clap ctl toggle`` — no toggle logic is duplicated.

Linux import-safe: only stdlib + config/paths at module load; all Win32 work is
inside ``main()`` and this is only ever launched on Windows.
"""
import subprocess

from . import config, paths


def main():
    import ctypes
    from ctypes import wintypes

    from .platforms.windows import _parse_accel

    accel = config.load().get("hotkey", {}).get("accel", "")
    if not accel:
        return
    mods, vk = _parse_accel(accel)
    if not mods or vk is None:
        return

    user32 = ctypes.windll.user32
    MOD_NOREPEAT = 0x4000
    WM_HOTKEY = 0x0312
    HOTKEY_ID = 1

    if not user32.RegisterHotKey(None, HOTKEY_ID, mods | MOD_NOREPEAT, vk):
        return  # combo already owned by another app

    try:
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                subprocess.Popen(
                    [paths.VENV_PYTHON, "-m", "clap_to_open.cli", "ctl", "toggle"],
                    cwd=paths.PROJECT_ROOT)
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
    finally:
        user32.UnregisterHotKey(None, HOTKEY_ID)


if __name__ == "__main__":
    main()
