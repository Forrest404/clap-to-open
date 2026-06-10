"use strict";

const $ = (id) => document.getElementById(id);
const api = async (method, path, body) => {
  const opt = { method, headers: { "Content-Type": "application/json" } };
  if (body !== undefined) opt.body = JSON.stringify(body);
  const r = await fetch(path, opt);
  if (!r.ok) {
    let msg = `${path} -> ${r.status}`;
    try { const j = await r.json(); if (j && j.error) msg = j.error; } catch (_) {}
    throw new Error(msg);
  }
  return r.json();
};

let toastTimer;
function toast(msg) {
  const t = $("toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 2200);
}

// Debounced config save: collect the live form into the config shape and POST.
let saveTimer;
let cfg = null; // last loaded config, mutated in place by the form
let lastHotkey = { available: false, binding: "" };
function scheduleSave(msg) {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(async () => {
    cfg = await api("POST", "/api/config", cfg);
    if (msg) toast(msg);
  }, 350);
}

/* ---- Status / listening / autostart ---- */
function renderStatus(st) {
  const pill = $("statusPill");
  pill.dataset.on = st.listening;
  $("statusText").textContent = st.listening ? "Listening" : "Off";
  $("listenToggle").checked = st.listening;
  $("autostartToggle").checked = st.autostart;
  $("listenHint").textContent = st.listening
    ? "Mic is active — clap to launch your workspace."
    : "Turn the mic listener on to react to claps.";
}

async function pollStatus() {
  try { renderStatus(await api("GET", "/api/status")); } catch (_) {}
}

$("listenToggle").addEventListener("change", async (e) => {
  renderStatus(await api("POST", "/api/listening", { on: e.target.checked }));
  toast(e.target.checked ? "Listening on" : "Listening off");
});
$("autostartToggle").addEventListener("change", async (e) => {
  renderStatus(await api("POST", "/api/autostart", { on: e.target.checked }));
  toast(e.target.checked ? "Will start on login" : "Won't start on login");
});

/* ---- Sliders + segmented controls ---- */
function bindRange(id, group, key, valId, fmt) {
  const el = $(id);
  const valEl = valId ? $(valId) : null;
  el.addEventListener("input", () => {
    const v = parseFloat(el.value);
    cfg[group][key] = v;
    if (valEl) valEl.textContent = fmt ? fmt(v) : v;
    scheduleSave("Saved");
  });
  return el;
}

function setupSegmented(containerId, onPick) {
  const segs = [...$(containerId).querySelectorAll(".seg")];
  segs.forEach((b) =>
    b.addEventListener("click", () => {
      segs.forEach((s) => s.classList.toggle("active", s === b));
      onPick(b.dataset.val);
    })
  );
}
function markSegmented(containerId, val) {
  $(containerId).querySelectorAll(".seg").forEach((s) =>
    s.classList.toggle("active", s.dataset.val === String(val)));
}

/* ---- Sound mode panels ---- */
function showSoundPanels(mode) {
  document.querySelectorAll("[data-sound]").forEach((el) =>
    el.classList.toggle("show", el.dataset.sound === mode));
}

/* ====================== Workspace layout editor ====================== */
function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
// Minimal shlex.quote-style join so the server's shlex.split reverses it.
function shlexJoin(argv) {
  return (argv || []).map((a) =>
    /[\s"'\\]/.test(a) ? "'" + String(a).replace(/'/g, "'\\''") + "'" : a
  ).join(" ");
}

let LZ = { monitors: [], windows: [] };   // layout state (source of truth)
let view = { scale: 1, minX: 0, minY: 0 };
let layoutDirty = false;
let selectedId = null;
let appsCache = null;
let uid = 1;

function setLayoutDirty(d) { layoutDirty = d; $("dirtyTag").hidden = !d; }

function normalizeWin(w) {
  return {
    id: w.id != null ? "w" + (uid++) : "w" + (uid++),
    wm_class: w.wm_class || "",
    title: w.title || "",
    command: w.command != null ? w.command : shlexJoin(w.argv),
    run: w.run || "",
    x: w.x || 0, y: w.y || 0,
    width: w.width || 900, height: w.height || 650,
    monitor: w.monitor || 0,
    maximized: !!w.maximized,
    _name: w._name || w.title || w.wm_class || "window",
    _guessed: !!w._guessed,
  };
}

/* ---- coordinate transform (logical screen space <-> canvas pixels) ---- */
function computeView() {
  const map = $("screenMap");
  const availW = map.clientWidth || 600;
  const mons = LZ.monitors;
  if (!mons.length) { view = { scale: 0.25, minX: 0, minY: 0 }; map.style.height = "120px"; return; }
  const minX = Math.min(...mons.map((m) => m.x));
  const minY = Math.min(...mons.map((m) => m.y));
  const maxX = Math.max(...mons.map((m) => m.x + m.width));
  const maxY = Math.max(...mons.map((m) => m.y + m.height));
  const worldW = (maxX - minX) || 1, worldH = (maxY - minY) || 1;
  const scale = Math.min(availW / worldW, 320 / worldH);
  view = { scale, minX, minY };
  map.style.height = Math.ceil(worldH * scale) + "px";
}
const toPx = (lx, ly) => [(lx - view.minX) * view.scale, (ly - view.minY) * view.scale];
const toLogical = (px, py) => [Math.round(px / view.scale + view.minX), Math.round(py / view.scale + view.minY)];

function monitorAt(w) {
  const cx = w.x + w.width / 2, cy = w.y + w.height / 2;
  for (const m of LZ.monitors)
    if (cx >= m.x && cx < m.x + m.width && cy >= m.y && cy < m.y + m.height) return m.index;
  return w.monitor || 0;
}

/* ---- render ---- */
function renderAll() { renderMap(); renderPanels(); }

function renderMap() {
  computeView();
  const map = $("screenMap");
  map.innerHTML = "";
  for (const m of LZ.monitors) {
    const [px, py] = toPx(m.x, m.y);
    const d = document.createElement("div");
    d.className = "mon";
    d.style.left = px + "px"; d.style.top = py + "px";
    d.style.width = m.width * view.scale + "px";
    d.style.height = m.height * view.scale + "px";
    d.innerHTML = `<span class="mon-label">${escapeHtml(m.connector)}${m.primary ? " ★" : ""} · ${m.width}×${m.height}</span>`;
    map.appendChild(d);
  }
  for (const w of LZ.windows) map.appendChild(makeBlock(w));
}

function makeBlock(w) {
  const b = document.createElement("div");
  b.className = "win-block" + (w.id === selectedId ? " selected" : "") + (w.maximized ? " maximized" : "");
  b.dataset.id = w.id;
  positionBlock(b, w);
  b.innerHTML = `<span class="wb-label">${escapeHtml(w._name || w.wm_class || "window")}</span>` +
    ["nw", "ne", "sw", "se"].map((d) => `<span class="handle ${d}" data-dir="${d}"></span>`).join("");
  b.addEventListener("pointerdown", (e) => onBlockDown(e, w, b));
  return b;
}

function positionBlock(b, w) {
  let x = w.x, y = w.y, width = w.width, height = w.height;
  if (w.maximized) {
    const m = LZ.monitors.find((mm) => mm.index === w.monitor) || LZ.monitors[0];
    if (m) { x = m.x; y = m.y; width = m.width; height = m.height; }
  }
  const [px, py] = toPx(x, y);
  b.style.left = px + "px"; b.style.top = py + "px";
  b.style.width = Math.max(8, width * view.scale) + "px";
  b.style.height = Math.max(8, height * view.scale) + "px";
}

function reflectWindow(w) {
  const b = $("screenMap").querySelector(`.win-block[data-id="${w.id}"]`);
  if (b) { b.classList.toggle("maximized", !!w.maximized); positionBlock(b, w); }
}
function syncPanel(w) {
  const p = $("winPanels").querySelector(`.wpanel[data-id="${w.id}"]`);
  if (!p) return;
  ["x", "y", "width", "height"].forEach((f) => { const el = p.querySelector(`[data-f="${f}"]`); if (el) el.value = w[f]; });
  const ms = p.querySelector('[data-f="monitor"]'); if (ms) ms.value = w.monitor;
}

/* ---- drag + resize (Pointer Events) ---- */
function onBlockDown(e, w, b) {
  e.preventDefault();
  selectWindow(w.id);
  if (w.maximized) return;
  const dir = e.target.dataset.dir || "";
  const sx = e.clientX, sy = e.clientY;
  const o = { x: w.x, y: w.y, width: w.width, height: w.height };
  const SNAP = 12 / view.scale;
  b.setPointerCapture(e.pointerId);
  function move(ev) {
    const dlx = (ev.clientX - sx) / view.scale, dly = (ev.clientY - sy) / view.scale;
    if (!dir) {
      w.x = Math.round(o.x + dlx); w.y = Math.round(o.y + dly);
      snapWindow(w, SNAP);
    } else {
      if (dir.includes("e")) w.width = Math.max(200, Math.round(o.width + dlx));
      if (dir.includes("s")) w.height = Math.max(150, Math.round(o.height + dly));
      if (dir.includes("w")) { const nw = Math.max(200, Math.round(o.width - dlx)); w.x = Math.round(o.x + (o.width - nw)); w.width = nw; }
      if (dir.includes("n")) { const nh = Math.max(150, Math.round(o.height - dly)); w.y = Math.round(o.y + (o.height - nh)); w.height = nh; }
    }
    w.monitor = monitorAt(w);
    positionBlock(b, w); syncPanel(w); setLayoutDirty(true);
  }
  function up() { b.removeEventListener("pointermove", move); b.removeEventListener("pointerup", up); }
  b.addEventListener("pointermove", move);
  b.addEventListener("pointerup", up);
}

function snapWindow(w, SNAP) {
  for (const m of LZ.monitors) {
    for (const ex of [m.x, m.x + m.width]) {
      if (Math.abs(w.x - ex) < SNAP) w.x = ex;
      if (Math.abs(w.x + w.width - ex) < SNAP) w.x = ex - w.width;
    }
    for (const ey of [m.y, m.y + m.height]) {
      if (Math.abs(w.y - ey) < SNAP) w.y = ey;
      if (Math.abs(w.y + w.height - ey) < SNAP) w.y = ey - w.height;
    }
  }
}

/* ---- per-window panels ---- */
function renderPanels() {
  const root = $("winPanels");
  root.innerHTML = "";
  if (!LZ.windows.length) {
    root.innerHTML = `<p class="muted">No windows yet — use “＋ Add app” or “Capture current”.</p>`;
  } else {
    LZ.windows.forEach((w) => root.appendChild(makePanel(w)));
  }
  const n = LZ.windows.length;
  $("layoutSummary").textContent = n
    ? `${n} window${n > 1 ? "s" : ""} — drag to arrange, then Save layout.`
    : "Pick which apps open and drag them where you want.";
}

function makePanel(w) {
  const p = document.createElement("div");
  p.className = "wpanel" + (w.id === selectedId ? " selected" : "");
  p.dataset.id = w.id;
  const monOpts = LZ.monitors.map((m) =>
    `<option value="${m.index}" ${m.index === w.monitor ? "selected" : ""}>${escapeHtml(m.connector)}</option>`).join("");
  const tag = !w.wm_class ? `<span class="warn-tag">no class · won't place</span>`
    : w._guessed ? `<span class="warn-tag" title="Guessed — edit if placement fails">guessed</span>` : "";
  p.innerHTML = `
    <div class="wpanel-head">
      <span class="wb-dot"></span>
      <input class="wp-name" data-f="_name" value="${escapeHtml(w._name || w.wm_class || "window")}">
      <button class="icon-btn wp-del" title="Remove">🗑</button>
    </div>
    <label class="wp-row">Command
      <input data-f="command" value="${escapeHtml(w.command || "")}"></label>
    <label class="wp-row">Run in terminal <span class="wp-hint">optional — e.g. claude</span>
      <input data-f="run" value="${escapeHtml(w.run || "")}" placeholder="command to run inside this terminal"></label>
    <label class="wp-row">Window class ${tag}
      <input data-f="wm_class" value="${escapeHtml(w.wm_class || "")}"></label>
    <div class="wp-grid">
      <label>Monitor<select data-f="monitor">${monOpts}</select></label>
      <label class="wp-max"><input type="checkbox" data-f="maximized" ${w.maximized ? "checked" : ""}> Maximize</label>
      <label>X<input type="number" data-f="x" value="${w.x}"></label>
      <label>Y<input type="number" data-f="y" value="${w.y}"></label>
      <label>W<input type="number" data-f="width" value="${w.width}"></label>
      <label>H<input type="number" data-f="height" value="${w.height}"></label>
    </div>`;
  p.querySelectorAll("[data-f]").forEach((el) => {
    const f = el.dataset.f;
    const evt = (el.type === "checkbox" || el.tagName === "SELECT") ? "change" : "input";
    el.addEventListener(evt, () => {
      if (el.type === "checkbox") w[f] = el.checked;
      else if (el.type === "number") w[f] = parseInt(el.value || "0", 10);
      else if (f === "monitor") { w.monitor = parseInt(el.value, 10); snapIntoMonitor(w); syncPanel(w); }
      else w[f] = el.value;
      if (f === "wm_class") w._guessed = false;
      setLayoutDirty(true);
      reflectWindow(w);
      if (f === "_name") { const b = $("screenMap").querySelector(`.win-block[data-id="${w.id}"] .wb-label`); if (b) b.textContent = w._name; }
    });
  });
  p.querySelector(".wp-del").addEventListener("click", () => {
    LZ.windows = LZ.windows.filter((x) => x !== w);
    if (selectedId === w.id) selectedId = null;
    setLayoutDirty(true); renderAll();
  });
  p.querySelector(".wpanel-head").addEventListener("click", (e) => {
    if (!e.target.closest("button, input")) selectWindow(w.id);
  });
  return p;
}

function snapIntoMonitor(w) {
  const m = LZ.monitors.find((mm) => mm.index === w.monitor);
  if (!m) return;
  if (w.x < m.x || w.x + w.width > m.x + m.width || w.y < m.y || w.y + w.height > m.y + m.height) {
    w.width = Math.min(w.width, m.width);
    w.height = Math.min(w.height, m.height);
    w.x = m.x + Math.max(0, Math.round((m.width - w.width) / 2));
    w.y = m.y + Math.max(0, Math.round((m.height - w.height) / 2));
  }
}

function selectWindow(id) {
  selectedId = id;
  $("screenMap").querySelectorAll(".win-block").forEach((b) => b.classList.toggle("selected", b.dataset.id === id));
  $("winPanels").querySelectorAll(".wpanel").forEach((p) => p.classList.toggle("selected", p.dataset.id === id));
}

/* ---- load / save / capture / clear / boot ---- */
async function loadLayout() {
  const data = await api("GET", "/api/layout");
  LZ.monitors = data.monitors || [];
  LZ.windows = (data.windows || []).map(normalizeWin);
  selectedId = null; setLayoutDirty(false); renderAll();
}

function payloadFromState() {
  return {
    windows: LZ.windows.map((w) => ({
      wm_class: w.wm_class, title: w.title || "", command: w.command,
      run: w.run || "",
      x: w.x, y: w.y, width: w.width, height: w.height,
      monitor: w.monitor, maximized: w.maximized,
    })),
  };
}

async function saveLayout() {
  try {
    const res = await api("POST", "/api/layout", payloadFromState());
    LZ.monitors = res.monitors || LZ.monitors;
    LZ.windows = (res.windows || []).map(normalizeWin);
    selectedId = null; setLayoutDirty(false); renderAll();
    toast("Layout saved");
  } catch (e) { toast("Save failed: " + e.message); }
}

function placeNew(w) {
  const m = LZ.monitors.find((mm) => mm.primary) || LZ.monitors[0] || { x: 0, y: 0, width: 1280, height: 800, index: 0 };
  w.width = Math.min(w.width || 900, Math.round(m.width * 0.6));
  w.height = Math.min(w.height || 650, Math.round(m.height * 0.6));
  w.x = m.x + Math.round((m.width - w.width) / 2);
  w.y = m.y + Math.round((m.height - w.height) / 2);
  w.monitor = m.index;
}

$("saveLayoutBtn").addEventListener("click", saveLayout);
$("captureBtn").addEventListener("click", async () => {
  if (layoutDirty && !confirm("Capture replaces the editor with your CURRENT windows. Discard unsaved edits?")) return;
  const res = await api("POST", "/api/layout/capture");
  LZ.monitors = res.monitors || LZ.monitors;
  LZ.windows = (res.windows || []).map(normalizeWin);
  selectedId = null; setLayoutDirty(false); renderAll();
  toast("Captured current windows");
});
$("clearBtn").addEventListener("click", async () => {
  if (!confirm("Clear the whole layout?")) return;
  await api("POST", "/api/layout/clear");
  LZ.windows = []; selectedId = null; setLayoutDirty(false); renderAll();
  toast("Layout cleared");
});
$("testBoot").addEventListener("click", async () => {
  await api("POST", "/api/test-boot");
  toast(layoutDirty ? "Boot replays the SAVED layout — Save first" : "Replaying layout…");
});

/* ---- add-app modal (installed / open windows / manual) ---- */
let addSource = "installed";
function openAdd() { $("addModal").hidden = false; $("addSearch").value = ""; if (addSource !== "manual") renderAddList(); }
function closeAdd() { $("addModal").hidden = true; }
$("addAppBtn").addEventListener("click", openAdd);
$("addClose").addEventListener("click", closeAdd);
$("addModal").addEventListener("click", (e) => { if (e.target.id === "addModal") closeAdd(); });
$("addSearch").addEventListener("input", renderAddList);

async function renderAddList() {
  const list = $("addList");
  const q = $("addSearch").value.toLowerCase();
  let items = [];
  if (addSource === "installed") {
    if (!appsCache) appsCache = await api("GET", "/api/apps");
    items = appsCache
      .filter((a) => a.name.toLowerCase().includes(q))
      .map((a) => ({ name: a.name, exec: a.exec, wm_class: a.wm_class, guessed: a.wm_class_guessed }));
  } else if (addSource === "open") {
    const ws = await api("GET", "/api/windows/open");
    items = ws
      .filter((w) => (w.wm_class || "").toLowerCase().includes(q) || (w.title || "").toLowerCase().includes(q))
      .map((w) => ({ name: w.title || w.wm_class, win: w }));
  }
  list.innerHTML = items.slice(0, 300).map((it, i) =>
    `<button class="add-item" data-i="${i}"><span class="ai-mono">${escapeHtml((it.name || "?").trim()[0] || "?").toUpperCase()}</span>` +
    `<span class="ai-name">${escapeHtml(it.name || "?")}</span></button>`).join("")
    || `<p class="muted">No matches.</p>`;
  list.querySelectorAll(".add-item").forEach((el) =>
    el.addEventListener("click", () => addFromItem(items[+el.dataset.i])));
}

function addFromItem(it) {
  let w;
  if (it.win) {
    w = normalizeWin({ ...it.win, command: shlexJoin(it.win.argv) });
  } else {
    w = normalizeWin({ wm_class: it.wm_class, command: shlexJoin(it.exec), _name: it.name, _guessed: it.guessed });
    placeNew(w);
  }
  LZ.windows.push(w);
  selectedId = w.id; setLayoutDirty(true); closeAdd(); renderAll();
  toast(`Added ${w._name}`);
}

$("manualAdd").addEventListener("click", () => {
  const name = $("manualName").value.trim();
  const cmd = $("manualCmd").value.trim();
  const cls = $("manualClass").value.trim();
  if (!cmd) { toast("Enter a command"); return; }
  const w = normalizeWin({ wm_class: cls, command: cmd, _name: name || cls || "app" });
  placeNew(w);
  LZ.windows.push(w);
  selectedId = w.id; setLayoutDirty(true);
  $("manualName").value = $("manualCmd").value = $("manualClass").value = "";
  closeAdd(); renderAll();
  toast(`Added ${w._name}`);
});

// Re-fit the canvas when the window resizes.
let _rsT;
window.addEventListener("resize", () => {
  clearTimeout(_rsT);
  _rsT = setTimeout(() => { if (LZ.monitors.length) renderMap(); }, 150);
});
$("testSound").addEventListener("click", async () => {
  await api("POST", "/api/test-sound");
  toast("Playing sound…");
});

/* ---- Toggle shortcut (GNOME global hotkey) ---- */
function renderHotkey(st) {
  const btn = $("hotkeyBtn"), clear = $("hotkeyClear");
  if (!st.available) {
    btn.disabled = true;
    btn.textContent = "Unavailable";
    $("hotkeyHint").textContent = "Global shortcuts need GNOME (gsettings).";
    return;
  }
  btn.textContent = st.binding ? prettyAccel(st.binding) : "Set shortcut";
  clear.hidden = !st.binding;
}
// "<Super><Alt>j" -> "Super + Alt + J" for display
function prettyAccel(a) {
  const mods = (a.match(/<[^>]+>/g) || [])
    .map((m) => m.slice(1, -1).replace("Primary", "Ctrl").replace("Control", "Ctrl"));
  const key = a.replace(/<[^>]+>/g, "");
  return [...mods, key.length === 1 ? key.toUpperCase() : key].join(" + ");
}
// Build a GNOME accelerator from a keydown event.
const KEYMAP = { " ": "space", Escape: "Escape", Enter: "Return", Tab: "Tab",
  Backspace: "BackSpace", Delete: "Delete", ArrowUp: "Up", ArrowDown: "Down",
  ArrowLeft: "Left", ArrowRight: "Right" };
const MODS = new Set(["Control", "Alt", "Shift", "Meta", "Super"]);
function eventToAccel(e) {
  if (MODS.has(e.key)) return null;           // a modifier alone — keep waiting
  let key;
  if (KEYMAP[e.key]) key = KEYMAP[e.key];
  else if (/^F\d{1,2}$/.test(e.key)) key = e.key;
  else if (e.key.length === 1) key = e.key.toLowerCase();
  else return null;
  const mods = [];
  if (e.ctrlKey) mods.push("<Control>");
  if (e.altKey) mods.push("<Alt>");
  if (e.shiftKey) mods.push("<Shift>");
  if (e.metaKey) mods.push("<Super>");
  // Require a modifier for letters/digits so we don't hijack plain typing.
  if (!mods.length && !/^F\d/.test(key)) return "NEED_MOD";
  return mods.join("") + key;
}
let capturing = false;
function captureKey(e) {
  if (!capturing) return;
  e.preventDefault();
  const accel = eventToAccel(e);
  if (accel === null) return;                 // modifier-only, keep listening
  stopCapture();
  if (accel === "NEED_MOD") { toast("Use a modifier (Ctrl/Alt/Super)"); return; }
  api("POST", "/api/hotkey", { accel }).then((st) => {
    lastHotkey = st;
    renderHotkey(st);
    toast(st.ok ? "Shortcut set: " + prettyAccel(accel) : (st.error || "Failed"));
  });
}
function stopCapture() {
  capturing = false;
  $("hotkeyBtn").classList.remove("capturing");
  document.removeEventListener("keydown", captureKey, true);
}
$("hotkeyBtn").addEventListener("click", () => {
  if ($("hotkeyBtn").disabled) return;
  if (capturing) { stopCapture(); renderHotkey(lastHotkey); return; }
  capturing = true;
  $("hotkeyBtn").classList.add("capturing");
  $("hotkeyBtn").textContent = "Press keys…";
  document.addEventListener("keydown", captureKey, true);
});
$("hotkeyClear").addEventListener("click", async () => {
  lastHotkey = await api("DELETE", "/api/hotkey");
  renderHotkey(lastHotkey);
  toast("Shortcut cleared");
});

/* ---- Reset settings ---- */
$("resetBtn").addEventListener("click", async () => {
  if (!confirm("Reset sensitivity, trigger, sound and pre-launch to defaults?")) return;
  cfg = await api("POST", "/api/config/reset");
  applyConfig();
  toast("Settings reset to defaults");
});

/* ---- Init ---- */
function applyConfig() {
  const s = cfg.sensitivity, t = cfg.trigger, snd = cfg.sound;
  const set = (id, v, valId, fmt) => {
    $(id).value = v;
    if (valId && $(valId)) $(valId).textContent = fmt ? fmt(v) : v;
  };
  set("threshold_bias", s.threshold_bias, "thresholdVal");
  set("initial_volume_threshold", s.initial_volume_threshold, "initVolVal");
  set("lowcut", s.lowcut, "lowcutVal");
  set("highcut", s.highcut, "highcutVal");
  set("reset_time", s.reset_time, "resetVal", (v) => v + "s");
  set("cooldown", t.cooldown_seconds, "cooldownVal", (v) => v + "s");
  markSegmented("clapCount", t.clap_count);
  markSegmented("soundMode", snd.mode);
  showSoundPanels(snd.mode);
  $("soundFile").value = snd.file || "";
  $("soundUrl").value = snd.url || "";
  $("preLaunch").value = cfg.boot.pre_launch_command || "";
}

async function init() {
  cfg = await api("GET", "/api/config");
  applyConfig();

  bindRange("threshold_bias", "sensitivity", "threshold_bias", "thresholdVal");
  bindRange("initial_volume_threshold", "sensitivity", "initial_volume_threshold", "initVolVal");
  bindRange("lowcut", "sensitivity", "lowcut", "lowcutVal");
  bindRange("highcut", "sensitivity", "highcut", "highcutVal");
  bindRange("reset_time", "sensitivity", "reset_time", "resetVal", (v) => v + "s");
  bindRange("cooldown", "trigger", "cooldown_seconds", "cooldownVal", (v) => v + "s");

  setupSegmented("clapCount", (v) => {
    cfg.trigger.clap_count = parseInt(v, 10);
    scheduleSave("Trigger updated");
  });
  setupSegmented("soundMode", (v) => {
    cfg.sound.mode = v;
    showSoundPanels(v);
    scheduleSave("Sound updated");
  });
  $("soundFile").addEventListener("input", (e) => {
    cfg.sound.file = e.target.value; scheduleSave();
  });
  $("soundUrl").addEventListener("input", (e) => {
    cfg.sound.url = e.target.value; scheduleSave();
  });
  $("preLaunch").addEventListener("input", (e) => {
    cfg.boot.pre_launch_command = e.target.value; scheduleSave();
  });

  lastHotkey = await api("GET", "/api/hotkey");
  renderHotkey(lastHotkey);

  setupSegmented("addSource", (v) => {
    addSource = v;
    $("addManual").hidden = v !== "manual";
    $("addList").hidden = v === "manual";
    $("addSearch").hidden = v === "manual";
    if (v !== "manual") renderAddList();
  });
  await loadLayout();

  await pollStatus();
  setInterval(pollStatus, 2000);

  await maybeOnboard();
}

/* ====================== First-run onboarding wizard ====================== */
async function obWelcome(body) {
  body.innerHTML = `
    <div class="ob-hero">👏</div>
    <h2>Welcome to Clap to Open</h2>
    <p class="muted">Clap into your mic and your whole workspace springs to life —
      every app relaunched and snapped to the right size and monitor.
      Let's set it up in about a minute.</p>`;
  return { nextLabel: "Let's go" };
}

async function obCheck(body) {
  body.innerHTML = `
    <h2>Quick system check</h2>
    <p class="muted">Making sure everything Clap to Open needs is in place.</p>
    <div class="ob-checks" id="obChecks">Checking…</div>
    <button class="btn ghost" id="obRecheck">Re-check</button>`;
  const render = async () => {
    const checks = await api("GET", "/api/doctor");
    const icon = { ok: "✓", warn: "!", bad: "✕" };
    $("obChecks").innerHTML = checks.map((c) =>
      `<div class="ob-check ob-${c.status}"><span class="obc-i">${icon[c.status]}</span>` +
      `<span><b>${escapeHtml(c.label)}</b>` +
      (c.hint ? `<br><span class="muted">${escapeHtml(c.hint)}</span>` : "") +
      `</span></div>`).join("");
  };
  await render();
  $("obRecheck").addEventListener("click", render);
  return {};
}

async function obCapture(body) {
  body.innerHTML = `
    <h2>Capture your workspace</h2>
    <p class="muted">Open and arrange the apps you want — drag them to the right
      monitors and size them how you like. Then capture the layout. You can
      fine-tune it any time in the editor.</p>
    <button class="btn" id="obCaptureBtn">⛶ Capture current windows</button>
    <p class="ob-result" id="obCapResult"></p>`;
  $("obCaptureBtn").addEventListener("click", async () => {
    const res = await api("POST", "/api/layout/capture");
    if (res.count) {
      LZ.monitors = res.monitors || LZ.monitors;
      LZ.windows = (res.windows || []).map(normalizeWin);
      renderAll();
      $("obCapResult").textContent = `✓ Saved ${res.count} window${res.count > 1 ? "s" : ""}.`;
    } else {
      $("obCapResult").textContent = "No windows found — open some apps and try again.";
    }
  });
  return {};
}

async function obListen(body) {
  const cc = cfg.trigger.clap_count;
  body.innerHTML = `
    <h2>Turn on listening</h2>
    <p class="muted">Pick your trigger, switch listening on, then clap to test —
      your saved layout will spring open.</p>
    <div class="segmented ob-clap" id="obClap">
      <button data-val="2" class="seg ${cc === 2 ? "active" : ""}">Double clap</button>
      <button data-val="3" class="seg ${cc === 3 ? "active" : ""}">Triple clap</button>
    </div>
    <button class="btn ob-listen" id="obListenBtn">Turn on listening</button>
    <button class="btn ghost" id="obTestBoot">▶ Preview without clapping</button>
    <p class="ob-result muted" id="obListenResult"></p>`;
  const refresh = async () => {
    const st = await api("GET", "/api/status");
    const b = $("obListenBtn");
    b.textContent = st.listening ? "● Listening — clap to test!" : "Turn on listening";
    b.classList.toggle("on", st.listening);
  };
  await refresh();
  setupSegmented("obClap", async (v) => {
    cfg.trigger.clap_count = parseInt(v, 10);
    await api("POST", "/api/config", cfg);
    markSegmented("clapCount", cfg.trigger.clap_count);
  });
  $("obListenBtn").addEventListener("click", async () => {
    const st = await api("GET", "/api/status");
    await api("POST", "/api/listening", { on: !st.listening });
    await refresh();
  });
  $("obTestBoot").addEventListener("click", async () => {
    await api("POST", "/api/test-boot");
    toast("Replaying your layout…");
  });
  return { nextLabel: "Finish" };
}

const OB_STEPS = [obWelcome, obCheck, obCapture, obListen];
let obStep = 0;
let obMeta = {};

function obRenderDots() {
  $("obDots").innerHTML = OB_STEPS.map((_, i) =>
    `<span class="ob-dot${i === obStep ? " active" : ""}${i < obStep ? " done" : ""}"></span>`
  ).join("");
}
async function obRender() {
  obRenderDots();
  obMeta = (await OB_STEPS[obStep]($("obBody"))) || {};
  $("obBack").hidden = obStep === 0;
  $("obNext").textContent = obMeta.nextLabel ||
    (obStep === OB_STEPS.length - 1 ? "Finish" : "Next");
}
async function obFinish() {
  await api("POST", "/api/onboarded", { done: true });
  $("onboard").hidden = true;
  cfg = await api("GET", "/api/config");
  applyConfig();
  await loadLayout();
  await pollStatus();
  toast("You're all set — clap away! 👏");
}
$("obNext").addEventListener("click", async () => {
  if (obStep < OB_STEPS.length - 1) { obStep++; await obRender(); }
  else { await obFinish(); }
});
$("obBack").addEventListener("click", async () => {
  if (obStep > 0) { obStep--; await obRender(); }
});
$("obSkip").addEventListener("click", async () => {
  await api("POST", "/api/onboarded", { done: true });
  $("onboard").hidden = true;
});

async function maybeOnboard() {
  if (cfg && !cfg.onboarded) {
    obStep = 0;
    $("onboard").hidden = false;
    await obRender();
  }
}

init().catch((e) => toast("Error: " + e.message));
