"""
Offline DeepFilterNet tuning lab.

Lets a human A/B-listen to candidate noise-suppression settings against
*real* recorded drive-thru audio (see recorder.py / recordings/raw/) before
committing to them live, instead of guessing at the live sliders in
real time with a customer's car at the window.

How it works: the exact same LADSPA plugin PipeWire loads at runtime
(pipewire/plugins/libdeep_filter_ladspa.so, see
pipewire/97-drivethru-deepfilter.conf) is re-run here offline, through
ffmpeg's built-in LADSPA host, directly against a short clip cut from a
recorded "raw" (pre-AEC/pre-filter) hour. This is the real algorithm, not
a simulation - only difference is it's not running inside PipeWire's
real-time audio graph, so there's no risk to the live call path while
trying things out.

Nothing here touches the live audio graph. server/audio_control.py's
set_denoise_attenuation/set_denoise_post_filter_beta (called from
server/main.py's /api/tuning/apply) is what actually applies a chosen
setting live, same as the existing /api/denoise-settings endpoint.
"""

import hashlib
import logging
import re
import wave
from array import array
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

RECORDINGS_DIR = Path(__file__).resolve().parent.parent / "recordings"
RAW_DIR = RECORDINGS_DIR / "raw"
FILTERED_DIR = RECORDINGS_DIR / "filtered"
WORK_DIR = RECORDINGS_DIR / "tuning"
CLIPS_DIR = WORK_DIR / "clips"
CANDIDATES_DIR = WORK_DIR / "candidates"

PLUGIN_PATH = Path(__file__).resolve().parent.parent / "pipewire" / "plugins" / "libdeep_filter_ladspa.so"
PLUGIN_LABEL = "deep_filter_mono"

# Fixed control-port order for deep_filter_mono, confirmed via
# `analyseplugin libdeep_filter_ladspa.so` - ffmpeg's ladspa filter takes
# control values positionally (no names), so this order must match the
# plugin exactly or the wrong knob gets tuned.
CONTROL_PORTS = (
    "atten_limit_db",
    "min_proc_db",
    "max_erb_db",
    "max_df_db",
    "min_buf_frames",
    "post_filter_beta",
)
CONTROL_DEFAULTS = {
    "atten_limit_db": 100.0,
    "min_proc_db": -15.0,
    "max_erb_db": 35.0,
    "max_df_db": 35.0,
    "min_buf_frames": 3.0,
    "post_filter_beta": 0.0,
}

# recordings/raw/2026-09-06_22h04.wav style filenames from recorder.py.
_HOUR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{2}h\d{2}$")

# Below this, treat the hour as an empty/error placeholder (recorder.py
# writes a bare 44-byte WAV header when a chunk failed outright) rather
# than something worth offering to load.
_MIN_USABLE_BYTES = 10_000


class TuningLabError(Exception):
    """Raised for tuning-lab requests that can't be fulfilled (bad hour id,
    ffmpeg failure, etc.) - callers turn this into an HTTP 400."""


def _ensure_dirs() -> None:
    CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)


def _wav_duration_sec(path: Path) -> float:
    with wave.open(str(path), "rb") as wf:
        return wf.getnframes() / float(wf.getframerate() or 1)


def list_hours() -> list[dict]:
    """List recorded hours that have a usable (non-empty) raw capture,
    newest first, each paired with whether a filtered capture also exists
    for the same hour."""
    if not RAW_DIR.is_dir():
        return []

    hours = []
    for raw_path in sorted(RAW_DIR.glob("*.wav"), reverse=True):
        hour_id = raw_path.stem
        if not _HOUR_RE.match(hour_id):
            continue
        if raw_path.stat().st_size < _MIN_USABLE_BYTES:
            continue
        filtered_path = FILTERED_DIR / raw_path.name
        try:
            duration_sec = _wav_duration_sec(raw_path)
        except Exception as e:
            logger.warning(f"Skipping unreadable recording {raw_path.name}: {e}")
            continue
        hours.append({
            "hour_id": hour_id,
            "duration_sec": duration_sec,
            "has_filtered": filtered_path.is_file() and filtered_path.stat().st_size >= _MIN_USABLE_BYTES,
        })
    return hours


def _resolve_hour(hour_id: str) -> Path:
    """Validate hour_id against the real filename pattern and confirm the
    file exists - this is the only thing standing between a client-supplied
    string and a filesystem path, so it must reject anything that isn't
    exactly one of our own recorded hours (no path traversal, no arbitrary
    reads)."""
    if not _HOUR_RE.match(hour_id):
        raise TuningLabError(f"Not a valid recording id: {hour_id!r}")
    raw_path = RAW_DIR / f"{hour_id}.wav"
    if not raw_path.is_file():
        raise TuningLabError(f"No such recording: {hour_id}")
    return raw_path


def _run_ffmpeg(args: list[str]) -> None:
    import subprocess
    result = subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "warning", *args],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        raise TuningLabError(f"ffmpeg failed: {result.stderr.strip()[-500:]}")


def get_clip(hour_id: str, start_sec: float, duration_sec: float) -> dict:
    """Cut a short raw (+ filtered, if that hour has one) clip for
    listening/processing, caching by (hour, start, duration) so repeated
    requests for the same slice don't re-invoke ffmpeg."""
    _ensure_dirs()
    raw_path = _resolve_hour(hour_id)
    start_sec = max(0.0, start_sec)
    duration_sec = max(1.0, min(duration_sec, 60.0))  # keep clips short - this is for listening, not bulk export

    tag = f"{hour_id}_{start_sec:.1f}_{duration_sec:.1f}"
    raw_clip = CLIPS_DIR / f"{tag}_raw.wav"
    if not raw_clip.exists():
        _run_ffmpeg(["-i", str(raw_path), "-ss", f"{start_sec:.2f}", "-t", f"{duration_sec:.2f}",
                     "-ar", "48000", "-ac", "1", str(raw_clip)])

    filtered_path = FILTERED_DIR / f"{hour_id}.wav"
    filtered_clip: Optional[Path] = None
    if filtered_path.is_file():
        filtered_clip = CLIPS_DIR / f"{tag}_filtered.wav"
        if not filtered_clip.exists():
            _run_ffmpeg(["-i", str(filtered_path), "-ss", f"{start_sec:.2f}", "-t", f"{duration_sec:.2f}",
                         "-ar", "48000", "-ac", "1", str(filtered_clip)])

    return {
        "raw_token": raw_clip.name,
        "filtered_token": filtered_clip.name if filtered_clip else None,
        "duration_sec": duration_sec,
    }


def generate_candidate(hour_id: str, start_sec: float, duration_sec: float, controls: dict) -> dict:
    """Run the real DeepFilterNet plugin offline (via ffmpeg's LADSPA host)
    against the raw clip with the given control values, and return a
    playable token plus rough before/after level metrics."""
    _ensure_dirs()
    clip = get_clip(hour_id, start_sec, duration_sec)
    raw_clip = CLIPS_DIR / clip["raw_token"]

    values = [controls.get(name, CONTROL_DEFAULTS[name]) for name in CONTROL_PORTS]
    controls_str = "|".join(f"{v:g}" for v in values)

    digest = hashlib.sha1(f"{hour_id}:{start_sec}:{duration_sec}:{controls_str}".encode()).hexdigest()[:16]
    out_path = CANDIDATES_DIR / f"{digest}.wav"
    if not out_path.exists():
        _run_ffmpeg([
            "-i", str(raw_clip),
            "-af", f"ladspa=file={PLUGIN_PATH}:plugin={PLUGIN_LABEL}:controls={controls_str}",
            "-ar", "48000", "-ac", "1", str(out_path),
        ])

    metrics = _compare_levels(raw_clip, out_path)
    return {"token": out_path.name, "metrics": metrics}


def _frame_dbfs(samples: array, rate: int, window_ms: float = 20.0) -> list[float]:
    """Per-window RMS level in dBFS (16-bit signed full scale). Silence
    floors out at -90 dB rather than -inf."""
    import math
    window_n = max(1, int(rate * window_ms / 1000))
    levels = []
    for i in range(0, len(samples) - window_n, window_n):
        chunk = samples[i:i + window_n]
        mean_sq = sum(s * s for s in chunk) / len(chunk)
        rms = math.sqrt(mean_sq) if mean_sq > 0 else 0.0
        dbfs = 20 * math.log10(rms / 32768.0) if rms > 0 else -90.0
        levels.append(max(dbfs, -90.0))
    return levels or [-90.0]


def _read_mono_pcm16(path: Path) -> tuple[array, int]:
    with wave.open(str(path), "rb") as wf:
        rate = wf.getframerate()
        raw_bytes = wf.readframes(wf.getnframes())
    samples = array("h")
    samples.frombytes(raw_bytes)
    return samples, rate


def _compare_levels(raw_path: Path, processed_path: Path) -> dict:
    """Rough, locally-computed before/after numbers to guide tuning - NOT a
    real speech-quality score (no PESQ/STOI here, no clean reference
    exists for real drive-thru audio). Treat these as a sanity check to
    read alongside actually listening, not a replacement for it:
      - noise_reduction_db: how much quieter the quiet stretches got
        (background/road noise) - bigger is more aggressive suppression.
      - speech_level_change_db: how much the loud stretches (presumably
        speech) changed - close to 0 is good; a big negative number means
        this setting is likely cutting into voice, not just noise.
    """
    try:
        raw_samples, raw_rate = _read_mono_pcm16(raw_path)
        proc_samples, proc_rate = _read_mono_pcm16(processed_path)
        raw_levels = sorted(_frame_dbfs(raw_samples, raw_rate))
        proc_levels = sorted(_frame_dbfs(proc_samples, proc_rate))

        def percentile(sorted_vals, p):
            idx = min(len(sorted_vals) - 1, max(0, int(len(sorted_vals) * p)))
            return sorted_vals[idx]

        noise_before = percentile(raw_levels, 0.10)
        noise_after = percentile(proc_levels, 0.10)
        speech_before = percentile(raw_levels, 0.90)
        speech_after = percentile(proc_levels, 0.90)

        return {
            "noise_reduction_db": round(noise_before - noise_after, 1),
            "speech_level_change_db": round(speech_after - speech_before, 1),
        }
    except Exception as e:
        logger.warning(f"Tuning-lab metrics failed for {processed_path.name}: {e}")
        return {"noise_reduction_db": None, "speech_level_change_db": None}


def resolve_audio_token(token: str) -> Optional[Path]:
    """Map a token previously handed out by get_clip()/generate_candidate()
    back to a real file path, for serving - only ever looks inside the
    clips/candidates dirs and only accepts tokens matching what we
    ourselves generate (hex hash or validated-hour-based names), so a
    client can't use this to read arbitrary files."""
    if not re.match(r"^[A-Za-z0-9_.\-]+\.wav$", token):
        return None
    for directory in (CLIPS_DIR, CANDIDATES_DIR):
        candidate = directory / token
        if candidate.is_file():
            try:
                candidate.resolve().relative_to(directory.resolve())
            except ValueError:
                continue
            return candidate
    return None
