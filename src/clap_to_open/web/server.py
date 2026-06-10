"""Flask app + JSON API behind the control panel.

The page is a single static template driven by ``fetch`` calls (no build step).
Every mutating endpoint funnels through :mod:`clap_to_open.config` and
:mod:`clap_to_open.service` so the listener and boot always see consistent state.
"""
import json
import os
import subprocess
import sys
import threading
import webbrowser

from flask import Flask, jsonify, request, send_from_directory

from .. import config, hotkey, paths, save, service, sound

app = Flask(
    __name__,
    static_folder="static",
    template_folder="templates",
)


@app.get("/")
def index():
    return send_from_directory(app.template_folder, "index.html")


@app.get("/api/status")
def api_status():
    return jsonify(service.status())


@app.post("/api/listening")
def api_listening():
    on = bool(request.json.get("on"))
    service.start() if on else service.stop()
    return jsonify(service.status())


@app.post("/api/autostart")
def api_autostart():
    service.set_autostart(bool(request.json.get("on")))
    return jsonify(service.status())


@app.get("/api/config")
def api_get_config():
    return jsonify(config.load())


@app.post("/api/config")
def api_set_config():
    cfg = config.save(request.json or {})
    # Apply new sensitivity / clap-count by restarting the listener if running.
    service.restart()
    return jsonify(cfg)


@app.post("/api/config/reset")
def api_reset():
    cfg = config.reset()
    service.restart()
    return jsonify(cfg)


@app.get("/api/hotkey")
def api_get_hotkey():
    return jsonify(hotkey.status())


@app.post("/api/hotkey")
def api_set_hotkey():
    accel = (request.json or {}).get("accel", "")
    return jsonify(hotkey.set_binding(accel))


@app.delete("/api/hotkey")
def api_clear_hotkey():
    return jsonify(hotkey.clear())


@app.get("/api/layout")
def api_get_layout():
    try:
        with open(paths.LAYOUT_PATH) as f:
            layout = json.load(f)
    except (OSError, json.JSONDecodeError):
        layout = []
    summary = [{
        "wm_class": e.get("wm_class"),
        "title": e.get("title"),
        "monitor": e.get("monitor"),
        "maximized": e.get("maximized"),
        "geometry": ("maximized" if e.get("maximized")
                     else f"{e.get('width')}x{e.get('height')} "
                          f"@ {e.get('x')},{e.get('y')}"),
    } for e in layout]
    return jsonify({"count": len(layout), "windows": summary})


@app.post("/api/layout/capture")
def api_capture():
    save.save(save.capture())
    return api_get_layout()


@app.post("/api/layout/clear")
def api_clear():
    save.save([])
    return api_get_layout()


@app.post("/api/test-boot")
def api_test_boot():
    subprocess.Popen([sys.executable, "-m", "clap_to_open.boot"])
    return jsonify({"ok": True})


@app.post("/api/test-sound")
def api_test_sound():
    sound.play(config.load())
    return jsonify({"ok": True})


def run(port=7333, open_browser=True):
    config.ensure_exists()
    url = f"http://localhost:{port}/"
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    print(f"clap-to-open: control panel at {url}", flush=True)
    app.run(host="127.0.0.1", port=port, debug=False)
