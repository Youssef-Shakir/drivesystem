"""
Serial listener for ESP32 sensor communication.

Handles auto-reconnect and heartbeat timeout detection.
"""

import logging
import re
import threading
import time
from datetime import datetime
from typing import Callable, Optional

import serial

logger = logging.getLogger(__name__)

# Some sensor nodes (e.g. the ESP32 firmware in esp32/sensor_node) do their
# own arrival/departure filtering onboard and send CAR_ARRIVED/CAR_LEFT plus
# "HB <dist_cm>" heartbeats. Others are a bare ultrasonic distance module
# that just streams a plain number every reading, e.g. "24.6\r\n" - no
# framing, no events. This matches either an int or a decimal.
_RAW_DISTANCE_RE = re.compile(r"^-?\d+(\.\d+)?$")


class SerialListener:
    """
    Listens for serial data from the ESP32 sensor node.

    Features:
    - Auto-reconnect on connection loss
    - Heartbeat timeout detection (sensor offline)
    - Thread-safe event callbacks
    """

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        heartbeat_timeout_sec: float = 15.0,
        on_event: Optional[Callable[[str], None]] = None,
        on_connection_change: Optional[Callable[[bool], None]] = None,
        on_heartbeat: Optional[Callable[[int], None]] = None,
    ):
        """
        Initialize the serial listener.

        Args:
            port: Serial port path (e.g., /dev/ttyUSB0)
            baudrate: Baud rate (default 115200)
            heartbeat_timeout_sec: Seconds without heartbeat before offline
            on_event: Callback for all events (CAR_ARRIVED, CAR_LEFT, HB)
            on_connection_change: Callback when connection state changes
            on_heartbeat: Callback for heartbeat with distance value
        """
        self.port = port
        self.baudrate = baudrate
        self.heartbeat_timeout_sec = heartbeat_timeout_sec
        self.on_event = on_event
        self.on_connection_change = on_connection_change
        self.on_heartbeat = on_heartbeat

        self._serial: Optional[serial.Serial] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._connected = False
        self._last_heartbeat: Optional[datetime] = None
        self._last_distance: int = 0
        self._lock = threading.Lock()

    @property
    def connected(self) -> bool:
        """Whether currently connected to the serial port."""
        with self._lock:
            return self._connected

    @property
    def last_heartbeat(self) -> Optional[datetime]:
        """Timestamp of last heartbeat received."""
        with self._lock:
            return self._last_heartbeat

    @property
    def last_distance(self) -> int:
        """Last distance reading from heartbeat."""
        with self._lock:
            return self._last_distance

    @property
    def is_sensor_online(self) -> bool:
        """Whether sensor is online (received heartbeat recently)."""
        with self._lock:
            if self._last_heartbeat is None:
                return False
            elapsed = (datetime.now() - self._last_heartbeat).total_seconds()
            return elapsed < self.heartbeat_timeout_sec

    def start(self) -> None:
        """Start the listener thread."""
        if self._thread is not None and self._thread.is_alive():
            logger.warning("Listener already running")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info(f"Serial listener started on {self.port}")

    def stop(self) -> None:
        """Stop the listener thread."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        self._close_serial()
        logger.info("Serial listener stopped")

    def _close_serial(self) -> None:
        """Close serial port if open."""
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None
            self._set_connected(False)

    def _set_connected(self, connected: bool) -> None:
        """Update connection state and notify callback."""
        with self._lock:
            if self._connected != connected:
                self._connected = connected
                if self.on_connection_change:
                    try:
                        self.on_connection_change(connected)
                    except Exception as e:
                        logger.error(f"Connection callback error: {e}")

    def _connect(self) -> bool:
        """Attempt to connect to the serial port."""
        try:
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=1.0,
            )
            self._set_connected(True)
            logger.info(f"Connected to {self.port}")
            return True
        except serial.SerialException as e:
            logger.debug(f"Failed to connect to {self.port}: {e}")
            self._serial = None
            self._set_connected(False)
            return False

    def _process_line(self, line: str) -> None:
        """Process a line of data from the serial port."""
        line = line.strip()
        if not line:
            return

        logger.debug(f"Serial rx: {line}")

        # A bare number - a distance-only sensor with no onboard event
        # framing (see _RAW_DISTANCE_RE above). Treat it exactly like a
        # heartbeat: update distance/last-seen and fire on_heartbeat, but
        # there's no CAR_ARRIVED/CAR_LEFT/HB text to hand to on_event here -
        # the presence filter derives arrival/departure from the distance
        # itself (see PresenceFilter.process_distance).
        if _RAW_DISTANCE_RE.match(line):
            with self._lock:
                self._last_heartbeat = datetime.now()
                try:
                    self._last_distance = round(float(line))
                except ValueError:
                    pass

            if self.on_heartbeat:
                try:
                    self.on_heartbeat(self._last_distance)
                except Exception as e:
                    logger.error(f"Heartbeat callback error: {e}")
            return

        # Update heartbeat timestamp
        if line.startswith("HB "):
            with self._lock:
                self._last_heartbeat = datetime.now()
                try:
                    self._last_distance = int(line[3:])
                except ValueError:
                    pass

            if self.on_heartbeat:
                try:
                    self.on_heartbeat(self._last_distance)
                except Exception as e:
                    logger.error(f"Heartbeat callback error: {e}")

        # Any valid message counts as activity
        if line in ("CAR_ARRIVED", "CAR_LEFT", "SENSOR_READY") or line.startswith("HB "):
            with self._lock:
                self._last_heartbeat = datetime.now()

        # Call event callback
        if self.on_event:
            try:
                self.on_event(line)
            except Exception as e:
                logger.error(f"Event callback error: {e}")

    def _run(self) -> None:
        """Main listener loop."""
        reconnect_delay = 1.0
        max_reconnect_delay = 30.0

        while not self._stop_event.is_set():
            # Try to connect if not connected
            if self._serial is None:
                if self._connect():
                    reconnect_delay = 1.0  # Reset delay on successful connect
                else:
                    # Wait before retry with exponential backoff
                    self._stop_event.wait(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)
                    continue

            # Read data
            try:
                if self._serial.in_waiting > 0:
                    line = self._serial.readline().decode("utf-8", errors="ignore")
                    self._process_line(line)
                else:
                    # Small sleep to prevent busy loop
                    time.sleep(0.01)

            except serial.SerialException as e:
                logger.warning(f"Serial error: {e}")
                self._close_serial()
            except Exception as e:
                logger.error(f"Unexpected error in serial listener: {e}")
                self._close_serial()


# Global serial listener instance
_listener: Optional[SerialListener] = None


def get_serial_listener() -> Optional[SerialListener]:
    """Get the global serial listener instance."""
    return _listener


def init_serial_listener(
    port: str,
    baudrate: int = 115200,
    heartbeat_timeout_sec: float = 15.0,
    on_event: Optional[Callable[[str], None]] = None,
    on_connection_change: Optional[Callable[[bool], None]] = None,
    on_heartbeat: Optional[Callable[[int], None]] = None,
) -> SerialListener:
    """Initialize the global serial listener instance."""
    global _listener
    if _listener is not None:
        _listener.stop()
    _listener = SerialListener(
        port=port,
        baudrate=baudrate,
        heartbeat_timeout_sec=heartbeat_timeout_sec,
        on_event=on_event,
        on_connection_change=on_connection_change,
        on_heartbeat=on_heartbeat,
    )
    return _listener
