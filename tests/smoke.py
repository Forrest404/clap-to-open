"""Cross-platform smoke test — runs on Linux and Windows CI.

Verifies imports, config/layout validation, that the platform backend resolves
and degrades gracefully, a pure Win32 helper, and that the web endpoints respond.
Real window placement / sound / hotkey are NOT exercised here (need a desktop).
"""
import clap_to_open.boot          # noqa: F401
import clap_to_open.cli           # noqa: F401
import clap_to_open.config as c
import clap_to_open.launchspec as ls
import clap_to_open.layout as L
import clap_to_open.save          # noqa: F401
import clap_to_open.sound         # noqa: F401
import clap_to_open.platforms.windows as W
from clap_to_open import platforms
from clap_to_open.web import server


def main():
    cfg = c.load()
    assert cfg["trigger"]["clap_count"] in (2, 3)

    # config validation clamps bad values
    assert c._validate({**c.DEFAULTS,
                        "trigger": {"clap_count": 9, "cooldown_seconds": 5}}
                       )["trigger"]["clap_count"] == 2

    # layout validation: command -> argv, and empty argv rejected
    assert L.clean([{"wm_class": "x", "command": "/bin/x --y", "x": 0, "y": 0,
                     "width": 10, "height": 10, "monitor": 0}])[0]["argv"] == ["/bin/x", "--y"]
    try:
        L.clean([{"wm_class": "x", "command": "", "width": 10, "height": 10}])
        raise SystemExit("layout validation did not reject empty command")
    except ValueError:
        pass

    # launchspec.apply_strategy — the heart of the "window didn't open" fix.
    #   single-instance terminal: strip the service flag, force a new window,
    #   and still compose the optional run-command.
    ptyxis = ls.apply_strategy({"wm_class": "org.gnome.Ptyxis",
                                "launch": ["/usr/bin/ptyxis", "--gapplication-service"]})
    assert "--gapplication-service" not in ptyxis, ptyxis
    assert "--new-window" in ptyxis, ptyxis
    ptyxis_run = ls.apply_strategy({"launch": ["ptyxis"], "run": "htop"})
    assert ptyxis_run == ["ptyxis", "--new-window", "--", "htop"], ptyxis_run
    #   Chromium PWA window -> --app=<url> --class=<wm_class> (a placeable window);
    #   ordinary browser window -> --new-window (carrying the URL).
    pwa = ls.apply_strategy({"wm_class": "brave-localhost__-Default",
                             "argv": ["/opt/brave.com/brave/brave", "http://localhost:7333/"]})
    assert pwa == ["/opt/brave.com/brave/brave", "--app=http://localhost:7333/",
                   "--class=brave-localhost__-Default"], pwa
    win = ls.apply_strategy({"wm_class": "brave-browser",
                             "argv": ["brave-browser", "http://localhost:7333/"]})
    assert win == ["brave-browser", "--new-window", "http://localhost:7333/"], win
    #   flatpak app launches via `flatpak run`, with new-window passed through.
    flat = ls.apply_strategy({"wm_class": "brave-browser", "app_id": "com.brave.Browser",
                              "launch": ["flatpak", "run", "com.brave.Browser"]})
    assert flat == ["flatpak", "run", "com.brave.Browser", "--new-window"], flat
    #   a plain app with no strategy replays verbatim.
    assert ls.apply_strategy({"wm_class": "blender", "launch": ["blender"]}) == ["blender"]

    # layout round-trip preserves resolved fields while the command is unchanged,
    # and drops them once the user edits the command.
    src = [{"wm_class": "org.gnome.Ptyxis", "argv": ["ptyxis"],
            "launch": ["ptyxis"], "app_id": "", "desktop_id": "org.gnome.Ptyxis.desktop",
            "x": 0, "y": 0, "width": 10, "height": 10, "monitor": 0}]
    api = L.to_api(src)[0]
    assert api["command"] == "ptyxis" and api["desktop_id"] == "org.gnome.Ptyxis.desktop"
    kept = L.clean([api])[0]
    assert kept.get("desktop_id") == "org.gnome.Ptyxis.desktop", kept
    edited = L.clean([{**api, "command": "ptyxis --new-window"}])[0]
    assert "desktop_id" not in edited and "launch" not in edited, edited

    # Clap to Open never captures/relaunches its own control panel, but leaves
    # other localhost apps (a real dashboard on a different port) alone.
    P = {7333}
    assert ls.is_control_panel(["brave", "http://localhost:7333/"], P)
    assert ls.is_control_panel(["brave", "--app=http://127.0.0.1:7333/"], P)
    assert not ls.is_control_panel(["brave", "http://localhost:7000/"], P)  # Odysseus
    assert not ls.is_control_panel(["brave", "https://github.com/x/clap-to-open"], P)
    assert not ls.is_control_panel(["blender"], P)

    # place() accepts the new pid kwarg on every backend (no desktop needed).
    assert platforms.place({"wm_class": ""}, set(), timeout=0, pid=None) is False

    # platform backend resolves; listings degrade gracefully to lists anywhere
    print("backend:", platforms._backend.__name__)
    assert isinstance(platforms.list_monitors(), list)
    assert isinstance(platforms.list_apps(), list)
    assert {"listening", "autostart"} <= set(platforms.svc_status())
    assert {"available", "binding"} <= set(platforms.hk_status())

    # pure Win32 helper works on any OS
    mods, vk = W._parse_accel("<Control><Alt>j")
    assert vk == ord("J") and mods, (mods, vk)

    # web endpoints respond
    tc = server.app.test_client()
    for ep in ("/api/layout", "/api/monitors", "/api/apps",
               "/api/status", "/api/hotkey"):
        assert tc.get(ep).status_code == 200, ep

    print("smoke OK")


if __name__ == "__main__":
    main()
