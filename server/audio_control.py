"""
Audio control via PipeWire (wpctl/pw-dump).

Handles volume control, muting, and PTT (push-to-talk) mode.
"""

import json
import logging
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

from .models import AudioMode

logger = logging.getLogger(__name__)

# The loopback stream module-loopback creates for outdoor-mic -> headset
# audio (see pipewire/99-drivethru-aec.conf). Gating this specific node lets
# voice detection duck wind/engine noise to the headset independently of the
# user's manual outdoor-mic mute button.
MIC_TO_HEADSET_NODE = "dt_loopback_mic_playback"

# The DeepFilterNet filter-chain's capture-side node (see
# pipewire/97-drivethru-deepfilter.conf) - this is the one that carries the
# LADSPA control ports as live-settable Props, not the "dt_denoised_source"
# output side. Its LADSPA node was named "deepfilter" in that config, which
# is why PipeWire prefixes every control port name with "deepfilter:".
DENOISE_NODE_NAME = "dt_deepfilter_capture"
DENOISE_ATTEN_PORT = "deepfilter:Attenuation Limit (dB)"


class AudioController:
    """Controls audio routing and volume via PipeWire."""

    def __init__(
        self,
        outdoor_mic_node: str,
        outdoor_speaker_node: str,
        headset_sink_node: str,
        headset_source_node: str,
        default_volumes: Optional[dict[str, float]] = None,
    ):
        self.outdoor_mic_node = outdoor_mic_node
        self.outdoor_speaker_node = outdoor_speaker_node
        self.headset_sink_node = headset_sink_node
        self.headset_source_node = headset_source_node

        # Current state
        self.volumes: dict[str, float] = default_volumes or {
            "outdoor_mic": 1.0,
            "outdoor_speaker": 0.8,
            "headset": 1.0,
            "indoor_mic": 1.0,
        }
        self.volumes.setdefault("indoor_mic", 1.0)
        self.muted: dict[str, bool] = {
            "outdoor_mic": False,
            "outdoor_speaker": False,
            "headset": False,
            "indoor_mic": False,
        }
        self.mode: AudioMode = AudioMode.FULL_DUPLEX
        self.ptt_active: bool = False

        # Voice-gated mic->headset: when enabled, mute the mic->headset
        # loopback unless voice_detector says someone is actually talking.
        self.voice_gate_enabled: bool = False

        # Node ID cache (node name -> ID)
        self._node_ids: dict[str, Optional[int]] = {}

    def _run_command(self, cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
        """Run a command and handle errors gracefully."""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5,
                check=check,
            )
            return result
        except subprocess.TimeoutExpired:
            logger.warning(f"Command timed out: {' '.join(cmd)}")
            raise
        except subprocess.CalledProcessError as e:
            logger.warning(f"Command failed: {' '.join(cmd)}: {e.stderr}")
            raise
        except FileNotFoundError:
            logger.error(f"Command not found: {cmd[0]}")
            raise

    def _cached_id_still_valid(self, node_name: str, node_id: int) -> bool:
        """
        Confirm a cached node ID still actually refers to node_name.

        PipeWire reassigns IDs from scratch on every PipeWire/WirePlumber
        restart, so a cached ID from before a restart can silently end up
        pointing at a completely different live node afterwards (e.g. the
        outdoor speaker instead of the outdoor mic) - and a volume/mute call
        would then silently hit the wrong device with no error at all. This
        is a cheap single-object check (not a full pw-dump) done before
        trusting a cached ID.
        """
        try:
            result = self._run_command(["pw-cli", "info", str(node_id)], check=True)
            return f'node.name = "{node_name}"' in result.stdout
        except Exception:
            return False

    def _get_node_id(self, node_name: str, retries: int = 3) -> Optional[int]:
        """Get PipeWire node ID by name using pw-dump."""
        if node_name in self._node_ids:
            cached_id = self._node_ids[node_name]
            if cached_id is None or self._cached_id_still_valid(node_name, cached_id):
                return cached_id
            logger.warning(
                f"Cached node ID {cached_id} for {node_name} no longer matches "
                f"(PipeWire/WirePlumber likely restarted) - re-resolving by name"
            )
            del self._node_ids[node_name]

        for attempt in range(retries):
            try:
                result = self._run_command(["pw-dump"], check=True)
                nodes = json.loads(result.stdout)

                for node in nodes:
                    if node.get("type") == "PipeWire:Interface:Node":
                        props = node.get("info", {}).get("props", {})
                        name = props.get("node.name", "")
                        if name == node_name:
                            node_id = node.get("id")
                            self._node_ids[node_name] = node_id
                            return node_id

                logger.warning(f"Node not found: {node_name}")
                self._node_ids[node_name] = None
                return None

            except json.JSONDecodeError as e:
                # pw-dump can return a truncated snapshot if the graph is
                # still settling right after PipeWire/WirePlumber start -
                # retry briefly rather than failing the whole lookup.
                if attempt + 1 < retries:
                    logger.warning(f"pw-dump returned malformed JSON (attempt {attempt + 1}/{retries}): {e}")
                    time.sleep(0.5)
                    continue
                logger.error(f"Failed to get node ID for {node_name}: {e}")
                return None
            except Exception as e:
                logger.error(f"Failed to get node ID for {node_name}: {e}")
                return None

        return None

    def refresh_node_ids(self) -> None:
        """Clear node ID cache and refresh."""
        self._node_ids.clear()

    def _set_volume(self, node_name: str, volume: float) -> bool:
        """Set volume for a node (0.0 - 1.5)."""
        node_id = self._get_node_id(node_name)
        if node_id is None:
            return False

        try:
            # wpctl uses percentage, so 1.0 = 100%
            self._run_command(
                ["wpctl", "set-volume", str(node_id), f"{volume:.2f}"],
                check=True
            )
            return True
        except Exception as e:
            logger.error(f"Failed to set volume for {node_name}: {e}")
            return False

    def _set_mute(self, node_name: str, muted: bool) -> bool:
        """Set mute state for a node."""
        node_id = self._get_node_id(node_name)
        if node_id is None:
            return False

        try:
            state = "1" if muted else "0"
            self._run_command(
                ["wpctl", "set-mute", str(node_id), state],
                check=True
            )
            return True
        except Exception as e:
            logger.error(f"Failed to set mute for {node_name}: {e}")
            return False

    def set_outdoor_mic_volume(self, volume: float) -> bool:
        """Set outdoor microphone volume."""
        if self._set_volume(self.outdoor_mic_node, volume):
            self.volumes["outdoor_mic"] = volume
            return True
        return False

    def set_outdoor_speaker_volume(self, volume: float) -> bool:
        """Set outdoor speaker volume."""
        if self._set_volume(self.outdoor_speaker_node, volume):
            self.volumes["outdoor_speaker"] = volume
            return True
        return False

    def set_headset_volume(self, volume: float) -> bool:
        """
        Set headset volume - the staff's EARS only (headset_sink_node, i.e.
        what plays into the headset). This is deliberately independent of
        the staff's mic (see set_indoor_mic_volume) - they used to be
        bundled together under one "headset" control, which meant turning
        down how loud the customer sounded in the headset also silently
        turned down how loud the staff's own voice went out to the
        customer. Split so each control only touches the one device it's
        labeled for.
        """
        if self._set_volume(self.headset_sink_node, volume):
            self.volumes["headset"] = volume
            return True
        return False

    def set_indoor_mic_volume(self, volume: float) -> bool:
        """Set indoor mic volume - the staff headset's MIC only (headset_source_node)."""
        if self._set_volume(self.headset_source_node, volume):
            self.volumes["indoor_mic"] = volume
            return True
        return False

    def set_volume(self, device: str, volume: float) -> bool:
        """Set volume for a named device."""
        volume = max(0.0, min(1.5, volume))  # Clamp to valid range

        if device == "outdoor_mic":
            return self.set_outdoor_mic_volume(volume)
        elif device == "outdoor_speaker":
            return self.set_outdoor_speaker_volume(volume)
        elif device == "headset":
            return self.set_headset_volume(volume)
        elif device == "indoor_mic":
            return self.set_indoor_mic_volume(volume)
        else:
            logger.warning(f"Unknown device: {device}")
            return False

    def set_mute(self, device: str, muted: bool) -> bool:
        """Set mute state for a named device."""
        if device == "outdoor_mic":
            success = self._set_mute(self.outdoor_mic_node, muted)
        elif device == "outdoor_speaker":
            success = self._set_mute(self.outdoor_speaker_node, muted)
        elif device == "headset":
            # Sink only (staff's ears) - see set_headset_volume's docstring
            # for why this no longer also touches the mic side.
            success = self._set_mute(self.headset_sink_node, muted)
        elif device == "indoor_mic":
            success = self._set_mute(self.headset_source_node, muted)
        else:
            logger.warning(f"Unknown device: {device}")
            return False

        if success:
            self.muted[device] = muted
        return success

    def set_mode(self, mode: AudioMode) -> bool:
        """Set audio mode (full_duplex or ptt)."""
        self.mode = mode

        if mode == AudioMode.FULL_DUPLEX:
            # Unmute everything
            self._set_mute(self.outdoor_mic_node, False)
            self._set_mute(self.outdoor_speaker_node, False)
            self.ptt_active = False
        else:
            # PTT mode: mute outdoor mic by default (staff not talking)
            self._set_mute(self.outdoor_mic_node, True)
            self._set_mute(self.outdoor_speaker_node, False)
            self.ptt_active = False

        return True

    def set_ptt(self, active: bool) -> bool:
        """
        Set push-to-talk state (only relevant in PTT mode).

        When PTT is active:
          - Outdoor speaker is unmuted (staff voice goes out)
          - Outdoor mic is muted (prevent echo/feedback)

        When PTT is inactive:
          - Outdoor speaker is muted (staff not talking)
          - Outdoor mic is unmuted (hear customer)
        """
        if self.mode != AudioMode.PTT:
            return False

        self.ptt_active = active

        if active:
            # Talking: mute customer mic, unmute speaker
            self._set_mute(self.outdoor_mic_node, True)
            self._set_mute(self.outdoor_speaker_node, False)
        else:
            # Listening: unmute customer mic, mute speaker
            self._set_mute(self.outdoor_mic_node, False)
            self._set_mute(self.outdoor_speaker_node, True)

        return True

    def _play_sound_fire_and_forget(self, sink: str, sound_path: Path, timeout: float = 10.0) -> bool:
        """
        Play a sound file to a sink without blocking the caller. Unlike a
        bare Popen() (which leaks a zombie process once pw-play exits, and
        can leave a permanently stuck process if pw-play ever hangs - e.g.
        PipeWire restarting mid-playback), this reaps the child in a
        background thread and kills it if it runs past `timeout`.
        """
        try:
            proc = subprocess.Popen(
                ["pw-play", "--target", sink, str(sound_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            logger.error(f"Failed to start pw-play for {sink}: {e}")
            return False

        def _reap():
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                logger.warning(f"pw-play to {sink} exceeded {timeout}s, killing it")
                proc.kill()
                proc.wait()

        threading.Thread(target=_reap, daemon=True).start()
        return True

    def play_chime(self, chime_path: Path, headset_sink: Optional[str] = None) -> bool:
        """Play a chime sound to the headset."""
        if not chime_path.exists():
            logger.warning(f"Chime file not found: {chime_path}")
            return False

        sink = headset_sink or self.headset_sink_node
        if not sink:
            logger.warning("No headset sink configured for chime")
            return False

        return self._play_sound_fire_and_forget(sink, chime_path)

    def play_test_sound(self, device: str, sound_path: Path) -> bool:
        """Play a test sound to a specific output device (outdoor_speaker or headset)."""
        if not sound_path.exists():
            logger.warning(f"Test sound file not found: {sound_path}")
            return False

        if device == "outdoor_speaker":
            sink = self.outdoor_speaker_node
        elif device == "headset":
            sink = self.headset_sink_node
        else:
            logger.warning(f"Unknown output device: {device}")
            return False

        if not sink:
            logger.warning(f"No sink configured for {device}")
            return False

        return self._play_sound_fire_and_forget(sink, sound_path)

    def set_denoise_attenuation(self, atten_db: float) -> bool:
        """
        Live-tune the DeepFilterNet outdoor-mic noise suppression without a
        PipeWire restart. 0 = fully bypassed (no suppression), 100 = full/
        unlimited suppression (this cut speech mid-word in testing - avoid).
        No-op (returns False) if the filter isn't loaded, e.g. running
        against an older PipeWire config that predates 97-drivethru-deepfilter.conf.
        """
        atten_db = max(0.0, min(100.0, atten_db))
        node_id = self._get_node_id(DENOISE_NODE_NAME)
        if node_id is None:
            logger.warning(f"Denoise node {DENOISE_NODE_NAME} not found - is 97-drivethru-deepfilter.conf loaded?")
            return False

        try:
            self._run_command(
                ["pw-cli", "set-param", str(node_id), "Props",
                 f'{{ params = [ "{DENOISE_ATTEN_PORT}" {atten_db:.1f} ] }}'],
                check=True,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to set denoise attenuation: {e}")
            return False

    def get_denoise_attenuation(self) -> Optional[float]:
        """Read the DeepFilterNet node's current live Attenuation Limit (dB), if loaded."""
        node_id = self._get_node_id(DENOISE_NODE_NAME)
        if node_id is None:
            return None
        try:
            result = self._run_command(["pw-cli", "enum-params", str(node_id), "Props"], check=True)
            # Output has two "Props" objects; the second carries the LADSPA
            # controls as alternating String/Float lines in a "params" Struct.
            lines = result.stdout.splitlines()
            for i, line in enumerate(lines):
                if DENOISE_ATTEN_PORT in line:
                    value_line = lines[i + 1].strip()
                    if value_line.startswith("Float"):
                        return float(value_line.split()[1])
        except Exception as e:
            logger.warning(f"Failed to read denoise attenuation: {e}")
        return None

    def set_voice_gate_enabled(self, enabled: bool) -> None:
        """Enable/disable voice-gating. Disabling always leaves the mic->headset path open."""
        self.voice_gate_enabled = enabled
        if not enabled:
            self._set_mute(MIC_TO_HEADSET_NODE, False)

    def apply_voice_gate(self, voice_detected: bool) -> bool:
        """Mute/unmute the mic->headset loopback based on voice detection (no-op if disabled)."""
        if not self.voice_gate_enabled:
            return True
        return self._set_mute(MIC_TO_HEADSET_NODE, not voice_detected)

    def apply_initial_settings(self) -> None:
        """Apply initial volume and mode settings."""
        for device, volume in self.volumes.items():
            self.set_volume(device, volume)
        self.set_mode(self.mode)


# Global audio controller instance
_audio: Optional[AudioController] = None


def get_audio_controller() -> AudioController:
    """Get the global audio controller instance."""
    global _audio
    if _audio is None:
        from .config import get_config
        config = get_config()
        _audio = AudioController(
            outdoor_mic_node=config.outdoor_mic_node,
            outdoor_speaker_node=config.outdoor_speaker_node,
            headset_sink_node=config.headset_sink_node,
            headset_source_node=config.headset_source_node,
            default_volumes=config.default_volumes,
        )
    return _audio


def init_audio_controller(
    outdoor_mic_node: str,
    outdoor_speaker_node: str,
    headset_sink_node: str,
    headset_source_node: str,
    default_volumes: Optional[dict[str, float]] = None,
) -> AudioController:
    """Initialize the global audio controller instance."""
    global _audio
    _audio = AudioController(
        outdoor_mic_node=outdoor_mic_node,
        outdoor_speaker_node=outdoor_speaker_node,
        headset_sink_node=headset_sink_node,
        headset_source_node=headset_source_node,
        default_volumes=default_volumes,
    )
    return _audio
