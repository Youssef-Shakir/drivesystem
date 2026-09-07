"""
Drive-Thru Intercom Server

FastAPI application providing REST API and dashboard for the intercom system.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import auth, bluetooth_control
from .audio_control import AudioController, get_audio_controller, init_audio_controller
from .config import Config, get_config, init_config
from .database import Database, get_database, init_database
from .level_meter import get_level_meter, init_level_meter
from .logging_setup import read_recent_log_lines, setup_logging
from .models import (
    AudioMode,
    BluetoothMacRequest,
    ChimeSelectRequest,
    DenoiseSettingsUpdate,
    LaneStatus,
    ModeUpdate,
    MuteUpdate,
    PTTUpdate,
    SensorSettingsUpdate,
    SensorStatus,
    Stats,
    SystemState,
    TestAudioRequest,
    TuningCandidateRequest,
    TuningClipRequest,
    VolumeUpdate,
)
from .presence_filter import PresenceFilter
from .recorder import get_recorder, init_recorder
from .serial_listener import SerialListener, init_serial_listener
from . import tuning_lab

# Configure logging (console + a rotating logs/drivethru.log file for
# later diagnosis without needing journalctl)
setup_logging()
logger = logging.getLogger(__name__)

# Global state
presence_filter: PresenceFilter | None = None
serial_listener: SerialListener | None = None
headset_monitor_task: asyncio.Task | None = None
headset_mac: str | None = None


def on_car_arrived() -> None:
    """Handle car arrival event."""
    logger.info("Car arrived at drive-thru")
    db = get_database()
    db.log_arrival()

    # Belt-and-suspenders on top of the monitor loop's mute: even if the
    # mute hasn't caught up yet (it only checks every poll_interval), never
    # even attempt to play the chime while the headset's audio path isn't
    # actually ready - pw-play falls back to the default sink (the outdoor
    # speaker) when its --target can't be resolved, which is exactly the
    # "outdoor speaker acting like the indoor headset speaker" bug.
    # is_audio_ready(), not just is_connected(): BlueZ can report the
    # radio link connected before PipeWire has actually created the
    # headset's nodes, and pw-play would still fail/fall back during that
    # gap even though is_connected() alone says yes. A skipped arrival
    # chime is a much smaller problem than a customer hearing it.
    if headset_mac and not bluetooth_control.is_audio_ready(headset_mac):
        logger.warning("Headset not ready - skipping arrival chime (would otherwise leak to outdoor speaker)")
        return

    # Play chime to headset
    config = get_config()
    audio = get_audio_controller()
    audio.play_chime(config.chime_path)


def on_car_left(service_duration_sec: float) -> None:
    """Handle car departure event."""
    logger.info(f"Car left drive-thru after {service_duration_sec:.1f}s")
    db = get_database()
    db.log_departure(service_duration_sec)


def on_serial_event(event: str) -> None:
    """Handle serial events from ESP32."""
    global presence_filter
    if presence_filter:
        presence_filter.process_event(event)


def on_serial_heartbeat(distance_cm: int) -> None:
    """Handle a raw distance reading. Drives arrival/departure detection
    for sensors that only stream a bare distance (no CAR_ARRIVED/CAR_LEFT
    of their own) - see PresenceFilter.process_distance. For sensors that
    do send their own events, this just keeps last_distance_cm current for
    the dashboard without affecting state (process_distance still runs the
    same hysteresis machine, but it's process_event's CAR_ARRIVED/CAR_LEFT
    that actually drives state in that case)."""
    global presence_filter
    if presence_filter:
        presence_filter.process_distance(distance_cm)


def on_connection_change(connected: bool) -> None:
    """Handle serial connection state changes."""
    if connected:
        logger.info("Sensor connected")
    else:
        logger.warning("Sensor disconnected")


async def monitor_headset_connection(headset_mac: str, poll_interval: float = 1.5) -> None:
    """
    Background loop for the life of the server: keeps the outdoor speaker
    muted whenever the Bluetooth headset isn't connected (otherwise sounds
    meant for staff - the arrival chime, test tones - fall back to playing
    out the outdoor speaker once the headset's PipeWire node disappears,
    which is what was heard as the outdoor speaker "acting like the indoor
    headset speaker"), and keeps retrying the connection continuously so the
    headset reconnects on its own as soon as it's powered on / back in
    range - like Windows does for a paired Bluetooth headset, rather than
    only trying at startup.

    Only acts on *transitions* in connection state, so it never fights a
    manual mute/unmute the user made from the dashboard while the headset's
    connection state hasn't actually changed.

    Gates on bluetooth_control.is_audio_ready(), not just is_connected():
    BlueZ can report the radio link "Connected: yes" for a noticeable
    stretch before PipeWire's bluez5 backend has actually created the
    Device/Nodes and settled on the headset-head-unit profile - during
    that gap nothing meant for the headset can actually play. Gating the
    unmute (and the dashboard's own "Connected" status, via device_info())
    on is_audio_ready() instead means "connected" only ever means "audio
    actually works", not just "radio link is up".
    """
    last_ready: Optional[bool] = None
    fail_count = 0
    last_fail_message = ""
    last_diagnostic_log = 0.0
    DIAGNOSTIC_LOG_INTERVAL_SEC = 20.0
    while True:
        try:
            acl_connected = await asyncio.to_thread(bluetooth_control.is_connected, headset_mac)

            if acl_connected:
                # Make sure it's on the right profile so PipeWire's mic/
                # speaker nodes actually get created - idempotent (see
                # force_headset_profile()'s docstring), safe to call every
                # poll while connected.
                await asyncio.to_thread(bluetooth_control.force_headset_profile, headset_mac)

            ready = acl_connected and await asyncio.to_thread(bluetooth_control.is_audio_ready, headset_mac)

            if ready and last_ready is not True:
                audio = get_audio_controller()
                audio.refresh_node_ids()
                audio.set_mute("outdoor_speaker", False)
                logger.info(f"Headset {headset_mac} connected - outdoor speaker unmuted")
                fail_count = 0

            elif not ready and last_ready is not False:
                audio = get_audio_controller()
                audio.set_mute("outdoor_speaker", True)
                logger.warning(f"Headset {headset_mac} not connected - outdoor speaker muted")

            last_ready = ready

            if not acl_connected:
                ok, message = await asyncio.to_thread(bluetooth_control.connect, headset_mac)
                if ok:
                    logger.info(f"Headset {headset_mac} auto-reconnected")
                    fail_count = 0
                else:
                    # Individual failures stay quiet (the state-transition
                    # log above already recorded it's disconnected - no
                    # need to spam a warning every poll_interval while it's
                    # simply off/out of range), but a long stretch with no
                    # visibility at all makes stretches like "took 3 minutes
                    # to reconnect at boot, no idea why" impossible to
                    # actually diagnose after the fact. Log a periodic
                    # summary with the actual last failure reason instead.
                    fail_count += 1
                    last_fail_message = message
                    now = asyncio.get_event_loop().time()
                    if now - last_diagnostic_log >= DIAGNOSTIC_LOG_INTERVAL_SEC:
                        logger.warning(
                            f"Headset {headset_mac} still not connected after "
                            f"{fail_count} attempts - last error: {last_fail_message}"
                        )
                        last_diagnostic_log = now
            elif not ready:
                # Radio link is up but PipeWire/the profile switch hasn't
                # caught up yet - nothing to retry here (no reconnect
                # needed), just worth surfacing if it drags on.
                now = asyncio.get_event_loop().time()
                if now - last_diagnostic_log >= DIAGNOSTIC_LOG_INTERVAL_SEC:
                    logger.warning(
                        f"Headset {headset_mac} radio-connected but audio path "
                        "not ready yet (waiting on PipeWire/profile)"
                    )
                    last_diagnostic_log = now
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Headset monitor loop error: {e}")

        await asyncio.sleep(poll_interval)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler."""
    global presence_filter, serial_listener, headset_monitor_task, headset_mac

    logger.info("Starting drive-thru intercom server...")

    # Initialize config
    config = init_config()

    # Initialize database
    init_database(config.database_path)
    logger.info(f"Database initialized at {config.database_path}")

    # Initialize audio controller first so we can mute the outdoor speaker
    # before doing anything else - see the mute step right below.
    audio = init_audio_controller(
        outdoor_mic_node=config.outdoor_mic_node,
        outdoor_speaker_node=config.outdoor_speaker_node,
        headset_sink_node=config.headset_sink_node,
        headset_source_node=config.headset_source_node,
        default_volumes=config.default_volumes,
    )
    if config.default_audio_mode == "ptt":
        audio.mode = AudioMode.PTT
    audio.apply_initial_settings()
    logger.info("Audio controller initialized")

    # Apply the saved DeepFilterNet outdoor-mic noise suppression tuning
    # (no-op if 97-drivethru-deepfilter.conf isn't loaded, e.g. reverted).
    if audio.set_denoise_attenuation(config.denoise_attenuation_limit_db):
        logger.info(f"Denoise attenuation limit set to {config.denoise_attenuation_limit_db} dB")
    if audio.set_denoise_post_filter_beta(config.denoise_post_filter_beta):
        logger.info(f"Denoise post-filter beta set to {config.denoise_post_filter_beta}")

    # Keep the outdoor speaker muted until the headset is confirmed
    # connected. Without this, anything meant for staff (chime, test tones)
    # falls back to the outdoor speaker while the headset's PipeWire node
    # doesn't exist yet - heard as the outdoor speaker "acting like the
    # indoor headset speaker". monitor_headset_connection() below unmutes
    # it the moment the headset actually connects.
    audio.set_mute("outdoor_speaker", True)

    # Actively connect the configured headset at startup - BlueZ's own
    # auto-reconnect for a trusted/paired device isn't reliable enough on
    # its own (confirmed: doesn't consistently happen across restarts).
    # A few retries since the headset may still be powering up / not yet
    # in range at the exact moment the service starts.
    headset_mac = bluetooth_control.mac_from_node_name(config.headset_sink_node)
    headset_connected_at_start = False
    if headset_mac:
        for attempt in range(3):
            connected, message = await asyncio.to_thread(bluetooth_control.connect, headset_mac)
            if connected:
                logger.info(f"Headset {headset_mac} connected at startup")
                headset_connected_at_start = True
                break
            logger.warning(f"Headset connect attempt {attempt + 1}/3 failed: {message}")
            if attempt < 2:
                await asyncio.sleep(3)
        # PipeWire defaults Bluetooth devices to A2DP-sink (no mic) - make
        # sure it's actually in headset-head-unit (HSP/HFP) before we look
        # up its nodes, whether or not the connect attempt above succeeded.
        await asyncio.to_thread(bluetooth_control.force_headset_profile, headset_mac)

        if headset_connected_at_start:
            audio.set_mute("outdoor_speaker", False)
        else:
            logger.warning(
                f"Headset {headset_mac} not connected at startup - "
                "outdoor speaker stays muted until it connects"
            )

        # Keep trying to (re)connect for the life of the service - "like
        # Windows", not just a few attempts at startup - and keep the
        # outdoor speaker mute in sync with the live connection state.
        headset_monitor_task = asyncio.create_task(monitor_headset_connection(headset_mac))
    else:
        logger.warning(
            "Could not determine headset MAC from config - auto-connect "
            "and outdoor-speaker muting are disabled; outdoor speaker "
            "left unmuted"
        )
        audio.set_mute("outdoor_speaker", False)

    # Start real-time level meters for the dashboard
    init_level_meter({
        "outdoor_mic": config.outdoor_mic_node,
        "outdoor_speaker": config.outdoor_speaker_node,
        "headset": config.headset_sink_node,
        "indoor_mic": config.headset_source_node,
    })
    logger.info("Level meters started")

    # Tuning recorder - records raw (pre-AEC) + filtered (post-denoise)
    # outdoor mic audio to recordings/ for offline AI-assisted tuning. Only
    # starts if raw_outdoor_mic is actually configured. Resumes the
    # original window across a restart rather than restarting the clock.
    if config.raw_outdoor_mic_node:
        recorder = init_recorder(
            raw_node=config.raw_outdoor_mic_node,
            duration_hours=config.recording_duration_hours,
        )
        started = await recorder.start(resume=True)
        if not started and not recorder.is_disabled():
            # No previous window to resume, and it was never explicitly
            # stopped either - this is a genuine first run, so start fresh.
            started = await recorder.start(resume=False)
        if started:
            ends_desc = recorder.end_at.isoformat() if recorder.end_at else "no limit - until stopped"
            logger.info(f"Tuning recording active, ends {ends_desc}")
        elif recorder.is_disabled():
            logger.info("Tuning recording not started - previously stopped; use the dashboard to start a new window")
    else:
        logger.warning("raw_outdoor_mic not configured - tuning recorder disabled")

    # Voice detection (Silero VAD) and the outdoor-speaker hardware bridge
    # are disabled - rolled back per user request after audio quality
    # regressed and neither of the above fixed it. See git history /
    # conversation log for hw_bridge.py and voice_detector.py if revisiting.

    # Initialize presence filter
    presence_filter = PresenceFilter(
        min_distance_cm=config.detect_min_cm,
        max_distance_cm=config.detect_max_cm,
        arrival_hold_sec=config.arrival_hold_sec,
        departure_hold_sec=config.departure_hold_sec,
        steady_sec=config.steady_sec,
        on_car_arrived=on_car_arrived,
        on_car_left=on_car_left,
    )

    # Initialize and start serial listener
    serial_listener = init_serial_listener(
        port=config.serial_port,
        baudrate=config.serial_baudrate,
        heartbeat_timeout_sec=config.heartbeat_timeout_sec,
        on_event=on_serial_event,
        on_connection_change=on_connection_change,
        on_heartbeat=on_serial_heartbeat,
    )
    serial_listener.start()
    logger.info(f"Serial listener started on {config.serial_port}")

    logger.info(f"Server ready at http://{config.server_host}:{config.server_port}")

    yield

    # Shutdown
    logger.info("Shutting down...")
    if headset_monitor_task:
        headset_monitor_task.cancel()
        try:
            await headset_monitor_task
        except asyncio.CancelledError:
            pass
    if serial_listener:
        serial_listener.stop()
    get_level_meter().stop()
    if get_recorder():
        # Keep state.json so a plain service restart resumes the same
        # 48h window instead of restarting the clock.
        await get_recorder().stop(clear_state=False)


app = FastAPI(
    title="Drive-Thru Intercom",
    description="Control and monitoring for drive-thru intercom system",
    version="1.0.0",
    lifespan=lifespan,
)


# Serve static files (order matters - more specific paths first)
static_dir = Path(__file__).parent / "static"
assets_dir = Path(__file__).parent / "assets"
if assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


# --- PIN gate ---
# Everything except /login requires a valid session cookie. API requests
# get a plain 401 (so the dashboard's fetch() calls fail cleanly); page
# requests get bounced to the login form.
_PUBLIC_PATHS = {"/login"}


@app.middleware("http")
async def pin_gate(request: Request, call_next):
    if request.url.path in _PUBLIC_PATHS:
        return await call_next(request)
    token = request.cookies.get(auth.SESSION_COOKIE)
    if not auth.verify_session_token(token):
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return RedirectResponse("/login", status_code=303)
    return await call_next(request)


@app.get("/login", response_class=HTMLResponse)
async def login_form():
    return auth.login_page_html()


@app.post("/login")
async def login_submit(request: Request, pin: str = Form(...)):
    client_ip = request.client.host if request.client else "unknown"
    if auth.is_rate_limited(client_ip):
        return HTMLResponse(auth.login_page_html("Too many attempts - wait a minute and try again."), status_code=429)

    config = get_config()
    if not auth.verify_pin(pin, config.dashboard_pin):
        auth.record_attempt(client_ip)
        logger.warning(f"Failed dashboard login attempt from {client_ip}")
        return HTMLResponse(auth.login_page_html("Wrong PIN."), status_code=401)

    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        auth.SESSION_COOKIE,
        auth.make_session_token(),
        max_age=auth.SESSION_MAX_AGE_SEC,
        httponly=True,
        samesite="lax",
    )
    return response


@app.post("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(auth.SESSION_COOKIE)
    return response


@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    """Serve the dashboard HTML."""
    index_path = static_dir / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return HTMLResponse("<h1>Dashboard not found</h1>", status_code=404)


@app.get("/api/state", response_model=SystemState)
async def get_state():
    """Get current system state."""
    global presence_filter, serial_listener

    audio = get_audio_controller()

    # Determine sensor status
    sensor_status = SensorStatus.UNKNOWN
    last_heartbeat = None
    last_distance = 0

    if serial_listener:
        if serial_listener.is_sensor_online:
            sensor_status = SensorStatus.ONLINE
        elif serial_listener.connected:
            sensor_status = SensorStatus.OFFLINE
        last_heartbeat = serial_listener.last_heartbeat
        last_distance = serial_listener.last_distance

    # Determine lane status
    lane_status = LaneStatus.EMPTY
    car_arrived_at = None

    if presence_filter:
        if presence_filter.is_car_present:
            lane_status = LaneStatus.CAR_PRESENT
            car_arrived_at = presence_filter.car_arrived_at
        last_distance = presence_filter.last_distance_cm or last_distance

    return SystemState(
        lane_status=lane_status,
        car_arrived_at=car_arrived_at,
        sensor_status=sensor_status,
        last_distance_cm=last_distance,
        last_heartbeat=last_heartbeat,
        audio_mode=audio.mode,
        ptt_active=audio.ptt_active,
        volumes=audio.volumes.copy(),
        muted=audio.muted.copy(),
    )


@app.get("/api/stats", response_model=Stats)
async def get_stats():
    """Get today's statistics."""
    db = get_database()
    return db.get_stats()


@app.post("/api/volume")
async def set_volume(update: VolumeUpdate):
    """Set volume for a device - takes effect immediately and is persisted
    to config.yaml so it survives a service restart or reboot instead of
    resetting to the old baked-in default."""
    audio = get_audio_controller()
    if update.device not in ("outdoor_mic", "outdoor_speaker", "headset", "indoor_mic"):
        raise HTTPException(status_code=400, detail=f"Unknown device: {update.device}")

    success = audio.set_volume(update.device, update.volume)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to set volume")

    get_config().set_default_volume(update.device, update.volume)
    return {"status": "ok", "device": update.device, "volume": update.volume}


@app.post("/api/mute")
async def set_mute(update: MuteUpdate):
    """Set mute state for a device."""
    audio = get_audio_controller()
    if update.device not in ("outdoor_mic", "outdoor_speaker", "headset", "indoor_mic"):
        raise HTTPException(status_code=400, detail=f"Unknown device: {update.device}")

    success = audio.set_mute(update.device, update.muted)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to set mute state")

    return {"status": "ok", "device": update.device, "muted": update.muted}


@app.post("/api/mode")
async def set_mode(update: ModeUpdate):
    """Set audio mode (full_duplex or ptt)."""
    audio = get_audio_controller()
    success = audio.set_mode(update.mode)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to set mode")

    return {"status": "ok", "mode": update.mode}


@app.post("/api/ptt")
async def set_ptt(update: PTTUpdate):
    """Set push-to-talk state (only in PTT mode)."""
    audio = get_audio_controller()
    if audio.mode != AudioMode.PTT:
        raise HTTPException(status_code=400, detail="PTT only available in PTT mode")

    success = audio.set_ptt(update.active)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to set PTT state")

    return {"status": "ok", "active": update.active}


@app.post("/api/test-audio")
async def test_audio(request: TestAudioRequest):
    """Play a test chime to an output device (outdoor_speaker or headset)."""
    if request.device not in ("outdoor_speaker", "headset"):
        raise HTTPException(status_code=400, detail=f"Cannot test device: {request.device}")

    if request.device == "headset" and headset_mac and not bluetooth_control.is_audio_ready(headset_mac):
        # Same reasoning as on_car_arrived: don't even attempt it - pw-play
        # falls back to the default sink (outdoor speaker) when the headset
        # node doesn't exist yet, which can be true even while BlueZ
        # reports the radio link connected (is_audio_ready() checks both).
        raise HTTPException(status_code=409, detail="Headset not ready")

    config = get_config()
    audio = get_audio_controller()
    success = audio.play_test_sound(request.device, config.chime_path)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to play test sound - check server logs")

    return {"status": "ok", "device": request.device}


@app.post("/api/refresh-audio")
async def refresh_audio():
    """Refresh audio node IDs (call after PipeWire restart)."""
    audio = get_audio_controller()
    audio.refresh_node_ids()
    audio.apply_initial_settings()
    get_level_meter().update_targets({
        "outdoor_mic": audio.outdoor_mic_node,
        "outdoor_speaker": audio.outdoor_speaker_node,
        "headset": audio.headset_sink_node,
        "indoor_mic": audio.headset_source_node,
    })
    return {"status": "ok"}


@app.get("/api/audio-levels")
async def get_audio_levels():
    """Get real-time peak/RMS levels for the outdoor mic, outdoor speaker, and headset."""
    return get_level_meter().get_levels()


@app.get("/api/recording/status")
async def get_recording_status():
    """Status of the raw+filtered outdoor-mic tuning recorder."""
    recorder = get_recorder()
    if not recorder:
        return {"running": False, "configured": False}
    return {**recorder.status(), "configured": True}


@app.post("/api/recording/start")
async def start_recording():
    """Start a fresh tuning-recording window (e.g. to kick off another
    multi-day capture after a previous one finished)."""
    recorder = get_recorder()
    if not recorder:
        raise HTTPException(status_code=400, detail="Recorder not configured - set audio.raw_outdoor_mic in config.yaml")
    started = await recorder.start(resume=False)
    if not started:
        raise HTTPException(status_code=409, detail="Already recording")
    return recorder.status()


@app.post("/api/recording/stop")
async def stop_recording():
    """Stop the tuning recorder early and discard its resume state."""
    recorder = get_recorder()
    if not recorder:
        raise HTTPException(status_code=400, detail="Recorder not configured")
    await recorder.stop(clear_state=True)
    return {"status": "ok"}


@app.get("/api/logs")
async def get_logs(lines: int = 200):
    """Recent lines from logs/drivethru.log, for on-dashboard diagnosis."""
    lines = max(1, min(lines, 2000))
    return {"lines": read_recent_log_lines(lines)}


@app.get("/api/settings")
async def get_settings():
    """Get current device settings."""
    config = get_config()
    audio = get_audio_controller()
    return {
        "serial_port": config.serial_port,
        "detect_min_cm": config.detect_min_cm,
        "detect_max_cm": config.detect_max_cm,
        "devices": {
            "outdoor_mic": audio.outdoor_mic_node,
            "outdoor_speaker": audio.outdoor_speaker_node,
            "headset_sink": audio.headset_sink_node,
            "headset_source": audio.headset_source_node,
        }
    }


# Audio processing settings (in-memory, adjustable via API)
audio_filter_settings = {
    "high_pass": {"enabled": True, "cutoff": 150},
    "noise_gate": {"enabled": True, "threshold": 0.015, "reduction": 0.2},
    "presence_boost": {"enabled": True, "low_freq": 2000, "high_freq": 4000, "gain": 0.3},
    "compressor": {"enabled": True, "threshold": 0.25, "ratio": 0.4},
    "normalize": {"enabled": True, "target": 0.85},
}


@app.get("/api/filter-settings")
async def get_filter_settings():
    """Get current audio filter settings."""
    return audio_filter_settings


@app.post("/api/filter-settings")
async def update_filter_settings(settings: dict):
    """Update audio filter settings."""
    global audio_filter_settings
    for key, value in settings.items():
        if key in audio_filter_settings:
            audio_filter_settings[key].update(value)
    return {"status": "ok", "settings": audio_filter_settings}


@app.post("/api/process-audio")
async def process_audio_with_settings():
    """Reprocess the recording with current filter settings."""
    import subprocess

    # Run the processing script with current settings
    settings_json = str(audio_filter_settings).replace("'", '"')
    result = subprocess.run(
        ["python3", "scripts/process_recording.py", "--settings", settings_json],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent,
    )

    if result.returncode == 0:
        return {"status": "ok", "output": result.stdout}
    else:
        return {"status": "error", "error": result.stderr}


@app.get("/api/pipewire-nodes")
async def get_pipewire_nodes():
    """Get available PipeWire nodes."""
    import json
    import subprocess
    try:
        result = subprocess.run(
            ["pw-dump"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        nodes = json.loads(result.stdout)
        audio_nodes = []
        for node in nodes:
            if node.get("type") == "PipeWire:Interface:Node":
                props = node.get("info", {}).get("props", {})
                name = props.get("node.name", "")
                desc = props.get("node.description", "")
                media_class = props.get("media.class", "")
                if name and media_class in ("Audio/Sink", "Audio/Source", "Stream/Output/Audio", "Stream/Input/Audio"):
                    audio_nodes.append({
                        "id": node.get("id"),
                        "name": name,
                        "description": desc,
                        "class": media_class,
                    })
        return {"nodes": audio_nodes}
    except Exception as e:
        return {"nodes": [], "error": str(e)}


@app.get("/api/denoise-settings")
async def get_denoise_settings():
    """
    Get the outdoor-mic noise suppression (DeepFilterNet) tuning. Reads the
    live value from PipeWire when the filter is loaded; falls back to the
    saved config value (and reports the filter as not loaded) otherwise.
    """
    config = get_config()
    audio = get_audio_controller()
    live_atten = await asyncio.to_thread(audio.get_denoise_attenuation)
    live_beta = await asyncio.to_thread(audio.get_denoise_post_filter_beta)
    return {
        "attenuation_limit_db": live_atten if live_atten is not None else config.denoise_attenuation_limit_db,
        "post_filter_beta": live_beta if live_beta is not None else config.denoise_post_filter_beta,
        "loaded": live_atten is not None,
    }


@app.post("/api/denoise-settings")
async def update_denoise_settings(update: DenoiseSettingsUpdate):
    """
    Live-tune outdoor-mic noise suppression - takes effect immediately, no
    PipeWire restart needed. 0 = fully bypassed, 100 = full/unlimited
    suppression (this cut speech mid-word in testing - the UI should warn
    before letting it go that high). post_filter_beta is optional -
    omitting it (or sending null) leaves that setting untouched.
    """
    audio = get_audio_controller()
    ok = await asyncio.to_thread(audio.set_denoise_attenuation, update.attenuation_limit_db)
    if not ok:
        raise HTTPException(
            status_code=500,
            detail="Failed to apply - is the DeepFilterNet filter loaded? (97-drivethru-deepfilter.conf)",
        )

    config = get_config()
    config.set_denoise_attenuation_limit_db(update.attenuation_limit_db)

    if update.post_filter_beta is not None:
        await asyncio.to_thread(audio.set_denoise_post_filter_beta, update.post_filter_beta)
        config.set_denoise_post_filter_beta(update.post_filter_beta)

    return {
        "status": "ok",
        "attenuation_limit_db": update.attenuation_limit_db,
        "post_filter_beta": update.post_filter_beta,
    }


@app.get("/api/tuning/hours")
async def tuning_list_hours():
    """List recorded hours available to the offline Mic Tuning Lab (see
    server/tuning_lab.py) - only ones with a usable, non-empty raw
    capture, newest first."""
    return {"hours": await asyncio.to_thread(tuning_lab.list_hours)}


@app.post("/api/tuning/clip")
async def tuning_get_clip(req: TuningClipRequest):
    """Cut a short raw(+filtered) clip from a recorded hour for
    listening/processing."""
    try:
        return await asyncio.to_thread(tuning_lab.get_clip, req.hour_id, req.start_sec, req.duration_sec)
    except tuning_lab.TuningLabError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/tuning/candidate")
async def tuning_generate_candidate(req: TuningCandidateRequest):
    """Run the real DeepFilterNet plugin offline (via ffmpeg's LADSPA host)
    against a recorded clip with the given control values - no live audio
    is touched. Returns a playable token plus rough before/after level
    metrics (see tuning_lab._compare_levels for what these do and don't mean)."""
    controls = {
        "atten_limit_db": req.atten_limit_db,
        "post_filter_beta": req.post_filter_beta,
        "min_proc_db": req.min_proc_db,
        "max_erb_db": req.max_erb_db,
        "max_df_db": req.max_df_db,
        "min_buf_frames": req.min_buf_frames,
    }
    try:
        return await asyncio.to_thread(
            tuning_lab.generate_candidate, req.hour_id, req.start_sec, req.duration_sec, controls,
        )
    except tuning_lab.TuningLabError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/tuning/audio/{token}")
async def tuning_get_audio(token: str):
    """Serve a clip or candidate WAV previously generated by this lab, for
    browser <audio> playback - this is how you actually hear the recorded
    mic on a device that has speakers, since the drive-thru box itself
    doesn't. token must resolve inside recordings/tuning/ (see
    tuning_lab.resolve_audio_token) - nothing else is servable this way."""
    path = tuning_lab.resolve_audio_token(token)
    if path is None:
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(path, media_type="audio/wav")


@app.get("/api/sensor-settings")
async def get_sensor_settings():
    """Get the car-detection distance band / hysteresis / stability tuning."""
    config = get_config()
    global presence_filter
    return {
        "detect_min_cm": config.detect_min_cm,
        "detect_max_cm": config.detect_max_cm,
        "arrival_hold_sec": config.arrival_hold_sec,
        "departure_hold_sec": config.departure_hold_sec,
        "steady_sec": config.steady_sec,
        "avg_distance_cm": round(presence_filter.avg_distance_cm, 1) if presence_filter else None,
        "is_stable": presence_filter.is_stable if presence_filter else None,
    }


@app.post("/api/sensor-settings")
async def update_sensor_settings(update: SensorSettingsUpdate):
    """
    Live-tune the distance band (cm), hold times (sec), and required
    steadiness a car must be detected with before it counts as
    arrived/departed - takes effect immediately on the running presence
    filter, no restart needed. The band is compared against a 3-second
    rolling average of the sensor's raw readings; steady_sec rejects
    readings that are still bouncing around before they even reach that
    average (sensor noise/interference vs. a car actually sitting still).
    """
    if update.detect_min_cm < 0 or update.detect_max_cm < 0:
        raise HTTPException(status_code=400, detail="Distances can't be negative")
    if update.detect_min_cm >= update.detect_max_cm:
        raise HTTPException(status_code=400, detail="detect_min_cm must be less than detect_max_cm")
    if update.arrival_hold_sec < 0 or update.departure_hold_sec < 0:
        raise HTTPException(status_code=400, detail="Hold times can't be negative")
    if update.steady_sec < 0:
        raise HTTPException(status_code=400, detail="steady_sec can't be negative")

    global presence_filter
    if presence_filter:
        presence_filter.update_settings(
            min_distance_cm=update.detect_min_cm,
            max_distance_cm=update.detect_max_cm,
            arrival_hold_sec=update.arrival_hold_sec,
            departure_hold_sec=update.departure_hold_sec,
            steady_sec=update.steady_sec,
        )

    config = get_config()
    config.set_sensor_settings(
        update.detect_min_cm,
        update.detect_max_cm,
        update.arrival_hold_sec,
        update.departure_hold_sec,
        update.steady_sec,
    )
    return {
        "status": "ok",
        "detect_min_cm": update.detect_min_cm,
        "detect_max_cm": update.detect_max_cm,
        "arrival_hold_sec": update.arrival_hold_sec,
        "departure_hold_sec": update.departure_hold_sec,
        "steady_sec": update.steady_sec,
    }


@app.post("/api/sensor-reset")
async def reset_sensor():
    """
    Manually reset the presence filter back to empty/idle - for staff to
    use when the sensor gets stuck showing a car present (sensor noise, a
    stationary object left in the detection zone) instead of cleanly
    seeing the car leave. If a car was actually being tracked as present,
    this logs a proper departure (with duration) exactly like the sensor
    detecting it leaving normally would - it's not a silent wipe.
    """
    global presence_filter
    if not presence_filter:
        raise HTTPException(status_code=503, detail="Sensor not initialized")
    presence_filter.force_departure()
    return {"status": "ok", "lane_status": presence_filter.state.value}


# Built-in arrival-chime presets, plus "custom" for whatever's been uploaded.
CHIME_PRESETS = {
    "classic": "server/assets/chimes/classic.wav",
    "double_beep": "server/assets/chimes/double_beep.wav",
    "soft": "server/assets/chimes/soft.wav",
    "urgent": "server/assets/chimes/urgent.wav",
}
CHIME_CUSTOM_PATH = "server/assets/chimes/custom.wav"


@app.get("/api/chime-settings")
async def get_chime_settings():
    """Get the available arrival-chime sounds and which one is selected."""
    config = get_config()
    project_root = Path(__file__).parent.parent
    current = str(config.chime_path.relative_to(project_root)) if config.chime_path.is_relative_to(project_root) else str(config.chime_path)

    selected = "custom" if current == CHIME_CUSTOM_PATH else next(
        (name for name, path in CHIME_PRESETS.items() if path == current), "classic"
    )
    return {
        "presets": list(CHIME_PRESETS.keys()),
        "selected": selected,
        "custom_uploaded": (project_root / CHIME_CUSTOM_PATH).exists(),
    }


@app.post("/api/chime-settings")
async def update_chime_settings(request: ChimeSelectRequest):
    """Select which sound plays on car arrival - a built-in preset, or
    'custom' for whatever's been uploaded via /api/chime-upload."""
    config = get_config()
    project_root = Path(__file__).parent.parent

    if request.chime == "custom":
        if not (project_root / CHIME_CUSTOM_PATH).exists():
            raise HTTPException(status_code=400, detail="No custom chime uploaded yet")
        path = CHIME_CUSTOM_PATH
    elif request.chime in CHIME_PRESETS:
        path = CHIME_PRESETS[request.chime]
    else:
        raise HTTPException(status_code=400, detail=f"Unknown chime: {request.chime}")

    config.set_chime_path(path)
    return {"status": "ok", "chime": request.chime}


@app.post("/api/chime-upload")
async def upload_chime(file: UploadFile = File(...)):
    """Upload a custom arrival-chime sound (WAV). Saved as custom.wav and
    selected immediately - use /api/chime-settings to switch back to a
    preset without losing the upload."""
    MAX_SIZE = 5 * 1024 * 1024
    data = await file.read(MAX_SIZE + 1)
    if len(data) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 5MB)")
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    project_root = Path(__file__).parent.parent
    dest = project_root / CHIME_CUSTOM_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)

    # Validate it's actually a playable WAV - reject and clean up otherwise.
    import wave
    try:
        with wave.open(str(dest), "rb") as w:
            if w.getnframes() == 0:
                raise ValueError("no audio frames")
    except Exception as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Not a valid WAV file: {e}")

    config = get_config()
    config.set_chime_path(CHIME_CUSTOM_PATH)
    return {"status": "ok", "chime": "custom"}


@app.get("/api/bluetooth/scan")
async def bluetooth_scan(duration: float = 8.0):
    """Scan for nearby Bluetooth devices (e.g. a staff headset in pairing mode)."""
    duration = max(2.0, min(duration, 20.0))
    devices = await asyncio.to_thread(bluetooth_control.scan, duration)
    return {"devices": devices}


@app.get("/api/bluetooth/devices")
async def bluetooth_devices():
    """List paired Bluetooth devices with live connection state."""
    paired = await asyncio.to_thread(bluetooth_control.list_paired)
    infos = await asyncio.gather(*[
        asyncio.to_thread(bluetooth_control.device_info, mac) for mac in paired
    ])
    return {"devices": list(infos)}


@app.post("/api/bluetooth/connect")
async def bluetooth_connect(request: BluetoothMacRequest):
    """
    Pair (if needed), trust, and connect a Bluetooth headset, then set it
    as the active headset for the intercom.
    """
    mac = request.mac
    if not bluetooth_control.is_valid_mac(mac):
        raise HTTPException(status_code=400, detail="Invalid MAC address")

    paired = await asyncio.to_thread(bluetooth_control.list_paired)
    if mac not in paired:
        ok, message = await asyncio.to_thread(bluetooth_control.pair, mac)
        if not ok:
            logger.warning(f"Bluetooth pairing failed for {mac}: {message}")
            raise HTTPException(status_code=500, detail=f"Pairing failed: {message}")

    ok, message = await asyncio.to_thread(bluetooth_control.connect, mac)
    if not ok:
        logger.warning(f"Bluetooth connect failed for {mac}: {message}")
        raise HTTPException(status_code=500, detail=f"Connect failed: {message}")

    sink, source = await asyncio.to_thread(bluetooth_control.find_headset_nodes, mac)
    if not sink and not source:
        return {
            "status": "connected",
            "warning": "Connected, but no PipeWire audio nodes were found yet. "
                       "Try 'Refresh Audio Devices' in a few seconds.",
        }

    config = get_config()
    config.set_headset_nodes(sink or config.headset_sink_node, source or config.headset_source_node)

    audio = get_audio_controller()
    audio.headset_sink_node = config.headset_sink_node
    audio.headset_source_node = config.headset_source_node
    audio.refresh_node_ids()
    audio.set_headset_volume(audio.volumes.get("headset", 1.0))
    audio.set_indoor_mic_volume(audio.volumes.get("indoor_mic", 1.0))
    get_level_meter().update_targets({
        "headset": audio.headset_sink_node,
        "indoor_mic": audio.headset_source_node,
    })

    return {
        "status": "connected",
        "headset_sink": sink,
        "headset_source": source,
    }


@app.post("/api/bluetooth/disconnect")
async def bluetooth_disconnect(request: BluetoothMacRequest):
    """Disconnect a Bluetooth device without forgetting it."""
    ok, message = await asyncio.to_thread(bluetooth_control.disconnect, request.mac)
    if not ok:
        logger.warning(f"Bluetooth disconnect failed for {request.mac}: {message}")
        raise HTTPException(status_code=500, detail=message)
    return {"status": "ok"}


@app.post("/api/bluetooth/forget")
async def bluetooth_forget(request: BluetoothMacRequest):
    """Unpair and remove a Bluetooth device."""
    ok, message = await asyncio.to_thread(bluetooth_control.forget, request.mac)
    if not ok:
        logger.warning(f"Bluetooth forget failed for {request.mac}: {message}")
        raise HTTPException(status_code=500, detail=message)
    return {"status": "ok"}


def main():
    """Run the server."""
    import uvicorn

    config = get_config()
    uvicorn.run(
        "server.main:app",
        host=config.server_host,
        port=config.server_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
