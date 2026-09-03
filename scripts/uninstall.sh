#!/bin/bash
#
# Drive-Thru Intercom System Uninstaller
#
set -e

INSTALL_DIR="/opt/drivethru"

echo "=== Drive-Thru Intercom Uninstaller ==="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: Please run with sudo"
    exit 1
fi

# Confirmation
read -p "This will remove all Drive-Thru Intercom files. Continue? [y/N] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Uninstall cancelled."
    exit 0
fi

echo ""
echo "[1/5] Stopping services..."
systemctl stop drivethru-server.service 2>/dev/null || true
systemctl disable drivethru-server.service 2>/dev/null || true
rm -f /etc/systemd/system/drivethru-server.service 2>/dev/null || true
systemctl daemon-reload

echo "[2/5] Removing user service..."
REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)
rm -f "$REAL_HOME/.config/systemd/user/drivethru.service" 2>/dev/null || true

echo "[3/5] Removing PipeWire configuration..."
rm -f "$REAL_HOME/.config/pipewire/pipewire.conf.d/99-drivethru-aec.conf" 2>/dev/null || true
rm -f "$REAL_HOME/.config/wireplumber/wireplumber.conf.d/99-drivethru-bluetooth.conf" 2>/dev/null || true

echo "[4/5] Removing autostart entry..."
rm -f "$REAL_HOME/.config/autostart/drivethru-intercom.desktop" 2>/dev/null || true
if id -u drivethru &>/dev/null; then
    DRIVETHRU_HOME=$(getent passwd drivethru | cut -d: -f6)
    rm -f "$DRIVETHRU_HOME/.config/autostart/drivethru-intercom.desktop" 2>/dev/null || true
fi

echo "[5/5] Removing installation directory..."
rm -rf "$INSTALL_DIR"

echo ""
echo "=== Uninstall Complete ==="
echo ""
echo "The Drive-Thru Intercom system has been removed."
echo ""
echo "Note: The 'drivethru' user (if created for kiosk mode) was not removed."
echo "To remove it manually: sudo userdel -r drivethru"
echo ""
echo "Restart PipeWire to complete cleanup:"
echo "  systemctl --user restart pipewire wireplumber"
echo ""
