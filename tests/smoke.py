"""Cross-platform smoke test — runs on Linux and Windows CI.

Verifies imports, config/layout validation, that the platform backend resolves
and degrades gracefully, a pure Win32 helper, and that the web endpoints respond.
Real window placement / sound / hotkey are NOT exercised here (need a desktop).
"""
import clap_to_open.boot          # noqa: F401
import clap_to_open.cli           # noqa: F401
import clap_to_open.config as c
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
