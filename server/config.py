"""Configuration loader for the drive-thru intercom system."""

import os
import re
from pathlib import Path
from typing import Any

import yaml


class Config:
    """Configuration container loaded from YAML."""

    def __init__(self, config_path: str | Path | None = None):
        if config_path is None:
            # Look for config.yaml in project root
            config_path = Path(__file__).parent.parent / "config.yaml"

        self._config_path = Path(config_path)
        self._data: dict[str, Any] = {}
        self.reload()

    def reload(self) -> None:
        """Reload configuration from disk."""
        if self._config_path.exists():
            with open(self._config_path, "r") as f:
                self._data = yaml.safe_load(f) or {}
        else:
            self._data = {}

    # Serial settings
    @property
    def serial_port(self) -> str:
        return self._data.get("serial", {}).get("port", "/dev/ttyUSB0")

    @property
    def serial_baudrate(self) -> int:
        return self._data.get("serial", {}).get("baudrate", 115200)

    @property
    def heartbeat_timeout_sec(self) -> float:
        return self._data.get("serial", {}).get("heartbeat_timeout_sec", 15.0)

    # Sensor settings
    @property
    def detect_min_cm(self) -> int:
        return self._data.get("sensor", {}).get("detect_min_cm", 50)

    @property
    def detect_max_cm(self) -> int:
        return self._data.get("sensor", {}).get("detect_max_cm", 100)

    @property
    def arrival_hold_sec(self) -> float:
        return self._data.get("sensor", {}).get("arrival_hold_sec", 2.0)

    @property
    def departure_hold_sec(self) -> float:
        return self._data.get("sensor", {}).get("departure_hold_sec", 3.0)

    @property
    def steady_sec(self) -> float:
        return self._data.get("sensor", {}).get("steady_sec", 1.0)

    def set_sensor_settings(
        self,
        detect_min_cm: int,
        detect_max_cm: int,
        arrival_hold_sec: float,
        departure_hold_sec: float,
        steady_sec: float,
    ) -> None:
        """Persist the car-detection band/hysteresis tuning to
        config.yaml, editing the lines in place so comments/formatting are
        preserved."""
        text = self._config_path.read_text()

        def _replace(field: str, value: float, text: str) -> str:
            pattern = re.compile(rf'^(\s*{field}:\s*).*$', re.MULTILINE)
            replacement = rf'\g<1>{value}'
            return pattern.sub(replacement, text, count=1) if pattern.search(text) else text

        text = _replace("detect_min_cm", detect_min_cm, text)
        text = _replace("detect_max_cm", detect_max_cm, text)
        text = _replace("arrival_hold_sec", arrival_hold_sec, text)
        text = _replace("departure_hold_sec", departure_hold_sec, text)
        text = _replace("steady_sec", steady_sec, text)
        self._config_path.write_text(text)
        self.reload()

    # Audio settings
    @property
    def outdoor_mic_node(self) -> str:
        return self._data.get("audio", {}).get("outdoor_mic", "dt_aec_source")

    @property
    def outdoor_speaker_node(self) -> str:
        return self._data.get("audio", {}).get("outdoor_speaker", "dt_aec_sink")

    @property
    def headset_sink_node(self) -> str:
        return self._data.get("audio", {}).get("headset_sink", "")

    @property
    def headset_source_node(self) -> str:
        return self._data.get("audio", {}).get("headset_source", "")

    @property
    def default_volumes(self) -> dict[str, float]:
        defaults = {
            "outdoor_mic": 1.0,
            "outdoor_speaker": 0.8,
            "headset": 1.0,
            "indoor_mic": 1.0,
        }
        # Merge rather than replace, so a config.yaml written before
        # indoor_mic existed still gets a sane default for it instead of a
        # missing key.
        defaults.update(self._data.get("audio", {}).get("default_volumes", {}))
        return defaults

    @property
    def default_audio_mode(self) -> str:
        return self._data.get("audio", {}).get("default_mode", "full_duplex")

    @property
    def chime_path(self) -> Path:
        path = self._data.get("audio", {}).get("chime_path", "server/assets/chime.wav")
        # Make relative to project root
        if not os.path.isabs(path):
            path = Path(__file__).parent.parent / path
        return Path(path)

    def set_chime_path(self, relative_path: str) -> None:
        """Persist which chime sound plays on car arrival (a preset or the
        uploaded custom.wav) to config.yaml, editing the line in place."""
        text = self._config_path.read_text()
        pattern = re.compile(r'^(\s*chime_path:\s*).*$', re.MULTILINE)
        replacement = rf'\g<1>"{relative_path}"'
        if pattern.search(text):
            text = pattern.sub(replacement, text, count=1)
        else:
            text += f'\naudio:\n  chime_path: "{relative_path}"\n'
        self._config_path.write_text(text)
        self.reload()

    # Denoise (DeepFilterNet) settings
    @property
    def denoise_attenuation_limit_db(self) -> float:
        return self._data.get("denoise", {}).get("attenuation_limit_db", 40.0)

    def set_denoise_attenuation_limit_db(self, value: float) -> None:
        """Persist the DeepFilterNet attenuation-limit tuning to config.yaml,
        editing the line in place so comments/formatting are preserved."""
        text = self._config_path.read_text()
        pattern = re.compile(r'^(\s*attenuation_limit_db:\s*).*$', re.MULTILINE)
        replacement = rf'\g<1>{value}'
        if pattern.search(text):
            text = pattern.sub(replacement, text, count=1)
        self._config_path.write_text(text)
        self.reload()

    # Server settings
    @property
    def server_host(self) -> str:
        return self._data.get("server", {}).get("host", "0.0.0.0")

    @property
    def server_port(self) -> int:
        return self._data.get("server", {}).get("port", 8080)

    def set_headset_nodes(self, sink: str, source: str) -> None:
        """
        Persist the headset sink/source node names to config.yaml, editing
        the two lines in place so comments and formatting are preserved,
        then reload the in-memory config.
        """
        text = self._config_path.read_text()

        def _replace(field: str, value: str, text: str) -> str:
            pattern = re.compile(rf'^(\s*{field}:\s*).*$', re.MULTILINE)
            replacement = rf'\g<1>"{value}"'
            if pattern.search(text):
                return pattern.sub(replacement, text, count=1)
            # Field missing entirely - append under the audio section
            return text

        text = _replace("headset_sink", sink, text)
        text = _replace("headset_source", source, text)
        self._config_path.write_text(text)
        self.reload()

    # Database settings
    @property
    def database_path(self) -> Path:
        path = self._data.get("database", {}).get("path", "drivethru.db")
        if not os.path.isabs(path):
            path = Path(__file__).parent.parent / path
        return Path(path)


# Global config instance
_config: Config | None = None


def get_config() -> Config:
    """Get the global config instance."""
    global _config
    if _config is None:
        _config = Config()
    return _config


def init_config(config_path: str | Path | None = None) -> Config:
    """Initialize the global config instance."""
    global _config
    _config = Config(config_path)
    return _config
