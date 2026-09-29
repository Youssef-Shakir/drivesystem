#!/usr/bin/env bash
#
# Drive-Thru Intercom System - Uninstaller
# ===========================================
# Removes the systemd service and deployed PipeWire/WirePlumber configs.
# Does NOT delete the repo itself, config.yaml, or recordings/logs - it
# only undoes what install.sh set up outside the repo. Run as your
# normal user (not root) from anywhere; it calls sudo itself where needed.
#
# Usage: bash scripts/uninstall.sh

set -euo pipefail

if [ "$(id -u)" -eq 0 ]; then
    echo "Run this as your normal user, not root/sudo." >&2
    exit 1
fi

echo "=== Drive-Thru Intercom Uninstaller ==="
echo "This removes the systemd service and deployed PipeWire configs."
echo "Your repo, config.yaml, recordings, and logs are left untouched."
echo
read -p "Continue? [y/N] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

echo
echo "[1/3] Stopping and removing systemd services..."
systemctl --user stop drivethru.service 2>/dev/null || true
systemctl --user disable drivethru.service 2>/dev/null || true
systemctl --user stop drivethru-gui.service 2>/dev/null || true
systemctl --user disable drivethru-gui.service 2>/dev/null || true
rm -f ~/.config/systemd/user/drivethru.service
rm -f ~/.config/systemd/user/drivethru-gui.service
systemctl --user daemon-reload

echo "[2/3] Removing deployed PipeWire/WirePlumber configs..."
rm -f ~/.config/pipewire/pipewire.conf.d/97-drivethru-deepfilter.conf
rm -f ~/.config/pipewire/pipewire.conf.d/99-drivethru-aec.conf
rm -f ~/.config/wireplumber/wireplumber.conf.d/99-drivethru-bluetooth.conf

echo "[3/3] Restarting PipeWire to drop the removed configs..."
systemctl --user restart pipewire pipewire-pulse wireplumber

echo
echo "=== Uninstall complete ==="
echo "Still on disk (delete manually if you want them gone too):"
echo "  - This repo directory"
echo "  - config.yaml (has your PIN and device settings)"
echo "  - recordings/, logs/, drivethru.db"
echo
echo "fail2ban/ufw changes from scripts/harden.sh (if you ran it) are NOT"
echo "undone by this script - they're host-level, not app-level."
