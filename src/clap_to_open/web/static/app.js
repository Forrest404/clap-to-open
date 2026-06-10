"use strict";

const $ = (id) => document.getElementById(id);
const api = async (method, path, body) => {
  const opt = { method, headers: { "Content-Type": "application/json" } };
  if (body !== undefined) opt.body = JSON.stringify(body);
  const r = await fetch(path, opt);
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
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

/* ---- Layout ---- */
function renderLayout(data) {
  $("layoutSummary").textContent = data.count
    ? `${data.count} window${data.count > 1 ? "s" : ""} saved.`
    : "No layout captured.";
  $("winList").innerHTML = data.windows.map((w) =>
    `<li><span class="wclass">${escapeHtml(w.wm_class || "?")}</span>` +
    `<span class="geo">mon ${w.monitor} · ${escapeHtml(w.geometry)}</span></li>`
  ).join("");
}
function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

$("captureBtn").addEventListener("click", async () => {
  renderLayout(await api("POST", "/api/layout/capture"));
  toast("Captured current layout");
});
$("clearBtn").addEventListener("click", async () => {
  renderLayout(await api("POST", "/api/layout/clear"));
  toast("Layout cleared");
});
$("testBoot").addEventListener("click", async () => {
  await api("POST", "/api/test-boot");
  toast("Replaying layout…");
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

  await pollStatus();
  setInterval(pollStatus, 2000);
}

init().catch((e) => toast("Error: " + e.message));
