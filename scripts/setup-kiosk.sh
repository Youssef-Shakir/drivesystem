#!/bin/bash
#
# Drive-Thru Intercom Kiosk Mode Setup
# Configures Ubuntu 24.04 as a dedicated drive-thru intercom system
#
set -e

INSTALL_DIR="/opt/drivethru"
SERVICE_USER="${SUDO_USER:-$USER}"
SERVICE_HOME=$(getent passwd "$SERVICE_USER" | cut -d: -f6)

echo "=== Drive-Thru Intercom Kiosk Setup ==="
echo "User: $SERVICE_USER"
echo "Home: $SERVICE_HOME"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: Please run with sudo"
    exit 1
fi

# 1. Create kiosk user if it doesn't exist
echo "[1/8] Setting up kiosk user..."
if ! id -u drivethru &>/dev/null; then
    useradd -m -s /bin/bash -G audio,video,dialout,plugdev drivethru
    echo "Created user 'drivethru'"
else
    echo "User 'drivethru' already exists"
fi

# 2. Configure auto-login
echo "[2/8] Configuring auto-login..."
mkdir -p /etc/gdm3
cat > /etc/gdm3/custom.conf << 'EOF'
[daemon]
AutomaticLoginEnable=true
AutomaticLogin=drivethru

[security]

[xdmcp]

[chooser]

[debug]
EOF

# 3. Create systemd user session directory
echo "[3/8] Setting up user session..."
DRIVETHRU_HOME=$(getent passwd drivethru | cut -d: -f6)
mkdir -p "$DRIVETHRU_HOME/.config/autostart"
mkdir -p "$DRIVETHRU_HOME/.config/systemd/user"

# 4. Copy desktop entry for autostart
echo "[4/8] Configuring autostart..."
cp "$INSTALL_DIR/gui/drivethru-intercom.desktop" "$DRIVETHRU_HOME/.config/autostart/"
chown drivethru:drivethru "$DRIVETHRU_HOME/.config/autostart/drivethru-intercom.desktop"

# 5. Create wrapper script that starts in fullscreen
echo "[5/8] Creating kiosk launcher..."
cat > "$INSTALL_DIR/start-kiosk.sh" << 'EOF'
#!/bin/bash
# Wait for display server
sleep 3

# Disable screen blanking
xset s off
xset -dpms
xset s noblank

# Hide cursor after 3 seconds of inactivity
unclutter -idle 3 &

# Start the application in fullscreen
cd /opt/drivethru
exec /opt/drivethru/venv/bin/python /opt/drivethru/gui/main.py --fullscreen
EOF
chmod +x "$INSTALL_DIR/start-kiosk.sh"

# Update desktop entry to use kiosk launcher
cat > "$DRIVETHRU_HOME/.config/autostart/drivethru-intercom.desktop" << 'EOF'
[Desktop Entry]
Version=1.0
Type=Application
Name=Drive-Thru Intercom
Comment=Drive-Thru Intercom Kiosk
Exec=/opt/drivethru/start-kiosk.sh
Terminal=false
X-GNOME-Autostart-enabled=true
EOF
chown drivethru:drivethru "$DRIVETHRU_HOME/.config/autostart/drivethru-intercom.desktop"

# 6. Disable unnecessary GNOME features
echo "[6/8] Configuring GNOME for kiosk mode..."
sudo -u drivethru dbus-launch gsettings set org.gnome.desktop.screensaver lock-enabled false 2>/dev/null || true
sudo -u drivethru dbus-launch gsettings set org.gnome.desktop.screensaver idle-activation-enabled false 2>/dev/null || true
sudo -u drivethru dbus-launch gsettings set org.gnome.desktop.session idle-delay 0 2>/dev/null || true
sudo -u drivethru dbus-launch gsettings set org.gnome.desktop.notifications show-banners false 2>/dev/null || true

# 7. Install unclutter for hiding cursor
echo "[7/8] Installing kiosk utilities..."
apt-get install -y unclutter

# 8. Create systemd service for the backend server
echo "[8/8] Setting up backend service..."
cat > /etc/systemd/system/drivethru-server.service << EOF
[Unit]
Description=Drive-Thru Intercom Backend Server
After=network.target sound.target

[Service]
Type=simple
User=drivethru
Group=drivethru
WorkingDirectory=$INSTALL_DIR/server
Environment=PATH=$INSTALL_DIR/venv/bin:/usr/bin
ExecStart=$INSTALL_DIR/venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable drivethru-server.service

echo ""
echo "=== Kiosk Setup Complete ==="
echo ""
echo "The system is now configured for kiosk mode:"
echo "  - Auto-login as 'drivethru' user"
echo "  - GUI starts automatically in fullscreen"
echo "  - Screen blanking disabled"
echo "  - Mouse cursor hides after inactivity"
echo "  - Backend server runs as system service"
echo ""
echo "To start now without rebooting:"
echo "  sudo systemctl start drivethru-server"
echo "  sudo -u drivethru /opt/drivethru/start-kiosk.sh"
echo ""
echo "To revert to normal mode, run:"
echo "  sudo $INSTALL_DIR/scripts/disable-kiosk.sh"
echo ""
