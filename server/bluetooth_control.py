"""
Bluetooth headset control via bluetoothctl.

Handles scanning, pairing, and connecting a staff Bluetooth headset,
then resolving the resulting PipeWire node names so audio_control can
route to it.
"""

import json
import logging
import re
import select as _select_mod
import subprocess
import time
from typing import Optional

logger = logging.getLogger(__name__)

MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")
_DEVICE_LINE_RE = re.compile(r"^Device\s+([0-9A-Fa-f:]{17})\s+(.*)$")

# Which Bluetooth controller (by its own MAC) every bluetoothctl call below
# should be pinned to - see set_adapter(). None means "trust bluez's own
# default controller", which is only safe with exactly one adapter present.
_adapter: Optional[str] = None


def set_adapter(mac: Optional[str]) -> None:
    """
    Pin every bluetoothctl interaction in this module to a specific
    controller, instead of relying on BlueZ's "default controller"
    tracking.

    Found the hard way: plugging in a second USB Bluetooth adapter made
    BlueZ silently switch its default controller to it - permanently, even
    after the new adapter was powered back off - so every one-shot
    `bluetoothctl <cmd> <mac>` call in this file (which never specified a
    controller) started transparently targeting the new, never-paired
    adapter instead of the one the headset was actually bonded to. No
    error surfaced at the time it flipped; it only showed up later as
    "Device ... not available" on every reconnect attempt, and as
    is_connected() reporting false even while audio was genuinely working
    over the correct adapter. Pass None to go back to trusting bluez's
    default (only correct with a single adapter in the system).
    """
    global _adapter
    _adapter = mac


def is_valid_mac(mac: str) -> bool:
    return bool(MAC_RE.match(mac))


_NODE_MAC_RE = re.compile(r"^bluez_(?:output|input)\.([0-9A-Fa-f_]{17})\.")


def mac_from_node_name(node_name: str) -> Optional[str]:
    """Extract 'AA:BB:CC:DD:EE:FF' from a bluez node name like
    'bluez_output.AA_BB_CC_DD_EE_FF.a2dp-sink'."""
    if not node_name:
        return None
    match = _NODE_MAC_RE.match(node_name)
    if not match:
        return None
    return match.group(1).replace("_", ":").upper()


# Commands whose real result is printed asynchronously, on their own
# timeline, well after the command itself is accepted - a period of no new
# output from these does NOT mean they're done (unlike e.g. "info" or
# "power", which reply synchronously and go quiet the instant they're
# finished). _run_scripted must not use its idle-quiet shortcut for these;
# it has to keep waiting (up to the full timeout) for one of its markers
# below instead.
#
# Markers are per-command, not a shared global set: bluetoothctl prints a
# "Connected: yes" property-change line as part of a *pair* operation too
# (pairing implicitly connects first), so a global marker list would let
# an in-flight pair stop early on that line and return failure, never
# reaching "Paired: yes"/"Pairing successful" - confirmed live, this
# exact bug shipped once already. Each command only reacts to its own
# markers.
_ASYNC_MARKERS = {
    "connect": ("Connection successful", "already connected", "Connected: yes", "Failed to connect", "org.bluez.Error"),
    "pair": ("Pairing successful", "already paired", "Failed to pair", "org.bluez.Error"),
    "disconnect": ("Successful disconnected", "Connected: no", "Failed to disconnect", "org.bluez.Error"),
}


def _run_scripted(commands: list[str], timeout: float) -> str:
    """
    Run one or more bluetoothctl commands in a single interactive session
    (piped through stdin) and return everything it printed.

    This exists only because bluetoothctl's one-shot CLI form
    (`bluetoothctl <cmd> <args>`) has no `--adapter`/`-a` flag (checked:
    `bluetoothctl --help` - only "select" as an in-session command
    selects a controller) and doesn't accept multiple commands as argv
    either (checked: `bluetoothctl select X connect Y` -> "Too many
    arguments") - so combining "select <adapter>" with the real command
    requires a scripted interactive session.

    The subtlety that makes this more than a one-line pipe: writing the
    whole script to stdin and then hitting EOF makes bluetoothctl quit
    immediately once it's *accepted* an async command like "connect",
    before that command's actual result line has printed - so an early,
    naive version of this raced every connect/pair call and always
    reported failure. Fixed by watching the output as it streams in:
    stop as soon as a recognized terminal marker for connect/pair/
    disconnect appears, otherwise (synchronous commands like info/power/
    devices) stop once output goes quiet for a short moment past a
    minimum settle time - and only ever fall back to the full `timeout`
    as a last resort.
    """
    # "select <adapter>" is never the operative command - find the real
    # one to know which markers (if any) apply.
    op_command = next((cmd.split()[0] for cmd in commands if cmd.split() and cmd.split()[0] != "select"), None)
    markers = _ASYNC_MARKERS.get(op_command, ())
    is_async = op_command in _ASYNC_MARKERS
    proc = subprocess.Popen(
        ["bluetoothctl"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, bufsize=1,
    )
    output: list[str] = []
    start = time.monotonic()
    deadline = start + timeout
    last_data_at = start
    try:
        proc.stdin.write("\n".join(commands) + "\n")
        proc.stdin.flush()

        while True:
            now = time.monotonic()
            if now >= deadline:
                break
            ready, _, _ = _select_mod.select([proc.stdout], [], [], min(0.3, deadline - now))
            if ready:
                line = proc.stdout.readline()
                if line == "":
                    break  # bluetoothctl exited on its own
                output.append(line)
                last_data_at = time.monotonic()
                if markers and any(marker in line for marker in markers):
                    break
            elif not is_async and (now - last_data_at > 0.5) and (now - start > 0.3):
                break
    finally:
        try:
            proc.stdin.write("quit\n")
            proc.stdin.flush()
        except Exception:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    return "".join(output)


def _run(args: list[str], timeout: float = 10) -> subprocess.CompletedProcess:
    """Run a one-shot bluetoothctl command, pinned to _adapter if set."""
    if _adapter:
        stdout = _run_scripted([f"select {_adapter}", " ".join(args)], timeout=timeout)
        return subprocess.CompletedProcess(args=["bluetoothctl", *args], returncode=0, stdout=stdout, stderr="")
    return subprocess.run(
        ["bluetoothctl", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _parse_device_lines(output: str) -> dict[str, str]:
    """Parse 'Device XX:XX:XX:XX:XX:XX Name' lines into {mac: name}."""
    devices: dict[str, str] = {}
    for line in output.splitlines():
        line = line.strip()
        # Strip bluetoothctl color codes and [NEW]/[CHG] prefixes
        line = re.sub(r"\x1b\[[0-9;]*m", "", line)
        line = re.sub(r"^\[(NEW|CHG|DEL)\]\s*", "", line)
        match = _DEVICE_LINE_RE.match(line)
        if match:
            devices[match.group(1)] = match.group(2)
    return devices


def ensure_powered() -> None:
    """Make sure the Bluetooth adapter is powered on."""
    try:
        _run(["power", "on"], timeout=5)
    except Exception as e:
        logger.warning(f"Failed to power on Bluetooth adapter: {e}")


def scan(duration: float = 8.0) -> list[dict]:
    """Scan for nearby Bluetooth devices for `duration` seconds."""
    ensure_powered()
    devices: dict[str, str] = {}

    try:
        if _adapter:
            # The one-shot `--timeout scan on` form can't also select a
            # controller first (see _run_scripted's docstring), and
            # scanning needs a real wall-clock wait, not just a scripted
            # command sequence - so this drives bluetoothctl interactively
            # instead, with its own explicit sleep rather than
            # _run_scripted's marker/idle detection (scan output is
            # sporadic CHG/NEW lines the whole time, not a single settling
            # result).
            proc = subprocess.Popen(
                ["bluetoothctl"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True,
            )
            try:
                proc.stdin.write(f"select {_adapter}\npower on\nscan on\n")
                proc.stdin.flush()
                time.sleep(duration)
                proc.stdin.write("devices\nscan off\n")
                proc.stdin.close()
                stdout, _ = proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, _ = proc.communicate()
            devices.update(_parse_device_lines(stdout))
        else:
            result = _run(["--timeout", str(int(duration)), "scan", "on"], timeout=duration + 5)
            devices.update(_parse_device_lines(result.stdout))
    except subprocess.TimeoutExpired:
        logger.warning("Bluetooth scan timed out")
    except Exception as e:
        logger.error(f"Bluetooth scan failed: {e}")

    # Merge in anything already known to bluez (paired or previously seen)
    try:
        result = _run(["devices"], timeout=5)
        devices.update({
            mac: name for mac, name in _parse_device_lines(result.stdout).items()
            if mac not in devices
        })
    except Exception as e:
        logger.warning(f"Failed to list known devices: {e}")

    paired = set(list_paired().keys())
    return [
        {"mac": mac, "name": name, "paired": mac in paired}
        for mac, name in sorted(devices.items(), key=lambda kv: kv[1].lower())
    ]


def list_paired() -> dict[str, str]:
    """List paired devices as {mac: name}."""
    try:
        result = _run(["paired-devices"], timeout=5)
        return _parse_device_lines(result.stdout)
    except Exception as e:
        logger.warning(f"Failed to list paired devices: {e}")
        return {}


def device_info(mac: str) -> dict:
    """Get Paired/Trusted/Connected state and name for a device."""
    info = {"mac": mac, "name": mac, "paired": False, "trusted": False, "connected": False}
    if not is_valid_mac(mac):
        return info
    try:
        result = _run(["info", mac], timeout=5)
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("Name:"):
                info["name"] = line.split(":", 1)[1].strip()
            elif line.startswith("Alias:") and info["name"] == mac:
                info["name"] = line.split(":", 1)[1].strip()
            elif line.startswith("Paired:"):
                info["paired"] = "yes" in line
            elif line.startswith("Trusted:"):
                info["trusted"] = "yes" in line
            elif line.startswith("Connected:"):
                info["connected"] = "yes" in line
    except Exception as e:
        logger.warning(f"Failed to get info for {mac}: {e}")

    # Only worth the extra pw-dump lookup for a device that's actually
    # ACL-connected - see is_audio_ready()'s docstring for why "Connected"
    # alone doesn't mean audio actually works yet. Uses
    # _pipewire_profile_ready() directly (not is_audio_ready()) since that
    # calls is_connected() -> device_info() and would recurse forever.
    info["audio_ready"] = _pipewire_profile_ready(mac) if info["connected"] else False
    return info


def pair(mac: str) -> tuple[bool, str]:
    """Pair, then trust, a device. Idempotent if already paired."""
    if not is_valid_mac(mac):
        return False, "Invalid MAC address"

    ensure_powered()
    try:
        _run(["pairable", "on"], timeout=5)
        result = _run(["pair", mac], timeout=20)
        output = result.stdout + result.stderr
        already_paired = "already" in output.lower() and "paired" in output.lower()
        if "Pairing successful" not in output and not already_paired:
            return False, output.strip() or "Pairing failed"

        trust_result = _run(["trust", mac], timeout=10)
        return True, (trust_result.stdout + result.stdout).strip()
    except subprocess.TimeoutExpired:
        return False, "Pairing timed out (is the headset in pairing mode?)"
    except Exception as e:
        return False, str(e)


def is_connected(mac: str) -> bool:
    """Quick current-connection check for a device (used by the background
    auto-reconnect monitor to decide whether to act)."""
    return device_info(mac).get("connected", False)


def _pipewire_profile_ready(mac: str) -> bool:
    """Whether PipeWire has created this device's Device object and
    settled on the headset-head-unit profile. Assumes the caller has
    already confirmed the BlueZ radio link is connected - doesn't check
    that itself, so this alone is never enough to say "ready" (see
    is_audio_ready(), the public version of that combined check).

    Split out from is_audio_ready() so device_info() can reuse just this
    half without calling back into is_connected() -> device_info() and
    recursing forever."""
    device_id = _get_pipewire_device_id(mac)
    if device_id is None:
        return False
    current_profile = _get_current_profile_name(device_id)
    return bool(current_profile) and current_profile.startswith("headset-head-unit")


def is_audio_ready(mac: str) -> bool:
    """
    Whether the headset isn't just BlueZ-connected (the radio/ACL link is
    up) but actually has a working audio path: PipeWire's bluez5 backend
    has created the Device object for it AND it's on the headset-head-unit
    (HSP/HFP) profile, so the mic/speaker nodes actually exist.

    bluetoothctl can report "Connected: yes" for a noticeable stretch
    before PipeWire catches up and creates its side of things - the
    dashboard showing "Connected" during that gap while no audio can
    actually flow yet is exactly the "connected" (ACL) vs. "connected"
    (usable) distinction this function exists to close. Use this instead
    of is_connected() anywhere audio is about to be attempted or the
    result is shown to staff as "ready to talk", not just is_connected()'s
    bare radio-link check.
    """
    return is_connected(mac) and _pipewire_profile_ready(mac)


def connect(mac: str) -> tuple[bool, str]:
    """Connect to an already-paired/trusted device.

    br-connection-profile-unavailable is a known-transient BlueZ error:
    it fires when a connect is attempted while BlueZ is still tearing
    down/registering profile plugins from a just-finished disconnect or
    profile switch, and normally clears within a couple of seconds. Retry
    a couple of times internally so a single button press (or monitor
    tick) succeeds instead of surfacing that as a hard failure.
    """
    if not is_valid_mac(mac):
        return False, "Invalid MAC address"

    # bluetoothctl's one-shot CLI form ("bluetoothctl connect <mac>") has
    # its own fast path for an already-connected device and prints
    # "already connected" right away; the scripted interactive session
    # _run uses when _adapter is pinned (see _run_scripted) doesn't get
    # that special-casing - asking it to "connect" a device that's
    # already connected can print nothing further at all, burning the
    # full timeout for no reason. Cheap to just check first.
    if is_connected(mac):
        force_headset_profile(mac)
        return True, "already connected"

    last_output = "Connect failed"
    for attempt in range(3):
        try:
            result = _run(["connect", mac], timeout=20)
            output = result.stdout + result.stderr
            if ("Connection successful" in output or "already connected" in output.lower()
                    or "Connected: yes" in output):
                force_headset_profile(mac)
                return True, output.strip()
            last_output = output.strip() or last_output
        except subprocess.TimeoutExpired:
            last_output = "Connect timed out"
        except Exception as e:
            last_output = str(e)

        if "profile-unavailable" in last_output.lower() and attempt < 2:
            time.sleep(2.0)
            continue
        break

    return False, last_output


def _get_current_profile_name(device_id: int) -> Optional[str]:
    """Read the PipeWire device's currently-active profile name (not the
    enum of available ones) via its 'Profile' param."""
    try:
        result = subprocess.run(
            ["pw-cli", "enum-params", str(device_id), "Profile"],
            capture_output=True, text=True, timeout=5,
        )
        match = re.search(r'name[^\n]*\n\s*String "([^"]+)"', result.stdout)
        if match:
            return match.group(1)
    except Exception as e:
        logger.warning(f"Failed to read current profile for device {device_id}: {e}")
    return None


def _get_pipewire_device_id(mac: str) -> Optional[int]:
    """Find the PipeWire device (card) id for a bluez MAC address."""
    try:
        result = subprocess.run(["pw-dump"], capture_output=True, text=True, timeout=5)
        nodes = json.loads(result.stdout)
        for obj in nodes:
            if obj.get("type") != "PipeWire:Interface:Device":
                continue
            props = obj.get("info", {}).get("props", {})
            if props.get("api.bluez5.address", "").upper() == mac.upper():
                return obj.get("id")
    except Exception as e:
        logger.warning(f"Failed to find PipeWire device for {mac}: {e}")
    return None


_PROFILE_BLOCK_RE = re.compile(
    r"Profile:index[^\n]*\n\s*Int (\d+).*?Profile:name[^\n]*\n\s*String \"([^\"]+)\"",
    re.DOTALL,
)


def _get_profile_index(device_id: int, preferred_names: list[str]) -> Optional[int]:
    """Look up a PipeWire device's profile index by name, in preference order."""
    try:
        result = subprocess.run(
            ["pw-cli", "enum-params", str(device_id), "EnumProfile"],
            capture_output=True, text=True, timeout=5,
        )
        by_name = {}
        for block in re.split(r"\n(?=  Object: size)", result.stdout):
            match = _PROFILE_BLOCK_RE.search(block)
            if match:
                by_name[match.group(2)] = int(match.group(1))
        for name in preferred_names:
            if name in by_name:
                return by_name[name]
    except Exception as e:
        logger.warning(f"Failed to enumerate profiles for device {device_id}: {e}")
    return None


def force_headset_profile(mac: str) -> bool:
    """
    Switch a connected Bluetooth device to the HSP/HFP headset-head-unit
    profile so its mic (source) node is exposed. PipeWire defaults newly
    connected devices to A2DP-sink (output-only, no mic), and this
    WirePlumber version (0.4.x) doesn't honor declarative profile-pinning
    rules, so it has to be done explicitly after every connect.

    Idempotent: does nothing if already on a headset-head-unit* profile.
    This matters because it's called both right after connect() succeeds
    and again by the background reconnect monitor - re-issuing
    wpctl set-profile on an already-correct profile still makes PipeWire
    tear down and renegotiate the Bluetooth transport, and on this headset
    (M890BT) that renegotiation was observed to itself trigger a real
    disconnect a few seconds later (seen as the connect/disconnect flap
    with br-connection-profile-unavailable on the next attempt). Skipping
    the redundant call removes that self-inflicted flap.
    """
    device_id = _get_pipewire_device_id(mac)
    if device_id is None:
        logger.warning(f"No PipeWire device found for {mac} yet")
        return False

    current = _get_current_profile_name(device_id)
    if current and current.startswith("headset-head-unit"):
        return True

    profile_index = _get_profile_index(
        device_id, ["headset-head-unit", "headset-head-unit-msbc", "headset-head-unit-cvsd"]
    )
    if profile_index is None:
        logger.warning(f"No headset-head-unit profile available for {mac}")
        return False

    try:
        subprocess.run(
            ["wpctl", "set-profile", str(device_id), str(profile_index)],
            capture_output=True, text=True, timeout=5, check=True,
        )
        return True
    except Exception as e:
        logger.error(f"Failed to set headset profile for {mac}: {e}")
        return False


def disconnect(mac: str) -> tuple[bool, str]:
    if not is_valid_mac(mac):
        return False, "Invalid MAC address"
    try:
        result = _run(["disconnect", mac], timeout=10)
        return result.returncode == 0, (result.stdout + result.stderr).strip()
    except Exception as e:
        return False, str(e)


def forget(mac: str) -> tuple[bool, str]:
    """Unpair and remove a device."""
    if not is_valid_mac(mac):
        return False, "Invalid MAC address"
    try:
        result = _run(["remove", mac], timeout=10)
        return result.returncode == 0, (result.stdout + result.stderr).strip()
    except Exception as e:
        return False, str(e)


def find_headset_nodes(mac: str, retries: int = 5, delay: float = 1.0) -> tuple[Optional[str], Optional[str]]:
    """
    After connecting, find the PipeWire sink/source node names for this
    headset by matching its MAC (colons -> underscores) against bluez
    node names. Retries briefly since PipeWire takes a moment to expose
    the nodes after a Bluetooth connection completes.
    """
    mac_key = mac.replace(":", "_").upper()
    sink_name: Optional[str] = None
    source_name: Optional[str] = None

    for _ in range(retries):
        try:
            result = subprocess.run(["pw-dump"], capture_output=True, text=True, timeout=5)
            nodes = json.loads(result.stdout)
            for node in nodes:
                if node.get("type") != "PipeWire:Interface:Node":
                    continue
                props = node.get("info", {}).get("props", {})
                name = props.get("node.name", "")
                if not name.upper().startswith(f"BLUEZ_OUTPUT.{mac_key}") and \
                   not name.upper().startswith(f"BLUEZ_INPUT.{mac_key}"):
                    continue
                media_class = props.get("media.class", "")
                if "bluez_output" in name.lower() and media_class == "Audio/Sink":
                    sink_name = name
                elif "bluez_input" in name.lower() and media_class == "Audio/Source":
                    source_name = name
        except Exception as e:
            logger.warning(f"Failed to query pw-dump: {e}")

        if sink_name or source_name:
            break
        time.sleep(delay)

    return sink_name, source_name
