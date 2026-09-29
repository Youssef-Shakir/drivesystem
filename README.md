# Drive-Thru Intercom System

A drive-thru intercom system built around a mini PC, featuring:
- Ultrasonic car detection with pedestrian/false-trigger filtering
- Full-duplex or push-to-talk audio modes
- WebRTC echo cancellation + DeepFilterNet neural noise suppression for
  the outdoor mic
- A PIN-gated, mobile-friendly web dashboard
- An offline "Mic Tuning Lab" for A/B-testing noise-filter settings
  against real recorded audio before applying them live
- Local-only operation - no cloud dependency, everything runs on the box

## Hardware Requirements

- **Mini PC**: Ubuntu 22.04 LTS with PipeWire audio (this system is built
  and tested against PipeWire 1.0.7 / WirePlumber 0.5.2 - newer versions
  should work but haven't been verified here)
- **Audio Interface**: USB audio interface with a mic input and a line
  output (reference hardware: Behringer UMC202HD)
- **Outdoor Mic**: Shotgun/directional mic aimed away from the speaker
- **Outdoor Speaker**: Horn speaker with amplifier
- **Staff Headset**: Bluetooth headset supporting the HSP/HFP
  headset-head-unit profile (needed for the mic side - A2DP alone is
  output-only)
- **Sensor**: ESP32 + JSN-SR04T ultrasonic sensor
- **RS485**: MAX485 modules for ESP32-to-PC communication over a longer
  cable run than USB alone would reliably reach

## Quick Start (automated)

```bash
git clone <your-repo-url> ~/drivesystem
cd ~/drivesystem
./install.sh
```

This installs system packages, creates the Python venv, creates
`config.yaml` from the template, deploys the PipeWire/WirePlumber
configs, and installs+enables the systemd service - but does **not**
start it, because you still need to:

1. **Edit `config.yaml`** - set your dashboard PIN, serial port, audio
   device names, and Bluetooth adapter MAC (see below).
2. **Edit the deployed PipeWire config's device names** to match your
   actual hardware: `~/.config/pipewire/pipewire.conf.d/99-drivethru-aec.conf`
3. **Pair your Bluetooth headset** (see below).
4. **Restart PipeWire and start the service**:
   ```bash
   systemctl --user restart pipewire pipewire-pulse wireplumber
   systemctl --user start drivethru.service
   ```
5. Open `http://<this-machine-ip>:8080` and log in with your PIN.

Run `./install.sh` again any time - it's safe to re-run (it won't
overwrite an existing `config.yaml` or re-clone the venv).

The rest of this README covers each of those steps in more detail, plus
tuning, troubleshooting, and security.

## Manual Install (what install.sh actually does)

If you'd rather do it by hand, or `install.sh` doesn't fit your setup:

### 1. System packages

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3-pip \
    pipewire pipewire-audio-client-libraries wireplumber libspa-0.2-bluetooth \
    bluez bluez-tools ffmpeg git
```

### 2. Python environment

```bash
cd ~/drivesystem
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure the server

```bash
cp config.yaml.example config.yaml
chmod 600 config.yaml
nano config.yaml
```

`config.yaml` is **gitignored on purpose** - see [Security](#security)
below for why. At minimum, set:

- `security.pin` - the numeric PIN staff use to open the dashboard
- `serial.port` - your ESP32's serial device, e.g. `/dev/ttyUSB0`
- `audio.outdoor_mic` / `audio.outdoor_speaker` - leave as
  `dt_aec_source` / `dt_aec_sink` if you're using the provided AEC config
  below; these are virtual node names it creates
- `audio.headset_sink` / `audio.headset_source` - your Bluetooth
  headset's PipeWire node names (find after pairing, see below)
- `audio.bluetooth_adapter` - your Bluetooth controller's own MAC (**not**
  the headset's), from `bluetoothctl list`. Required as soon as more than
  one Bluetooth adapter is ever plugged into this machine - BlueZ silently
  makes whichever adapter was plugged in last its "default" controller,
  permanently, even after that adapter is powered back off. Without this
  pinned, a second adapter appearing (even briefly) can silently break
  reconnection to an already-working headset. Set it even with only one
  adapter, so it's already correct if a second one is ever added.

Find device names with:

```bash
pw-cli list-objects Node | grep -E "(node.name|node.description)"
bluetoothctl list
```

### 4. PipeWire configuration

```bash
mkdir -p ~/.config/pipewire/pipewire.conf.d
mkdir -p ~/.config/wireplumber/wireplumber.conf.d

cp pipewire/99-drivethru-aec.conf ~/.config/pipewire/pipewire.conf.d/
cp pipewire/97-drivethru-deepfilter.conf ~/.config/pipewire/pipewire.conf.d/
cp pipewire/99-drivethru-bluetooth.conf ~/.config/wireplumber/wireplumber.conf.d/
```

Edit the two files you just copied into `pipewire.conf.d/` and replace
the placeholder device names with your actual hardware (from
`pw-cli list-objects Node` above). `97-drivethru-deepfilter.conf` also
has a `plugin = "/absolute/path/.../libdeep_filter_ladspa.so"` line -
point it at wherever **this clone** actually lives
(`install.sh` does this rewrite for you automatically).

Restart PipeWire to load them:

```bash
systemctl --user restart pipewire pipewire-pulse wireplumber
```

### 5. Pair the Bluetooth headset

Put the headset into pairing mode (usually holding its power/call button
until the LED fast-blinks), then:

```bash
bluetoothctl
[bluetoothctl]# agent on
[bluetoothctl]# default-agent
[bluetoothctl]# scan on
# wait for your headset's name to appear, then:
[bluetoothctl]# pair XX:XX:XX:XX:XX:XX
[bluetoothctl]# trust XX:XX:XX:XX:XX:XX
[bluetoothctl]# connect XX:XX:XX:XX:XX:XX
[bluetoothctl]# scan off
[bluetoothctl]# quit
```

Then confirm PipeWire actually created the audio nodes (a Bluetooth
"Connected: yes" is not the same as audio actually working - see
[Troubleshooting](#troubleshooting)):

```bash
pw-cli list-objects Node | grep -E "bluez_(input|output)"
```

If nothing shows up, force the HSP/HFP profile (PipeWire defaults new
Bluetooth devices to output-only A2DP, which has no mic):

```bash
wpctl set-profile <device-id> <headset-head-unit-profile-index>
# or just restart the app once configured - it does this automatically
```

Put the resulting `bluez_output.XX_XX_XX_XX_XX_XX.1` /
`bluez_input.XX_XX_XX_XX_XX_XX.0` node names into `config.yaml`'s
`headset_sink` / `headset_source`.

**If you ever add a second Bluetooth adapter** (e.g. a USB dongle for
range): pair the headset to whichever adapter you're actually using,
set `audio.bluetooth_adapter` in `config.yaml` to that adapter's MAC, and
restart the service. Test the new adapter thoroughly before relying on
it - not every USB Bluetooth dongle handles the HFP audio profile
reliably even when the radio-level pairing itself succeeds.

### 6. Flash the ESP32 sensor node

Using Arduino IDE or PlatformIO, open `esp32/sensor_node/sensor_node.ino`,
select your board, and upload.

Wiring:
- GPIO5 -> JSN-SR04T TRIG
- GPIO18 -> JSN-SR04T ECHO
- 5V -> JSN-SR04T VCC
- GND -> JSN-SR04T GND
- TX/RX -> MAX485 module -> RS485 cable -> PC's USB-RS485 adapter

### 7. Run it

Directly, for testing:

```bash
source .venv/bin/activate
python -m uvicorn server.main:app --host 0.0.0.0 --port 8080
```

Or as a service (recommended for production - restarts automatically,
survives reboot):

```bash
mkdir -p ~/.config/systemd/user
cp systemd/drivethru.service ~/.config/systemd/user/
# Edit WorkingDirectory/ExecStart in the copy if this repo isn't at
# /home/<you>/drivesystem
nano ~/.config/systemd/user/drivethru.service

systemctl --user daemon-reload
systemctl --user enable --now drivethru.service
sudo loginctl enable-linger "$USER"   # starts it at boot, no login needed

systemctl --user status drivethru.service
journalctl --user -u drivethru.service -f
```

Access the dashboard at `http://<pc-ip>:8080` and log in with the PIN
you set in `config.yaml`.

## Security

Read this before putting the system on any network you don't fully
control.

- **The dashboard PIN is a shared-terminal deterrent, not real
  authentication.** It stops someone glancing at an unattended tab from
  changing settings; it does not withstand a determined attacker
  (no rate-limit lockout beyond a short cooldown, no 2FA, a 4-digit PIN
  has only 10,000 possibilities). **Never expose port 8080 to the open
  internet.** Keep it LAN-only, or behind a VPN if remote access is
  needed.
- **`config.yaml` is gitignored and must stay that way.** It holds your
  real PIN and this site's device MACs. `config.yaml.example` is the
  tracked template - always edit a copy, never the template itself, and
  never `git add -f` the real file. If a PIN or MAC ever does end up
  committed, treat it as burned: change the PIN and remove the file from
  tracking (`git rm --cached config.yaml`) rather than assuming a later
  commit "fixes" it - it's still in history.
- **Run `scripts/harden.sh` once per machine** (`sudo bash
  scripts/harden.sh`). It installs and configures fail2ban against SSH
  brute-forcing, and sets up a firewall (ufw) that allows SSH from
  anywhere but restricts the dashboard port to your LAN subnet only -
  edit the `LAN_SUBNET` variable at the top of the script first if
  your network isn't `192.168.50.0/24`. It leaves SSH password login
  as-is; switching to key-only auth is a good next step but is easy to
  lock yourself out with if rushed, so it's deliberately left as a
  separate, manual decision rather than something this script does for
  you.
- **The disk itself is not encrypted** on the reference install (plain
  ext4 on LVM). That means anyone with physical access to the drive can
  read the source code and any recorded audio directly, bypassing all of
  the above. Retrofitting full-disk encryption onto a running system
  means repartitioning and reinstalling, so it isn't something to do
  casually - but it's worth enabling (Ubuntu's installer offers LUKS
  full-disk encryption as a checkbox) the next time this box, or a new
  one, gets a fresh OS install, especially if it's in a physically
  accessible location.
- **File permissions**: `install.sh` and `harden.sh` both set
  `config.yaml`, `.session_secret`, and `drivethru.db` to `600`
  (owner-only) and the repo directory to `750`. If you ever copy these
  files elsewhere (backups, a second machine), carry the same
  permissions with them.

## Testing Without Hardware

Use the sensor simulator to test the system without the ESP32/sensor
connected:

```bash
# Terminal 1: Start simulator
python scripts/simulate_sensor.py
# Note the PTY path it prints (e.g. /dev/pts/5), set serial.port in
# config.yaml to that path

# Terminal 2: Start server
python -m uvicorn server.main:app --host 0.0.0.0 --port 8080

# In the simulator terminal:
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

### Sensor detection band

```yaml
sensor:
  detect_min_cm: 30    # closer than this doesn't count (e.g. a person
                        # walking right up to the window)
  detect_max_cm: 150   # farther than this doesn't count
  arrival_hold_sec: 1.0
  departure_hold_sec: 2.0
  steady_sec: 2.0       # how long readings must stay stable before
                         # they're trusted at all
```

Measure the actual distance to a car stopped at your window and set the
band around that, with margin for different vehicle heights/sizes. Also
adjustable live from the dashboard's Settings panel.

### Outdoor mic noise filtering

The live path is WebRTC AEC (`99-drivethru-aec.conf`) followed by
DeepFilterNet neural noise suppression (`97-drivethru-deepfilter.conf`).
Two DeepFilterNet parameters are live-tunable from the dashboard's
**Settings > Mic Tuning Lab**:

- **Attenuation Limit (dB)**: how much noise suppression is allowed.
  0 = off, 100 = maximum (can cut speech mid-word if pushed too high -
  confirmed by testing). Start around 40-60 and adjust by ear.
- **Post Filter Beta**: an additional post-filter stage, ships disabled
  (0.0) since it was found to contribute to voice-clipping alongside a
  too-high attenuation limit in earlier testing.

The Mic Tuning Lab lets you generate candidate settings against real
recorded audio (via the on-demand recorder, Settings > Mic Tuning
Recording) and listen to raw vs. live-filtered vs. candidate before
applying anything - much safer than tuning by ear on a live call.

### Bluetooth headset audio quality

The WirePlumber config (`99-drivethru-bluetooth.conf`) enables mSBC
(16kHz wideband voice) when the headset supports it, falling back to
CVSD (8kHz) otherwise - this is normal HSP/HFP behavior, not a bug.
Check which is active:

```bash
pw-cli enum-params <bluez-node-id> Format
# look for audio.rate: 16000 (mSBC) vs 8000 (CVSD)
```

Keep any Bluetooth dongle away from USB 3.0 ports and Wi-Fi antennas -
both are known 2.4GHz interference sources for Bluetooth audio.

### Volume levels

Adjustable live from the dashboard sliders (values persist back to
`config.yaml` automatically), or set initial defaults directly:

```yaml
audio:
  default_volumes:
    outdoor_mic: 1.0       # 0.0-1.5 (1.0 = 100%)
    outdoor_speaker: 0.8   # start lower to avoid feedback, raise gradually
    headset: 1.0           # staff's ears
    indoor_mic: 1.0         # staff's mic, as heard by the customer
```

## Troubleshooting

### "Sensor offline" on dashboard

1. Check the USB-RS485 adapter is connected: `ls /dev/ttyUSB*`
2. Check the ESP32 is powered and running
3. Verify the baud rate matches (`serial.baudrate` in config.yaml)
4. Check RS485 A/B wiring polarity

### Headset shows "Connected" but there's no audio

This is the single most common Bluetooth issue with this system -
BlueZ's "Connected: yes" only means the radio link is up, not that
PipeWire has created a usable audio path yet:

1. Check PipeWire actually created the nodes:
   `pw-cli list-objects Node | grep bluez`. Nothing there = PipeWire
   hasn't caught up yet (can take a few seconds after connect) or the
   device is stuck on the wrong profile.
2. If nodes exist but there's still no source (mic) node, it's likely
   stuck on A2DP (output-only) instead of headset-head-unit - the app
   forces this automatically on connect, or do it manually:
   `wpctl set-profile <device-id> <headset-head-unit-index>`.
3. **More than one Bluetooth adapter in the system?** Set
   `audio.bluetooth_adapter` in config.yaml to the one your headset is
   actually paired to - see the note under step 5 of Manual Install.
   Without this, BlueZ can silently be routing every connect attempt
   through the wrong adapter.
4. As a last resort, restart the whole audio stack:
   `systemctl --user restart pipewire pipewire-pulse wireplumber` then
   reconnect the headset.

### No audio at all (not just the headset)

1. Check PipeWire is running: `systemctl --user status pipewire`
2. Verify device names in `config.yaml` match
   `pw-cli list-objects Node` output exactly
3. Restart PipeWire: `systemctl --user restart pipewire wireplumber`

### Outdoor mic leaking to the outdoor speaker when the headset disconnects

Should not happen on a current checkout - `99-drivethru-aec.conf`'s
loopback nodes are set with `node.dont-fallback` + `node.linger` so a
missing headset target parks the stream instead of falling back to the
outdoor speaker. If you're seeing this, confirm those two properties are
still present on both loopback `playback.props`/`capture.props` blocks
in your deployed config - an older or hand-edited copy may be missing
them.

### Dashboard not loading / 401 Unauthorized

1. Check the server is running: `curl http://localhost:8080/api/state`
   (a 401 here is expected if unauthenticated - that's the PIN gate
   working correctly, not a bug)
2. Check the firewall allows the dashboard port from your machine's
   network: `sudo ufw status` (see `scripts/harden.sh`)
3. Session cookies last 30 days; if you're being asked to log in
   constantly, check the system clock is correct (`timedatectl`) - a
   large clock skew can make the signed session cookie look invalid.

### Tuning recorder isn't producing files

1. Confirm `audio.raw_outdoor_mic` in config.yaml is set to your actual
   ALSA hardware input name (not `dt_aec_source` - the recorder wants
   the raw, pre-processing signal as a reference)
2. Check `Settings > Mic Tuning Recording` on the dashboard for a
   reported error
3. Check `logs/drivethru.log` (or `journalctl --user -u drivethru.service`)
   for `pw-cat` failures

## API Reference

All `/api/*` routes (and `/`) require a valid PIN session cookie;
unauthenticated requests get a `401`. `/login` and `/logout` are the
only public routes.

| Category | Endpoint | Method | Description |
|---|---|---|---|
| Auth | `/login` | GET/POST | Login page / submit PIN |
| Auth | `/logout` | POST | Clear session |
| Core | `/` | GET | Web dashboard |
| Core | `/api/state` | GET | Current lane/audio/volume state |
| Core | `/api/stats` | GET | Today's arrival stats |
| Core | `/api/settings` | GET | All current settings, for the dashboard |
| Audio | `/api/volume` | POST | Set a device's volume (persists to config.yaml) |
| Audio | `/api/mute` | POST | Set a device's mute state |
| Audio | `/api/mode` | POST | `full_duplex` or `ptt` |
| Audio | `/api/ptt` | POST | Push-to-talk state (PTT mode only) |
| Audio | `/api/test-audio` | POST | Play a test tone to a device |
| Audio | `/api/refresh-audio` | POST | Re-resolve PipeWire node IDs (after a restart) |
| Audio | `/api/audio-levels` | GET | Live per-device level meters |
| Audio | `/api/pipewire-nodes` | GET | List all available PipeWire nodes |
| Denoise | `/api/denoise-settings` | GET/POST | DeepFilterNet Attenuation/Beta, live |
| Tuning | `/api/tuning/hours` | GET | Recorded hours available to the Tuning Lab |
| Tuning | `/api/tuning/clip` | POST | Cut a short listenable clip |
| Tuning | `/api/tuning/candidate` | POST | Run DeepFilterNet offline with given settings |
| Tuning | `/api/tuning/audio/{token}` | GET | Serve a clip/candidate for playback |
| Recording | `/api/recording/status` | GET | Tuning recorder status |
| Recording | `/api/recording/start` | POST | Start recording (optionally time-limited) |
| Recording | `/api/recording/stop` | POST | Stop recording |
| Sensor | `/api/sensor-settings` | GET/POST | Detection band / hysteresis |
| Sensor | `/api/sensor-reset` | POST | Reset sensor connection |
| Bluetooth | `/api/bluetooth/scan` | GET | Scan for nearby devices |
| Bluetooth | `/api/bluetooth/devices` | GET | List paired devices |
| Bluetooth | `/api/bluetooth/connect` | POST | Connect to a device by MAC |
| Bluetooth | `/api/bluetooth/disconnect` | POST | Disconnect |
| Bluetooth | `/api/bluetooth/forget` | POST | Unpair |
| Chime | `/api/chime-settings` | GET/POST | Select which chime plays on arrival |
| Chime | `/api/chime-upload` | POST | Upload a custom chime |
| Diagnostics | `/api/logs` | GET | Recent log lines |

## Uninstalling

```bash
bash scripts/uninstall.sh
```

Removes the systemd service and deployed PipeWire configs. Leaves the
repo, `config.yaml`, recordings, and logs in place - delete those
manually if you want them gone too. Does not undo `scripts/harden.sh`
(fail2ban/firewall are host-level, not app-level).

## License

No LICENSE file is currently included in this repository - until one is
added, treat the source as all-rights-reserved rather than assuming any
particular open-source license applies.
