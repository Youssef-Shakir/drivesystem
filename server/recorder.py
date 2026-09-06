"""
Dual-stream tuning recorder.

Records two synchronized audio streams for offline AI-assisted tuning of
the outdoor mic's AEC/noise-filter settings:

  - "raw": the pure, unprocessed mic signal straight off the physical
    hardware - before AEC, before DeepFilterNet.
  - "filtered": dt_denoised_source, the final cleaned-up signal that
    actually reaches the headset today (after AEC + DeepFilterNet).

Having both lets an offline process later compare what came in against
what today's pipeline produced, to study what a better tuning would sound
like. Neither stream feeds into the live call audio path - this only taps
existing nodes as an extra read-only consumer.

Runs for a fixed window (default 48h) starting from whenever it's first
started, and resumes across a service restart from the ORIGINAL start
time (persisted in recordings/state.json) rather than restarting the
clock - so a mid-window PipeWire/service restart doesn't quietly extend
the capture past what was asked for.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

RECORDINGS_DIR = Path(__file__).resolve().parent.parent / "recordings"
STATE_PATH = RECORDINGS_DIR / "state.json"

# Marker left behind by an explicit user stop (or a window completing on
# its own) so a later service restart doesn't quietly start a brand-new
# recording window - only an explicit start(resume=False) (the dashboard's
# Start New button) removes it. Without this, stopping the recording and
# then restarting the service for an unrelated reason (a deploy, a reboot)
# would silently resurrect a fresh multi-day capture.
_DISABLED_MARKER = RECORDINGS_DIR / ".recording_disabled"

# The already-denoised signal actually sent to the headset today (see
# 97-drivethru-deepfilter.conf's playback.props.node.name) - a fixed
# internal PipeWire node name, not user-facing config, matching how
# audio_control.py hardcodes MIC_TO_HEADSET_NODE for the same reason.
FILTERED_NODE = "dt_denoised_source"

# Rotate to a new file every hour - keeps individual files small/manageable
# and means a mid-write crash or power loss only costs at most an hour, not
# the whole multi-day capture.
CHUNK_SEC = 3600.0

# How long to back off after pw-cat fails to start or dies immediately
# (e.g. the target node doesn't exist yet) before retrying, so a persistent
# failure doesn't spin in a tight loop.
RETRY_BACKOFF_SEC = 15.0


class TuningRecorder:
    def __init__(self, raw_node: str, filtered_node: str = FILTERED_NODE, duration_hours: float = 48.0):
        self.raw_node = raw_node
        self.filtered_node = filtered_node
        self.duration_hours = duration_hours

        self._tasks: list[asyncio.Task] = []
        self._procs: list[asyncio.subprocess.Process] = []
        self._stop_requested = False
        self.started_at: Optional[datetime] = None
        self.files_written = {"raw": 0, "filtered": 0}
        self.last_error: Optional[str] = None

    # --- state persistence (so a service restart resumes the same window) ---
    def _load_state(self) -> Optional[dict]:
        if STATE_PATH.exists():
            try:
                return json.loads(STATE_PATH.read_text())
            except Exception:
                return None
        return None

    def _save_state(self) -> None:
        RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps({
            "started_at": self.started_at.isoformat(),
            "duration_hours": self.duration_hours,
        }))

    def _clear_state(self) -> None:
        if STATE_PATH.exists():
            STATE_PATH.unlink()

    @staticmethod
    def is_disabled() -> bool:
        """True once the recorder has been explicitly stopped (or a window
        completed on its own) and hasn't been explicitly re-started since."""
        return _DISABLED_MARKER.exists()

    @property
    def end_at(self) -> Optional[datetime]:
        if self.started_at is None:
            return None
        return self.started_at + timedelta(hours=self.duration_hours)

    @property
    def is_running(self) -> bool:
        return bool(self._tasks) and not self._stop_requested

    def status(self) -> dict:
        now = datetime.now()
        running = self.is_running
        remaining_sec = max(0.0, (self.end_at - now).total_seconds()) if (running and self.end_at) else 0.0
        return {
            "running": running,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ends_at": self.end_at.isoformat() if self.end_at else None,
            "remaining_sec": remaining_sec,
            "duration_hours": self.duration_hours,
            "files_written": dict(self.files_written),
            "raw_node": self.raw_node,
            "filtered_node": self.filtered_node,
            "output_dir": str(RECORDINGS_DIR),
            "last_error": self.last_error,
        }

    async def start(self, resume: bool = False) -> bool:
        """Start (or resume) recording. Returns False if already running,
        or (when resuming) the original window has already elapsed."""
        if self.is_running:
            return False

        if resume:
            if self.is_disabled():
                logger.info("Tuning recording was explicitly stopped previously - not auto-resuming")
                return False
            state = self._load_state()
            if not state:
                return False
            try:
                self.started_at = datetime.fromisoformat(state["started_at"])
            except (KeyError, ValueError):
                return False
            self.duration_hours = state.get("duration_hours", self.duration_hours)
            if datetime.now() >= self.end_at:
                logger.info("Tuning recording window already elapsed - not resuming")
                self._clear_state()
                self.started_at = None
                _DISABLED_MARKER.parent.mkdir(parents=True, exist_ok=True)
                _DISABLED_MARKER.touch()
                return False
            logger.info(f"Resuming tuning recording (started {self.started_at.isoformat()}, ends {self.end_at.isoformat()})")
        else:
            self.started_at = datetime.now()
            self._save_state()
            _DISABLED_MARKER.unlink(missing_ok=True)
            logger.info(f"Starting tuning recording, ends {self.end_at.isoformat()}")

        self._stop_requested = False
        self.last_error = None
        (RECORDINGS_DIR / "raw").mkdir(parents=True, exist_ok=True)
        (RECORDINGS_DIR / "filtered").mkdir(parents=True, exist_ok=True)

        self._tasks = [
            asyncio.create_task(self._record_loop("raw", self.raw_node)),
            asyncio.create_task(self._record_loop("filtered", self.filtered_node)),
        ]
        return True

    async def stop(self, clear_state: bool = True) -> None:
        """Stop recording. clear_state=False keeps recordings/state.json so
        a later start(resume=True) picks the same window back up (used on
        a plain service restart); clear_state=True abandons the recording
        entirely (used when the user explicitly stops it)."""
        self._stop_requested = True
        for proc in list(self._procs):
            if proc.returncode is None:
                try:
                    proc.terminate()
                except ProcessLookupError:
                    pass
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks = []
        if clear_state:
            self._clear_state()
            self.started_at = None
            _DISABLED_MARKER.parent.mkdir(parents=True, exist_ok=True)
            _DISABLED_MARKER.touch()
        logger.info(f"Tuning recording stopped (state {'cleared' if clear_state else 'kept for resume'})")

    async def _record_loop(self, label: str, node: str) -> None:
        out_dir = RECORDINGS_DIR / label
        try:
            while not self._stop_requested:
                now = datetime.now()
                if self.end_at and now >= self.end_at:
                    logger.info(f"Tuning recording ({label}): {self.duration_hours}h window complete")
                    break

                chunk_sec = CHUNK_SEC
                if self.end_at:
                    chunk_sec = min(chunk_sec, (self.end_at - now).total_seconds())
                if chunk_sec < 1:
                    break

                filename = out_dir / f"{now.strftime('%Y-%m-%d_%Hh%M')}.wav"
                cmd = [
                    "pw-cat", "--record",
                    "--target", node,
                    "--channels", "1",
                    "--rate", "48000",
                    "--format", "s16",
                    str(filename),
                ]
                try:
                    proc = await asyncio.create_subprocess_exec(
                        *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
                    )
                except Exception as e:
                    self.last_error = f"{label}: failed to start pw-cat: {e}"
                    logger.error(f"Tuning recording ({label}): failed to start pw-cat: {e}")
                    await asyncio.sleep(RETRY_BACKOFF_SEC)
                    continue

                self._procs.append(proc)
                try:
                    await asyncio.wait_for(proc.wait(), timeout=chunk_sec)
                    # Exited on its own before the chunk boundary - almost
                    # certainly an error (target node missing, etc).
                    stderr = (await proc.stderr.read()).decode(errors="replace") if proc.stderr else ""
                    self.last_error = f"{label}: pw-cat exited early (code {proc.returncode}) - {stderr.strip()[:300]}"
                    logger.warning(f"Tuning recording ({label}): {self.last_error}. Retrying in {RETRY_BACKOFF_SEC:.0f}s.")
                    await asyncio.sleep(RETRY_BACKOFF_SEC)
                except asyncio.TimeoutError:
                    # Normal case: reached the chunk boundary - rotate.
                    proc.terminate()
                    try:
                        await asyncio.wait_for(proc.wait(), timeout=5)
                    except asyncio.TimeoutError:
                        proc.kill()
                    self.files_written[label] += 1
                finally:
                    if proc in self._procs:
                        self._procs.remove(proc)
        except asyncio.CancelledError:
            raise
        finally:
            logger.info(f"Tuning recording loop for {label} ended")


_recorder: Optional[TuningRecorder] = None


def get_recorder() -> Optional[TuningRecorder]:
    return _recorder


def init_recorder(raw_node: str, filtered_node: str = FILTERED_NODE, duration_hours: float = 48.0) -> TuningRecorder:
    global _recorder
    _recorder = TuningRecorder(raw_node, filtered_node, duration_hours)
    return _recorder
