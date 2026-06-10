"""Read the monitor layout from GNOME/Mutter for the visual layout editor.

``org.gnome.Mutter.DisplayConfig.GetCurrentState`` returns the physical monitors
(with their modes) and the *logical* monitors (position + scale). Window
coordinates in ``layout.json`` live in this logical space, and window-calls
reports a window's ``monitor`` as the index into the logical-monitors array — so
we return logical monitors in that same array order and expose the index.

We talk D-Bus through ``Gio`` (PyGObject is already installed) and use
``result.unpack()`` to get native Python tuples, avoiding any text parsing.
"""


def _current_resolution(physical_monitor):
    """Return (width_px, height_px) of the monitor's current mode, or None."""
    _info, modes, _props = physical_monitor
    for mode in modes:
        # mode = (id, width, height, refresh, preferred_scale, [scales], props)
        mode_props = mode[6]
        if mode_props.get("is-current"):
            return int(mode[1]), int(mode[2])
    return None


def list_monitors():
    """Return logical monitors as a list of dicts in Mutter array order.

    [{index, connector, x, y, width, height, scale, primary}], where width/height
    are logical pixels (current mode resolution / scale). Returns [] if the
    DisplayConfig service is unavailable (e.g. not running GNOME).
    """
    try:
        from gi.repository import Gio
    except Exception:
        return []
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        res = bus.call_sync(
            "org.gnome.Mutter.DisplayConfig",
            "/org/gnome/Mutter/DisplayConfig",
            "org.gnome.Mutter.DisplayConfig",
            "GetCurrentState",
            None, None, Gio.DBusCallFlags.NONE, -1, None,
        )
    except Exception:
        return []

    _serial, physical, logical, _props = res.unpack()

    # connector -> current (width_px, height_px)
    res_by_connector = {}
    for pm in physical:
        connector = pm[0][0]
        cur = _current_resolution(pm)
        if cur:
            res_by_connector[connector] = cur

    monitors = []
    for index, lm in enumerate(logical):
        # lm = (x, y, scale, transform, primary, [(connector, ...)], props)
        x, y, scale, _transform, primary, members, _lprops = lm
        connector = members[0][0] if members else f"monitor-{index}"
        phys = res_by_connector.get(connector)
        if phys:
            width = round(phys[0] / scale)
            height = round(phys[1] / scale)
        else:
            width, height = 0, 0
        monitors.append({
            "index": index,
            "connector": connector,
            "x": int(x),
            "y": int(y),
            "width": width,
            "height": height,
            "scale": round(scale, 4),
            "primary": bool(primary),
        })
    return monitors
