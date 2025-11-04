#!/usr/bin/env bash
set -euo pipefail

# Install or update the Pecunia env drift systemd timer.
# Run as root (or with sudo) on the target host.

SERVICE_NAME="pecunia-env-check"
SYSTEMD_DIR="/etc/systemd/system"
WORKDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

copy_unit() {
  local src="$1"
  local dest="$SYSTEMD_DIR/$(basename "$src")"
  if [[ ! -f "$src" ]]; then
    echo "Missing source file: $src" >&2
    exit 1
  fi
  echo "Installing $(basename "$src") → $dest"
  install -m 0644 "$src" "$dest"
}

echo "Installing $SERVICE_NAME systemd unit and timer..."
copy_unit "$WORKDIR/infra/systemd/${SERVICE_NAME}.service"
copy_unit "$WORKDIR/infra/systemd/${SERVICE_NAME}.timer"

echo "Reloading systemd daemon..."
systemctl daemon-reload

echo "Enabling and starting timer..."
systemctl enable "${SERVICE_NAME}.timer"
systemctl start "${SERVICE_NAME}.timer"

echo "Timer status:"
systemctl status "${SERVICE_NAME}.timer" --no-pager
