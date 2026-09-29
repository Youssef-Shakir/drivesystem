#!/usr/bin/env bash
#
# Drive-Thru Intercom System - Installer
# =========================================
# Installs IN PLACE, wherever this repo is checked out (no copying to
# /opt or elsewhere) - that's how the reference deployment actually runs:
# a per-user systemd service pointed straight at the cloned repo.
#
# Usage:
#   git clone <repo-url> ~/drivesystem
#   cd ~/drivesystem
#   ./install.sh
#
# Run as your normal user, NOT root/sudo - it calls sudo itself for the
# few steps that need it (apt install, adding you to hardware groups,
# enabling linger) and asks for your password interactively at that
# point, same as running any of those commands by hand.
#
# What this does, in order:
#   1. Installs system packages (Python, PipeWire/WirePlumber, Bluetooth,
#      ffmpeg).
#   2. Creates a Python venv in .venv/ and installs requirements.txt.
#   3. Copies config.yaml.example -> config.yaml if you don't have one
#      yet (never overwrites an existing config.yaml).
#   4. Deploys the PipeWire/WirePlumber configs from pipewire/ into
#      ~/.config/, rewriting the LADSPA plugin's absolute path to match
#      wherever THIS clone actually lives.
#   5. Installs the systemd --user service, same path-rewrite, enables
#      it, and enables linger so it survives a reboot with nobody logged
#      in (this box is headless).
#   6. Adds you to the audio/dialout/plugdev groups (mic+speaker access,
#      the ESP32 serial port, and Bluetooth) if you aren't already.
#
# Does NOT touch firewall/SSH hardening (see scripts/harden.sh for that -
# separate on purpose, since it's a host-level decision, not part of
# getting the app running) and does NOT pick your PIN or device names for
# you - those are yours to set in config.yaml, see README.md.

set -euo pipefail

if [ "$(id -u)" -eq 0 ]; then
    echo "Run this as your normal user, not root/sudo - it calls sudo itself where needed." >&2
    exit 1
fi

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$REPO_DIR/.venv"
PYTHON_BIN="python3.11"

echo "=================================================="
echo "  Drive-Thru Intercom System - Installer"
echo "=================================================="
echo "Installing in place at: $REPO_DIR"
echo

read -p "Continue? [y/N] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

# --- 1. System packages --------------------------------------------------
echo
echo "[1/6] Installing system packages (will ask for your sudo password)..."
sudo apt-get update -qq
sudo apt-get install -y \
    "$PYTHON_BIN" "${PYTHON_BIN}-venv" python3-pip \
    pipewire pipewire-audio-client-libraries wireplumber libspa-0.2-bluetooth \
    bluez bluez-tools \
    ffmpeg git

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "ERROR: $PYTHON_BIN not available after install - check your Ubuntu version" \
         "(this was built/tested on 22.04 'jammy'; a newer release may only ship a" \
         "different python3.x - if so, edit PYTHON_BIN at the top of this script)." >&2
    exit 1
fi

# --- 2. Python venv --------------------------------------------------------
echo
echo "[2/6] Creating Python virtual environment..."
if [ ! -d "$VENV_DIR" ]; then
    "$PYTHON_BIN" -m venv "$VENV_DIR"
else
    echo "    .venv already exists, reusing it."
fi
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -r "$REPO_DIR/requirements.txt" -q

# --- 3. config.yaml --------------------------------------------------------
echo
echo "[3/6] Setting up config.yaml..."
if [ -f "$REPO_DIR/config.yaml" ]; then
    echo "    config.yaml already exists - leaving it untouched."
else
    cp "$REPO_DIR/config.yaml.example" "$REPO_DIR/config.yaml"
    chmod 600 "$REPO_DIR/config.yaml"
    echo "    Created config.yaml from the template - YOU MUST EDIT IT before"
    echo "    starting the server (PIN, device names, Bluetooth adapter MAC)."
    echo "    See README.md 'Configure the Server'."
fi

# --- 4. PipeWire / WirePlumber configs -------------------------------------
echo
echo "[4/6] Deploying PipeWire/WirePlumber configs..."
mkdir -p ~/.config/pipewire/pipewire.conf.d
mkdir -p ~/.config/wireplumber/wireplumber.conf.d

# 97/99-*.conf (not the -bluetooth one, that's WirePlumber's directory, and
# not .disabled ones) go to pipewire.conf.d. The plugin= line inside the
# DeepFilterNet config has an absolute path baked in - rewrite it to match
# THIS clone's actual location so it isn't silently still pointing at
# wherever the original reference install lived.
for conf in "$REPO_DIR"/pipewire/9*-drivethru-*.conf; do
    name="$(basename "$conf")"
    [[ "$name" == *bluetooth* ]] && continue
    sed "s|plugin = \"[^\"]*/pipewire/plugins/|plugin = \"$REPO_DIR/pipewire/plugins/|" \
        "$conf" > ~/.config/pipewire/pipewire.conf.d/"$name"
done
cp "$REPO_DIR/pipewire/99-drivethru-bluetooth.conf" ~/.config/wireplumber/wireplumber.conf.d/
echo "    Deployed. Restart PipeWire after editing device names in config.yaml:"
echo "      systemctl --user restart pipewire pipewire-pulse wireplumber"

# --- 5. systemd service -----------------------------------------------------
echo
echo "[5/6] Installing systemd user service..."
mkdir -p ~/.config/systemd/user
sed -e "s|WorkingDirectory=.*|WorkingDirectory=$REPO_DIR|" \
    -e "s|ExecStart=.*python|ExecStart=$VENV_DIR/bin/python|" \
    "$REPO_DIR/systemd/drivethru.service" > ~/.config/systemd/user/drivethru.service

systemctl --user daemon-reload
systemctl --user enable drivethru.service
sudo loginctl enable-linger "$USER"
echo "    Installed and enabled (not started yet - config.yaml needs your edits first)."

# --- 6. Hardware group access -----------------------------------------------
echo
echo "[6/6] Checking group membership (audio, dialout, plugdev)..."
NEEDED_GROUPS=(audio dialout plugdev)
MISSING=()
for g in "${NEEDED_GROUPS[@]}"; do
    id -nG "$USER" | grep -qw "$g" || MISSING+=("$g")
done
if [ ${#MISSING[@]} -gt 0 ]; then
    sudo usermod -aG "$(IFS=,; echo "${MISSING[*]}")" "$USER"
    echo "    Added to: ${MISSING[*]} - LOG OUT AND BACK IN for this to take effect."
else
    echo "    Already in all required groups."
fi

echo
echo "=================================================="
echo "  Install steps done. Before starting the server:"
echo "=================================================="
echo "  1. Edit config.yaml - PIN, serial port, device names, Bluetooth"
echo "     adapter MAC. Find device names with:"
echo "       pw-cli list-objects Node | grep -E 'node.name|node.description'"
echo "       bluetoothctl list"
echo "  2. Edit the deployed PipeWire configs' device names to match:"
echo "       ~/.config/pipewire/pipewire.conf.d/99-drivethru-aec.conf"
echo "  3. Pair your Bluetooth headset: bluetoothctl (scan, pair, trust, connect)"
echo "  4. Restart PipeWire: systemctl --user restart pipewire pipewire-pulse wireplumber"
echo "  5. Start the server: systemctl --user start drivethru.service"
echo "  6. Open http://<this-machine-ip>:8080 and log in with your PIN"
echo
echo "  Optional but recommended: sudo bash scripts/harden.sh"
echo "  (fail2ban + firewall - see README.md 'Security')"
echo
echo "  Full details: README.md"
echo
