#!/usr/bin/env bash
# Remove the systemd unit and desktop launcher. Leaves the project folder, venv
# and config.json in place (delete the folder yourself to fully remove).
set -euo pipefail

SYSTEMD_DIR="$HOME/.config/systemd/user"
APPS_DIR="$HOME/.local/share/applications"
SERVICE="clap-to-open.service"

systemctl --user stop "$SERVICE" 2>/dev/null || true
systemctl --user disable "$SERVICE" 2>/dev/null || true
rm -f "$SYSTEMD_DIR/$SERVICE"
rm -f "$APPS_DIR/clap-to-open.desktop"
systemctl --user daemon-reload

echo "Removed $SERVICE and the app launcher."
echo "The project folder, venv and config.json were left untouched."
