#!/usr/bin/env bash
# One-command installer for Clap to Open.
#
#   curl -fsSL https://raw.githubusercontent.com/Forrest404/clap-to-open/main/scripts/bootstrap.sh | bash
#
# Clones (or updates) the repo into ~/.local/share/clap-to-open and runs the
# installer. Override the location with CLAP_DIR=/some/path.
set -euo pipefail

REPO="https://github.com/Forrest404/clap-to-open.git"
DIR="${CLAP_DIR:-$HOME/.local/share/clap-to-open}"

command -v git >/dev/null || { echo "git is required. Install git and retry." >&2; exit 1; }

if [ -d "$DIR/.git" ]; then
  echo "==> Updating existing checkout at $DIR"
  git -C "$DIR" pull --ff-only
else
  echo "==> Cloning $REPO -> $DIR"
  mkdir -p "$(dirname "$DIR")"
  git clone --depth 1 "$REPO" "$DIR"
fi

exec bash "$DIR/scripts/install.sh"
