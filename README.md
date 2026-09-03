# Drive-Thru Intercom System

A DIY drive-thru intercom system for restaurants, featuring:
- Ultrasonic car detection with pedestrian filtering
- Full-duplex or push-to-talk audio modes
- WebRTC echo cancellation for outdoor environments
- Mobile-friendly web dashboard
- Local-only operation (no cloud, no auth)

## Hardware Requirements

- **Mini PC**: Ubuntu 24.04 LTS with PipeWire audio
- **Audio Interface**: Behringer UMC202HD USB (outdoor mic in, speaker out)
- **Outdoor Mic**: RODE NTG3 or similar shotgun mic
- **Outdoor Speaker**: Horn speaker with amplifier
- **Staff Headset**: Bluetooth headset with USB dongle (mSBC capable)
- **Sensor**: ESP32 + JSN-SR04T ultrasonic sensor
- **RS485**: MAX485 modules for ESP32-to-PC communication (15m CAT6)

## Quick Start

### 1. Ubuntu System Setup

```bash
# Install dependencies
sudo apt update
sudo apt install -y python3.12 python3.12-venv pipewire wireplumber \
    pipewire-audio-client-libraries libspa-0.2-bluetooth git

# Clone the repository
git clone <your-repo-url> ~/drivesystem
cd ~/drivesystem

# Create Python virtual environment
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Generate the chime sound
python scripts/generate_chime.py
```

### 2. Find Your Audio Device Names

```bash
# List all PipeWire nodes
pw-cli list-objects Node | grep -E "(node.name|node.description)"

# Look for entries like:
#   node.name = "alsa_input.usb-BEHRINGER_UMC202HD_XXXXXXXX-00.analog-stereo"
#   node.name = "alsa_output.usb-BEHRINGER_UMC202HD_XXXXXXXX-00.analog-stereo"
#   node.name = "bluez_output.XX_XX_XX_XX_XX_XX.1"
#   node.name = "bluez_input.XX_XX_XX_XX_XX_XX.0"
```

### 3. Configure PipeWire

```bash
# Copy PipeWire config (edit device names first!)
mkdir -p ~/.config/pipewire/pipewire.conf.d
cp pipewire/99-drivethru-aec.conf ~/.config/pipewire/pipewire.conf.d/

# Copy WirePlumber Bluetooth config
mkdir -p ~/.config/wireplumber/wireplumber.conf.d
cp pipewire/99-drivethru-bluetooth.conf ~/.config/wireplumber/wireplumber.conf.d/

# IMPORTANT: Edit the config files and replace placeholder device names
nano ~/.config/pipewire/pipewire.conf.d/99-drivethru-aec.conf

# Restart PipeWire
systemctl --user restart pipewire pipewire-pulse wireplumber
```

### 4. Configure the Server

Edit `config.yaml` with your device names:

```yaml
serial:
  port: /dev/ttyUSB0  # Or /dev/pts/X for simulator

audio:
  outdoor_mic: "dt_aec_source"
  outdoor_speaker: "dt_aec_sink"
  headset_sink: "bluez_output.XX_XX_XX_XX_XX_XX.1"   # Your headset
  headset_source: "bluez_input.XX_XX_XX_XX_XX_XX.0"  # Your headset mic
```

### 5. Flash the ESP32

Using Arduino IDE or PlatformIO:

1. Open `esp32/sensor_node/sensor_node.ino`
2. Select your ESP32 board
3. Upload the sketch

Wiring:
- GPIO5 -> JSN-SR04T TRIG
- GPIO18 -> JSN-SR04T ECHO
- 5V -> JSN-SR04T VCC
- GND -> JSN-SR04T GND
- TX/RX -> MAX485 module -> RS485 cable -> PC's USB-RS485 adapter

### 6. Run the Server

```bash
# Activate virtual environment
cd ~/drivesystem
source .venv/bin/activate

# Run directly
python -m uvicorn server.main:app --host 0.0.0.0 --port 8080

# Or install as a service (see below)
```

Access the dashboard at `http://<pc-ip>:8080`

### 7. Install as System Service

```bash
# Copy service file (edit paths first!)
mkdir -p ~/.config/systemd/user
cp systemd/drivethru.service ~/.config/systemd/user/

# Edit the service file to match your installation path
nano ~/.config/systemd/user/drivethru.service

# Enable and start
systemctl --user daemon-reload
systemctl --user enable drivethru.service
systemctl --user start drivethru.service

# Enable linger so it runs at boot (before login)
sudo loginctl enable-linger $USER

# Check status
systemctl --user status drivethru.service
journalctl --user -u drivethru.service -f
```

## Testing Without Hardware

Use the sensor simulator to test the system:

```bash
# Terminal 1: Start simulator
python scripts/simulate_sensor.py

# Note the PTY path (e.g., /dev/pts/5)
# Update config.yaml: serial.port: "/dev/pts/5"

# Terminal 2: Start server
python -m uvicorn server.main:app --host 0.0.0.0 --port 8080

# In simulator terminal, press:
#   'a' - simulate car arrival
#   'l' - simulate car leaving
#   'q' - quit
```

## Running Tests

```bash
source .venv/bin/activate
pytest tests/ -v
```

## Tuning Guide

### Sensor Detection Threshold

The default detection threshold is 150cm. Adjust in `config.yaml`:

```yaml
sensor:
  detect_threshold_cm: 150  # Distance in cm
```

Or modify `DETECT_CM` in the ESP32 sketch for permanent change.

**Tips:**
- Measure the actual distance to passing cars on the street
- Set threshold ~30cm less than that distance
- Account for different vehicle sizes (motorcycles vs trucks)

### Echo Cancellation

If you hear echo or feedback:

1. **Check loopback routing**: Ensure audio isn't looping through speakers and back to mic
2. **Adjust AEC settings** in `99-drivethru-aec.conf`:
   ```
   webrtc.noise_suppression_level = 3  # More aggressive (0-3)
   ```
3. **Physical isolation**: Aim the shotgun mic away from the speaker

### Bluetooth Audio Quality

For best headset quality:

1. **Verify mSBC is active**:
   ```bash
   pactl list cards | grep -A 20 "bluez"
   # Look for "headset-head-unit-msbc"
   ```

2. **Force mSBC profile**:
   ```bash
   pactl set-card-profile bluez_card.XX_XX_XX_XX_XX_XX headset-head-unit-msbc
   ```

3. **Reduce interference**: Keep Bluetooth dongle away from USB 3.0 ports and WiFi antennas

### Volume Levels

Adjust initial volumes in `config.yaml`:

```yaml
audio:
  default_volumes:
    outdoor_mic: 1.0      # 0.0-1.5 (100% = 1.0)
    outdoor_speaker: 0.8  # Start lower to avoid feedback
    headset: 1.0
```

Or use the web dashboard sliders at runtime.

## Troubleshooting

### "Sensor offline" on dashboard

1. Check USB-RS485 adapter is connected: `ls /dev/ttyUSB*`
2. Check ESP32 is powered and running
3. Verify baud rate matches (115200)
4. Check RS485 A/B wiring polarity

### No audio

1. Check PipeWire is running: `systemctl --user status pipewire`
2. Verify device names in config match `pw-cli list-objects Node` output
3. Restart PipeWire: `systemctl --user restart pipewire wireplumber`
4. Check Bluetooth headset is paired and connected

### Dashboard not loading

1. Check server is running: `curl http://localhost:8080/api/state`
2. Check firewall allows port 8080: `sudo ufw allow 8080/tcp`
3. Check logs: `journalctl --user -u drivethru.service`

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Web dashboard |
| `/api/state` | GET | Current system state |
| `/api/stats` | GET | Today's statistics |
| `/api/volume` | POST | Set device volume |
| `/api/mute` | POST | Set device mute state |
| `/api/mode` | POST | Set audio mode (full_duplex/ptt) |
| `/api/ptt` | POST | Set PTT state (in PTT mode) |
| `/api/refresh-audio` | POST | Refresh PipeWire node IDs |

## License

MIT License - See LICENSE file for details.
