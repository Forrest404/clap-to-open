"""Flask app + JSON API behind the control panel.

The page is a single static template driven by ``fetch`` calls (no build step).
Every mutating endpoint funnels through :mod:`clap_to_open.config` and
:mod:`clap_to_open.service` so the listener and boot always see consistent state.
"""
import subprocess
import sys
import threading
import webbrowser

from flask import Flask, jsonify, request, send_from_directory

from .. import apps, config, hotkey, layout, monitors, save, service, sound

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


def _layout_payload():
    entries = layout.load()
    return {
        "count": len(entries),
        "windows": layout.to_api(entries),
        "monitors": monitors.list_monitors(),
    }


@app.get("/api/layout")
def api_get_layout():
    return jsonify(_layout_payload())


@app.post("/api/layout")
def api_set_layout():
    mons = monitors.list_monitors()
    try:
        entries = layout.clean((request.json or {}).get("windows", []),
                               monitor_count=len(mons) or None)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    save.save(entries)
    return jsonify(_layout_payload())


@app.post("/api/layout/capture")
def api_capture():
    save.save(save.capture())
    return jsonify(_layout_payload())


@app.post("/api/layout/clear")
def api_clear():
    save.save([])
    return jsonify(_layout_payload())


@app.get("/api/monitors")
def api_monitors():
    return jsonify(monitors.list_monitors())


@app.get("/api/apps")
def api_apps():
    return jsonify(apps.list_apps())


@app.get("/api/windows/open")
def api_open_windows():
    return jsonify(save.capture())


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
