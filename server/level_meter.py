"""
Real-time audio level metering via PipeWire.

Runs a background pw-cat capture per monitored device (outdoor mic,
outdoor speaker, headset) and computes peak/RMS levels from the raw PCM,
so the dashboard's level meters reflect actual signal instead of a
simulation.
"""

import audioop
import logging
import subprocess
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

SAMPLE_RATE = 8000
CHUNK_SIZE = 800  # ~50ms of s16 mono @ 8kHz
RETRY_DELAY_SEC = 1.0


class DeviceLevelMonitor:
    """Captures a single device's monitor feed and tracks its current peak/RMS level."""

    def __init__(self, name: str, node_name: str):
        self.name = name
        self.node_name = node_name
        self._peak = 0.0
        self._rms = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._proc: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._proc:
            self._proc.terminate()
        if self._thread:
            self._thread.join(timeout=2)

    def set_target(self, node_name: str) -> None:
        """Change which node to capture from; restarts the capture process."""
        if node_name == self.node_name:
            return
        self.node_name = node_name
        if self._proc:
            self._proc.terminate()

    def _run(self) -> None:
        while not self._stop.is_set():
            if not self.node_name:
                time.sleep(RETRY_DELAY_SEC)
                continue

            try:
                self._proc = subprocess.Popen(
                    [
                        "pw-cat", "--record", "--target", self.node_name,
                        "--channels", "1", "--rate", str(SAMPLE_RATE), "--format", "s16", "-",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                )
                while not self._stop.is_set():
                    data = self._proc.stdout.read(CHUNK_SIZE)
                    if not data:
                        break
                    # Odd-length reads break audioop's 16-bit sample assumption
                    if len(data) % 2:
                        data = data[:-1]
                    if not data:
                        continue
                    peak = audioop.max(data, 2) / 32768.0
                    rms = audioop.rms(data, 2) / 32768.0
                    with self._lock:
                        self._peak = peak
                        self._rms = rms
            except FileNotFoundError:
                logger.error("pw-cat not found - is pipewire-bin installed?")
                return
            except Exception as e:
                logger.warning(f"Level monitor for {self.name} ({self.node_name}) error: {e}")
            finally:
                if self._proc:
                    self._proc.terminate()
                    self._proc = None

            with self._lock:
                self._peak = 0.0
                self._rms = 0.0

            if not self._stop.is_set():
                time.sleep(RETRY_DELAY_SEC)

    def get_level(self) -> dict:
        with self._lock:
            return {"peak": round(self._peak, 4), "rms": round(self._rms, 4)}


class LevelMeterManager:
    """Owns one DeviceLevelMonitor per named device."""

    def __init__(self):
        self._monitors: dict[str, DeviceLevelMonitor] = {}

    def start(self, devices: dict[str, str]) -> None:
        for name, node_name in devices.items():
            monitor = DeviceLevelMonitor(name, node_name)
            self._monitors[name] = monitor
            monitor.start()

    def stop(self) -> None:
        for monitor in self._monitors.values():
            monitor.stop()

    def update_targets(self, devices: dict[str, str]) -> None:
        for name, node_name in devices.items():
            if name in self._monitors:
                self._monitors[name].set_target(node_name)

    def get_levels(self) -> dict:
        return {name: monitor.get_level() for name, monitor in self._monitors.items()}


_manager: Optional[LevelMeterManager] = None


def get_level_meter() -> LevelMeterManager:
    global _manager
    if _manager is None:
        _manager = LevelMeterManager()
    return _manager


def init_level_meter(devices: dict[str, str]) -> LevelMeterManager:
    global _manager
    _manager = LevelMeterManager()
    _manager.start(devices)
    return _manager
