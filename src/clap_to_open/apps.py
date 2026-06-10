"""List installed desktop applications for the layout editor's app picker.

Uses ``Gio.DesktopAppInfo`` (PyGObject, already installed): it parses every
``.desktop`` file on the system, strips ``Exec`` field codes (%U %F %i …) and
resolves flatpak exec lines for us. For each app we also work out the window
class boot.py will need to match the launched window — ``StartupWMClass`` when
present, otherwise the desktop id, otherwise the executable's basename.
"""
import os
import shlex


def _wm_class(info):
    """Return (wm_class, guessed): guessed=False only when from StartupWMClass."""
    cls = info.get_startup_wm_class()
    if cls:
        return cls, False
    desktop_id = info.get_id() or ""
    if desktop_id.endswith(".desktop"):
        desktop_id = desktop_id[: -len(".desktop")]
    if desktop_id:
        return desktop_id, True
    exe = info.get_executable() or ""
    return os.path.basename(exe), True


def _icon_name(info):
    icon = info.get_icon()
    if icon is None:
        return None
    # Themed icons expose a name; file icons expose a path.
    try:
        from gi.repository import Gio
        if isinstance(icon, Gio.ThemedIcon):
            names = icon.get_names()
            return names[0] if names else None
        if isinstance(icon, Gio.FileIcon):
            return icon.get_file().get_path()
    except Exception:
        pass
    return icon.to_string() if hasattr(icon, "to_string") else None


def list_apps():
    """Return launchable apps: [{name, exec(list), icon, wm_class, desktop_id}].

    Sorted by name; hidden/no-display entries skipped. Empty list off-GNOME.
    """
    try:
        from gi.repository import Gio
    except Exception:
        return []

    apps = []
    seen = set()
    for info in Gio.DesktopAppInfo.get_all():
        if not info.should_show():       # respects NoDisplay/Hidden/OnlyShowIn
            continue
        cmdline = info.get_commandline()
        if not cmdline:
            continue
        try:
            argv = shlex.split(cmdline)
        except ValueError:
            argv = cmdline.split()
        # Drop leftover Exec field codes (%U %F %i …) and flatpak file-forwarding
        # placeholders (@@, @@u) — they only matter when opening files/URLs.
        argv = [a for a in argv
                if not (len(a) == 2 and a[0] == "%") and not a.startswith("@@")]
        if not argv:
            continue
        desktop_id = info.get_id() or ""
        if desktop_id in seen:
            continue
        seen.add(desktop_id)
        wm_class, guessed = _wm_class(info)
        apps.append({
            "name": info.get_display_name() or argv[0],
            "exec": argv,
            "icon": _icon_name(info),
            "wm_class": wm_class,
            "wm_class_guessed": guessed,
            "desktop_id": desktop_id,
        })
    apps.sort(key=lambda a: a["name"].lower())
    return apps
