#!/bin/bash
#
# Disable Drive-Thru Intercom Kiosk Mode
# Reverts the system to normal operation
#
set -e

echo "=== Disabling Kiosk Mode ==="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: Please run with sudo"
    exit 1
fi

# 1. Disable auto-login
echo "[1/4] Disabling auto-login..."
cat > /etc/gdm3/custom.conf << 'EOF'
[daemon]
# AutomaticLoginEnable=false

[security]

[xdmcp]

[chooser]

[debug]
EOF

# 2. Stop and disable services
echo "[2/4] Stopping services..."
systemctl stop drivethru-server.service 2>/dev/null || true
systemctl disable drivethru-server.service 2>/dev/null || true

# 3. Remove autostart entry
echo "[3/4] Removing autostart..."
DRIVETHRU_HOME=$(getent passwd drivethru | cut -d: -f6)
rm -f "$DRIVETHRU_HOME/.config/autostart/drivethru-intercom.desktop" 2>/dev/null || true

# 4. Re-enable GNOME features
echo "[4/4] Restoring GNOME settings..."
sudo -u drivethru dbus-launch gsettings reset org.gnome.desktop.screensaver lock-enabled 2>/dev/null || true
sudo -u drivethru dbus-launch gsettings reset org.gnome.desktop.screensaver idle-activation-enabled 2>/dev/null || true
sudo -u drivethru dbus-launch gsettings reset org.gnome.desktop.session idle-delay 2>/dev/null || true

echo ""
echo "=== Kiosk Mode Disabled ==="
echo ""
echo "The system will now boot to normal login screen."
echo "You can still run the application manually:"
echo "  /opt/drivethru/venv/bin/python /opt/drivethru/gui/main.py"
echo ""
echo "Reboot to apply changes."
echo ""
