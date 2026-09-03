#!/bin/bash
#
# Drive-Thru Intercom System Installer
# For Ubuntu 24.04 LTS
#
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/drivethru"
VENV_DIR="$INSTALL_DIR/venv"

echo "=============================================="
echo "  Drive-Thru Intercom System Installer"
echo "=============================================="
echo ""
echo "Source: $SCRIPT_DIR"
echo "Target: $INSTALL_DIR"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: Please run with sudo"
    echo "Usage: sudo ./install.sh"
    exit 1
fi

# Get the actual user (not root)
REAL_USER="${SUDO_USER:-$USER}"
echo "Installing for user: $REAL_USER"
echo ""

# Confirmation
read -p "Continue with installation? [y/N] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Installation cancelled."
    exit 0
fi

echo ""
echo "[1/9] Installing system dependencies..."
apt-get update
apt-get install -y \
    python3.12 \
    python3.12-venv \
    python3-pip \
    pipewire \
    pipewire-audio \
    wireplumber \
    libpipewire-0.3-modules \
    bluez \
    bluez-tools \
    ffmpeg \
    git \
    unclutter

echo ""
echo "[2/9] Creating installation directory..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR/server/assets"
mkdir -p "$INSTALL_DIR/gui"
mkdir -p "$INSTALL_DIR/scripts"
mkdir -p "$INSTALL_DIR/pipewire"
mkdir -p "$INSTALL_DIR/systemd"

echo ""
echo "[3/9] Copying application files..."
# Server
cp -r "$SCRIPT_DIR/server/"* "$INSTALL_DIR/server/"
# GUI
cp -r "$SCRIPT_DIR/gui/"* "$INSTALL_DIR/gui/"
# Scripts
cp -r "$SCRIPT_DIR/scripts/"* "$INSTALL_DIR/scripts/"
# PipeWire configs
cp -r "$SCRIPT_DIR/pipewire/"* "$INSTALL_DIR/pipewire/"
# Systemd service
cp -r "$SCRIPT_DIR/systemd/"* "$INSTALL_DIR/systemd/"
# Config
cp "$SCRIPT_DIR/config.yaml" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/requirements.txt" "$INSTALL_DIR/"

echo ""
echo "[4/9] Creating Python virtual environment..."
python3.12 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

echo ""
echo "[5/9] Installing Python dependencies..."
pip install --upgrade pip
pip install -r "$INSTALL_DIR/requirements.txt"
deactivate

echo ""
echo "[6/9] Installing PipeWire configuration..."
REAL_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)

# Create user's PipeWire config directory
mkdir -p "$REAL_HOME/.config/pipewire/pipewire.conf.d"
mkdir -p "$REAL_HOME/.config/wireplumber/wireplumber.conf.d"

# Copy AEC configuration
cp "$INSTALL_DIR/pipewire/99-drivethru-aec.conf" \
   "$REAL_HOME/.config/pipewire/pipewire.conf.d/"

# Copy Bluetooth mSBC configuration
cp "$INSTALL_DIR/pipewire/99-drivethru-bluetooth.conf" \
   "$REAL_HOME/.config/wireplumber/wireplumber.conf.d/"

# Set ownership
chown -R "$REAL_USER:$REAL_USER" "$REAL_HOME/.config/pipewire"
chown -R "$REAL_USER:$REAL_USER" "$REAL_HOME/.config/wireplumber"

echo ""
echo "[7/9] Setting up user systemd service..."
mkdir -p "$REAL_HOME/.config/systemd/user"
cp "$INSTALL_DIR/systemd/drivethru.service" "$REAL_HOME/.config/systemd/user/"
chown -R "$REAL_USER:$REAL_USER" "$REAL_HOME/.config/systemd"

echo ""
echo "[8/9] Adding user to required groups..."
usermod -aG audio,dialout,plugdev "$REAL_USER"

echo ""
echo "[9/9] Setting permissions..."
chown -R "$REAL_USER:$REAL_USER" "$INSTALL_DIR"
chmod +x "$INSTALL_DIR/scripts/"*.sh
chmod +x "$INSTALL_DIR/scripts/"*.py

echo ""
echo "=============================================="
echo "  Installation Complete!"
echo "=============================================="
echo ""
echo "Files installed to: $INSTALL_DIR"
echo ""
echo "Next steps:"
echo ""
echo "1. Connect your hardware:"
echo "   - Behringer UMC202HD USB audio interface"
echo "   - RODE NTG3 microphone"
echo "   - Bluetooth headset (pair via Settings > Bluetooth)"
echo "   - ESP32 sensor via USB serial"
echo ""
echo "2. Update configuration:"
echo "   sudo nano $INSTALL_DIR/config.yaml"
echo "   - Set the correct serial port (e.g., /dev/ttyUSB0)"
echo "   - Verify audio device names"
echo ""
echo "3. Restart PipeWire to load AEC config:"
echo "   systemctl --user restart pipewire wireplumber"
echo ""
echo "4. Start the application:"
echo ""
echo "   Option A - GUI Application:"
echo "   $VENV_DIR/bin/python $INSTALL_DIR/gui/main.py"
echo ""
echo "   Option B - Web Dashboard:"
echo "   cd $INSTALL_DIR/server && $VENV_DIR/bin/python -m uvicorn main:app"
echo "   Then open http://localhost:8000 in browser"
echo ""
echo "   Option C - Background Service:"
echo "   systemctl --user enable --now drivethru.service"
echo ""
echo "5. For dedicated kiosk mode (optional):"
echo "   sudo $INSTALL_DIR/scripts/setup-kiosk.sh"
echo ""
echo "For help: https://github.com/your-repo/drivethru-intercom"
echo ""
