"""
Demo mode backend for GUI preview.

Provides mock data so the GUI can run without the real backend.
Use this for testing on Windows or previewing the UI.
"""

import random
from datetime import datetime
from typing import Optional, Callable
from dataclasses import dataclass, field


@dataclass
class DemoStats:
    """Mock statistics."""
    cars_today: int = 12
    avg_service_time_sec: float = 47.5
    total_cars_all_time: int = 1547


@dataclass
class DemoConfig:
    """Mock configuration."""
    detect_threshold_cm: int = 150
    serial_port: str = "DEMO"
    chime_enabled: bool = True


class DemoPresenceFilter:
    """Mock presence filter for demo mode."""

    def __init__(
        self,
        threshold_cm: int = 150,
        on_car_arrived: Optional[Callable[[], None]] = None,
        on_car_left: Optional[Callable[[float], None]] = None,
    ):
        self.threshold_cm = threshold_cm
        self.on_car_arrived = on_car_arrived
        self.on_car_left = on_car_left
        self._car_present = False
        self._car_arrived_at: Optional[datetime] = None
        self._last_distance_cm = 200

    @property
    def last_distance_cm(self) -> int:
        return self._last_distance_cm

    @property
    def is_car_present(self) -> bool:
        return self._car_present

    def process_event(self, event: str):
        """Process simulated events."""
        if event == "CAR_ARRIVED":
            self._car_present = True
            self._car_arrived_at = datetime.now()
            self._last_distance_cm = random.randint(80, 140)
            if self.on_car_arrived:
                self.on_car_arrived()
        elif event == "CAR_LEFT":
            duration = 0.0
            if self._car_arrived_at:
                duration = (datetime.now() - self._car_arrived_at).total_seconds()
            self._car_present = False
            self._car_arrived_at = None
            self._last_distance_cm = random.randint(250, 350)
            if self.on_car_left:
                self.on_car_left(duration)

    def simulate_distance(self):
        """Simulate random distance fluctuations."""
        if self._car_present:
            self._last_distance_cm = random.randint(80, 140)
        else:
            self._last_distance_cm = random.randint(250, 350)


class DemoSerialListener:
    """Mock serial listener for demo mode."""

    def __init__(self):
        self.is_sensor_online = True
        self.last_distance = 200

    def start(self):
        pass

    def stop(self):
        pass


class DemoAudioController:
    """Mock audio controller for demo mode."""

    def __init__(self):
        self.volumes = {
            "outdoor_mic": 1.0,
            "outdoor_speaker": 0.8,
            "headset": 1.0,
        }
        self.muted = {
            "outdoor_mic": False,
            "outdoor_speaker": False,
            "headset": False,
        }
        self.mode = "full_duplex"
        self.ptt_active = False

    def set_volume(self, device: str, volume: float) -> bool:
        self.volumes[device] = volume
        return True

    def set_mute(self, device: str, muted: bool) -> bool:
        self.muted[device] = muted
        return True

    def set_mode(self, mode) -> bool:
        self.mode = str(mode.value) if hasattr(mode, 'value') else str(mode)
        return True

    def set_ptt(self, active: bool) -> bool:
        self.ptt_active = active
        return True


class DemoDatabase:
    """Mock database for demo mode."""

    def __init__(self):
        self._cars_today = 12
        self._total_time = 570.0  # seconds

    def log_arrival(self):
        pass

    def log_departure(self, duration: float):
        self._cars_today += 1
        self._total_time += duration

    def get_stats(self) -> DemoStats:
        avg = self._total_time / max(1, self._cars_today)
        return DemoStats(
            cars_today=self._cars_today,
            avg_service_time_sec=avg,
        )


# Global demo instances
_demo_config: Optional[DemoConfig] = None
_demo_database: Optional[DemoDatabase] = None
_demo_audio: Optional[DemoAudioController] = None
_demo_serial: Optional[DemoSerialListener] = None
_demo_presence: Optional[DemoPresenceFilter] = None


def init_demo_mode():
    """Initialize demo mode backends."""
    global _demo_config, _demo_database, _demo_audio, _demo_serial
    _demo_config = DemoConfig()
    _demo_database = DemoDatabase()
    _demo_audio = DemoAudioController()
    _demo_serial = DemoSerialListener()


def get_demo_config() -> DemoConfig:
    global _demo_config
    if _demo_config is None:
        _demo_config = DemoConfig()
    return _demo_config


def get_demo_database() -> DemoDatabase:
    global _demo_database
    if _demo_database is None:
        _demo_database = DemoDatabase()
    return _demo_database


def get_demo_audio() -> DemoAudioController:
    global _demo_audio
    if _demo_audio is None:
        _demo_audio = DemoAudioController()
    return _demo_audio


def get_demo_serial() -> DemoSerialListener:
    global _demo_serial
    if _demo_serial is None:
        _demo_serial = DemoSerialListener()
    return _demo_serial


def create_demo_presence(
    on_car_arrived: Optional[Callable[[], None]] = None,
    on_car_left: Optional[Callable[[float], None]] = None,
) -> DemoPresenceFilter:
    """Create a demo presence filter."""
    global _demo_presence
    _demo_presence = DemoPresenceFilter(
        on_car_arrived=on_car_arrived,
        on_car_left=on_car_left,
    )
    return _demo_presence


def get_demo_presence() -> Optional[DemoPresenceFilter]:
    return _demo_presence
