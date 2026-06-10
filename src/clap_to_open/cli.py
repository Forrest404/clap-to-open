"""``clap`` command — the single entry point for everything.

    clap serve [--port N] [--no-open]   start the web control panel
    clap boot                           replay the saved layout now
    clap save                           capture the current window layout
    clap ctl on|off|toggle|status       control the listener service
    clap doctor                         diagnose the local setup
"""
import argparse
import sys

from . import boot, config, doctor, platforms, save


def _notify(title, body, icon=None):
    import shutil
    import subprocess
    if shutil.which("notify-send"):
        args = ["notify-send"]
        if icon:
            args += ["-i", icon]
        subprocess.run(args + [title, body])


def cmd_ctl(args):
    action = args.action
    if action == "status":
        st = platforms.svc_status()
        print(f"listening: {'on' if st['listening'] else 'off'}")
        print(f"autostart: {'on' if st['autostart'] else 'off'}")
        return
    if action == "on":
        platforms.svc_start()
        on = True
    elif action == "off":
        platforms.svc_stop()
        on = False
    else:  # toggle
        on = platforms.svc_toggle()
    if on:
        print("clap-to-open: ON (listening for claps)")
        _notify("Clap to Open: ON", "Listening for claps.",
                "audio-input-microphone-symbolic")
    else:
        print("clap-to-open: OFF (mic not listening)")
        _notify("Clap to Open: OFF", "Mic is no longer listening.",
                "microphone-sensitivity-muted-symbolic")


def cmd_serve(args):
    from .web.server import run
    config.ensure_exists()
    run(port=args.port, open_browser=not args.no_open)


def main(argv=None):
    config.ensure_exists()
    parser = argparse.ArgumentParser(prog="clap", description="Clap to Open")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_serve = sub.add_parser("serve", help="start the web control panel")
    p_serve.add_argument("--port", type=int, default=7333)
    p_serve.add_argument("--no-open", action="store_true",
                         help="don't open a browser window")
    p_serve.set_defaults(func=cmd_serve)

    sub.add_parser("boot", help="replay the saved layout now").set_defaults(
        func=lambda a: boot.main())
    sub.add_parser("save", help="capture the current window layout").set_defaults(
        func=lambda a: save.main())
    sub.add_parser("doctor", help="diagnose the local setup").set_defaults(
        func=lambda a: doctor.run())

    p_ctl = sub.add_parser("ctl", help="control the listener service")
    p_ctl.add_argument("action", choices=["on", "off", "toggle", "status"])
    p_ctl.set_defaults(func=cmd_ctl)

    args = parser.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
