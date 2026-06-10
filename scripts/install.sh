#!/usr/bin/env bash
# Install Clap to Open into this checkout: create a self-contained venv, install
# the package + dependencies, render the systemd user service and desktop
# launcher, and seed config. Safe to re-run (idempotent).
set -euo pipefail

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$PROJECT/venv"
SYSTEMD_DIR="$HOME/.config/systemd/user"
APPS_DIR="$HOME/.local/share/applications"
SERVICE="clap-to-open.service"

# ---- pretty output -----------------------------------------------------------
if [ -t 1 ]; then B=$'\e[1m'; G=$'\e[32m'; Y=$'\e[33m'; R=$'\e[31m'; N=$'\e[0m'
else B=; G=; Y=; R=; N=; fi
say()  { echo "${B}${G}==>${N} $*"; }
warn() { echo "${Y}!  $*${N}"; }
err()  { echo "${R}✗  $*${N}" >&2; }

# ---- detect the package manager (for dependency hints / auto-install) --------
PM=""; INSTALL=""; PORTAUDIO_PKG=""; VENV_PKG=""
if   command -v dnf     >/dev/null; then PM=dnf;    INSTALL="sudo dnf install -y";        PORTAUDIO_PKG="portaudio-devel";  VENV_PKG="python3";
elif command -v apt-get >/dev/null; then PM=apt;    INSTALL="sudo apt-get install -y";    PORTAUDIO_PKG="portaudio19-dev";  VENV_PKG="python3-venv";
elif command -v pacman  >/dev/null; then PM=pacman; INSTALL="sudo pacman -S --noconfirm"; PORTAUDIO_PKG="portaudio";        VENV_PKG="python";
elif command -v zypper  >/dev/null; then PM=zypper; INSTALL="sudo zypper install -y";     PORTAUDIO_PKG="portaudio-devel";  VENV_PKG="python3";
fi

maybe_install() {  # $1 = package, $2 = human description
  [ -n "$INSTALL" ] || { warn "Install $2 manually, then re-run."; return 1; }
  if [ -t 0 ]; then
    read -rp "   Install $2 with: $INSTALL $1 ? [Y/n] " ans
    case "${ans:-Y}" in [Nn]*) return 1;; esac
    $INSTALL "$1"
  else
    warn "Missing $2. Install it with: $INSTALL $1"; return 1
  fi
}

say "Project: $PROJECT  (distro pkg manager: ${PM:-unknown})"

# ---- 1. Python + venv module -------------------------------------------------
command -v python3 >/dev/null || { err "python3 not found."; exit 1; }
if ! python3 -m venv --help >/dev/null 2>&1; then
  warn "The Python 'venv' module is missing."
  maybe_install "$VENV_PKG" "the Python venv module" || { err "Cannot continue without venv."; exit 1; }
fi

# ---- 2. Self-contained venv + package ---------------------------------------
# --system-site-packages so we can import the system PyGObject (gi) for the
# monitor layout (Mutter DisplayConfig) and app picker. PyGObject ships with
# GNOME and isn't pip-installable cleanly, so we borrow it from the system.
[ -d "$VENV" ] || { say "Creating venv at $VENV"; python3 -m venv --system-site-packages "$VENV"; }
"$VENV/bin/pip" install --upgrade pip >/dev/null

say "Installing the package + dependencies"
if ! "$VENV/bin/pip" install -e "$PROJECT"; then
  warn "Install failed — PyAudio usually needs PortAudio development headers."
  if maybe_install "$PORTAUDIO_PKG" "PortAudio headers (for PyAudio)"; then
    "$VENV/bin/pip" install -e "$PROJECT"
  else
    err "Could not install dependencies."; exit 1
  fi
fi

# ---- 3. Default startup sound -----------------------------------------------
SOUND="$PROJECT/data/sounds/boot.ogg"
if [ ! -f "$SOUND" ]; then
  for cand in /usr/share/sounds/freedesktop/stereo/complete.oga \
              /usr/share/sounds/freedesktop/stereo/bell.oga; do
    [ -f "$cand" ] && { cp "$cand" "$SOUND"; say "Seeded default sound from $cand"; break; }
  done
fi

# ---- 4. Migrate a layout.json from the legacy location, if any --------------
OLD_LAYOUT="$HOME/.local/share/clap-trigger/layout.json"
if [ -f "$OLD_LAYOUT" ] && [ ! -f "$PROJECT/layout.json" ]; then
  cp "$OLD_LAYOUT" "$PROJECT/layout.json"; say "Migrated existing layout.json"
fi

# ---- 5. systemd user service -------------------------------------------------
mkdir -p "$SYSTEMD_DIR"
sed "s#@PROJECT@#$PROJECT#g" "$PROJECT/systemd/clap-to-open.service.in" > "$SYSTEMD_DIR/$SERVICE"
systemctl --user daemon-reload 2>/dev/null || warn "systemctl --user unavailable (no graphical session?)"
say "Installed $SERVICE (not started — turn it on from the UI or 'clap ctl on')"

# ---- 6. Desktop launcher -----------------------------------------------------
mkdir -p "$APPS_DIR"
sed "s#@PROJECT@#$PROJECT#g" "$PROJECT/data/clap-to-open.desktop.in" > "$APPS_DIR/clap-to-open.desktop"
say "Installed 'Clap to Open' app launcher"

# ---- 7. Seed config.json -----------------------------------------------------
"$VENV/bin/clap" ctl status >/dev/null 2>&1 || true

# ---- 8. Environment sanity checks (warnings only) ---------------------------
echo
[ "${XDG_SESSION_TYPE:-}" = "wayland" ] || warn "Not a Wayland session — window placement uses GNOME window-calls and is tuned for Wayland."
if command -v gnome-extensions >/dev/null; then
  if ! gnome-extensions list 2>/dev/null | grep -q window-calls; then
    warn "GNOME 'window-calls' extension not found — required to place windows."
    warn "  Install it: https://extensions.gnome.org/extension/4724/window-calls/"
  fi
else
  warn "gnome-extensions not found — this tool targets GNOME. Window placement needs the 'window-calls' extension."
fi
command -v paplay >/dev/null || command -v ffplay >/dev/null || \
  warn "Neither paplay nor ffplay found — the local startup sound won't play."

cat <<EOF

${B}${G}Done!${N}  Next steps:
  • Open the control panel:   ${B}$VENV/bin/clap serve${N}
  • Or launch ${B}Clap to Open${N} from your applications.
  • Capture a layout, tune sensitivity, then switch Listening on.

  Tip: add ${B}$VENV/bin${N} to your PATH to just run ${B}clap${N}.
  Tip: bind a GNOME shortcut to ${B}$VENV/bin/clap ctl toggle${N}.
EOF
