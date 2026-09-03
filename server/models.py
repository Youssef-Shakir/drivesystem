"""Pydantic models for the drive-thru intercom system."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class AudioMode(str, Enum):
    FULL_DUPLEX = "full_duplex"
    PTT = "ptt"


class SensorStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


class LaneStatus(str, Enum):
    EMPTY = "empty"
    CAR_PRESENT = "car_present"


class SystemState(BaseModel):
    """Current system state for the dashboard."""
    lane_status: LaneStatus = LaneStatus.EMPTY
    car_arrived_at: Optional[datetime] = None
    sensor_status: SensorStatus = SensorStatus.UNKNOWN
    last_distance_cm: int = 0
    last_heartbeat: Optional[datetime] = None
    audio_mode: AudioMode = AudioMode.FULL_DUPLEX
    ptt_active: bool = False
    volumes: dict[str, float] = {}
    muted: dict[str, bool] = {}


class VolumeUpdate(BaseModel):
    """Volume update request."""
    device: str
    volume: float


class MuteUpdate(BaseModel):
    """Mute update request."""
    device: str
    muted: bool


class ModeUpdate(BaseModel):
    """Audio mode update request."""
    mode: AudioMode


class PTTUpdate(BaseModel):
    """Push-to-talk state update."""
    active: bool


class BluetoothMacRequest(BaseModel):
    """Request identifying a Bluetooth device by MAC address."""
    mac: str


class TestAudioRequest(BaseModel):
    """Request to play a test sound to an output device."""
    device: str


class DenoiseSettingsUpdate(BaseModel):
    """Outdoor-mic noise suppression (DeepFilterNet) tuning update."""
    attenuation_limit_db: float


class SensorSettingsUpdate(BaseModel):
    """Car-detection distance band / hysteresis tuning update."""
    detect_min_cm: int
    detect_max_cm: int
    arrival_hold_sec: float
    departure_hold_sec: float
    steady_sec: float


class ChimeSelectRequest(BaseModel):
    """Select which arrival-chime sound to play (a preset name or 'custom')."""
    chime: str


class Stats(BaseModel):
    """Daily statistics."""
    cars_today: int = 0
    avg_service_time_sec: float = 0.0
    total_cars_all_time: int = 0


class Visit(BaseModel):
    """A car visit record."""
    id: int
    arrived_at: datetime
    left_at: Optional[datetime] = None
    service_duration_sec: Optional[float] = None
