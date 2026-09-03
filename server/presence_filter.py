"""
Presence filter state machine for car detection.

Processes raw sensor events from the ESP32 and provides filtered
car arrival/departure events with hysteresis.
"""

from collections import deque
from datetime import datetime
from enum import Enum
from typing import Callable, Optional

# How far back to average raw distance readings before comparing against
# the min/max band - smooths out single-reading noise/spikes from the
# ultrasonic sensor.
AVG_WINDOW_SEC = 3.0

# Max reading-to-reading spread (cm) allowed within the steady_sec window
# for a run of readings to be trusted at all. A car sitting still gives a
# steady reading; spurious echoes/interference with nothing actually in
# front of the sensor bounce around well past this.
STABILITY_TOLERANCE_CM = 15.0


class PresenceState(Enum):
    """State machine states."""
    IDLE = "idle"               # No car, waiting for detection
    DETECTING = "detecting"     # Object detected, waiting for confirmation
    CAR_PRESENT = "car_present" # Car confirmed present
    DEPARTING = "departing"     # Object gone, waiting for departure confirmation


class PresenceFilter:
    """
    State machine that filters raw distance readings to detect car presence.

    Some sensor nodes (the ESP32 firmware in esp32/sensor_node) do their own
    filtering onboard and send CAR_ARRIVED/CAR_LEFT events directly - see
    process_event(). Others (e.g. a bare ultrasonic distance module wired
    straight to the serial port) only ever stream a raw distance reading -
    see process_distance(), which runs the same threshold + hysteresis
    state machine as the ESP32 firmware's updateState(), just in Python.
    Both paths converge on the same on_car_arrived/on_car_left callbacks.
    """

    def __init__(
        self,
        min_distance_cm: int = 50,
        max_distance_cm: int = 100,
        arrival_hold_sec: float = 2.0,
        departure_hold_sec: float = 3.0,
        steady_sec: float = 1.0,
        on_car_arrived: Optional[Callable[[], None]] = None,
        on_car_left: Optional[Callable[[float], None]] = None,
    ):
        """
        Initialize the presence filter.

        Args:
            min_distance_cm: A car only counts as detected once the
                (3s-averaged) distance is at or above this - closer than
                this (e.g. something right up against the sensor) doesn't
                count, only used by process_distance().
            max_distance_cm: ...and at or below this - farther than this
                doesn't count either. Together min/max form the detection
                band; only used by process_distance().
            arrival_hold_sec: How long the averaged distance must stay
                inside [min_distance_cm, max_distance_cm] before it's
                confirmed as an arrived car (filters pedestrians/transients
                passing through) - only used by process_distance().
            departure_hold_sec: How long it must stay outside that band
                before the car is confirmed departed - only used by
                process_distance().
            steady_sec: How long the raw readings must stay within
                STABILITY_TOLERANCE_CM of each other before they're
                trusted at all - readings bouncing around more than that
                are treated as sensor noise/interference and ignored
                rather than fed into the arrival/departure logic. A real
                car sitting still gives a steady reading; 0 disables this
                check. Only used by process_distance().
            on_car_arrived: Callback when a car arrives
            on_car_left: Callback when a car leaves, receives service duration in seconds
        """
        self.min_distance_cm = min_distance_cm
        self.max_distance_cm = max_distance_cm
        self.arrival_hold_sec = arrival_hold_sec
        self.departure_hold_sec = departure_hold_sec
        self.steady_sec = steady_sec
        self.on_car_arrived = on_car_arrived
        self.on_car_left = on_car_left

        self._state = PresenceState.IDLE
        self._car_arrived_at: Optional[datetime] = None
        self._last_distance_cm: int = 0
        self._state_entered_at: Optional[datetime] = None
        # (timestamp, distance) samples from the last AVG_WINDOW_SEC seconds
        self._recent_readings: deque[tuple[datetime, float]] = deque()

    @property
    def state(self) -> PresenceState:
        """Current state."""
        return self._state

    @property
    def car_arrived_at(self) -> Optional[datetime]:
        """Timestamp when current car arrived."""
        return self._car_arrived_at

    @property
    def last_distance_cm(self) -> int:
        """Last known raw distance reading."""
        return self._last_distance_cm

    def _readings_within(self, seconds: float, now: datetime) -> list[float]:
        """Raw distance values from the last `seconds` seconds."""
        cutoff = now.timestamp() - seconds
        return [v for t, v in self._recent_readings if t.timestamp() >= cutoff]

    @property
    def avg_distance_cm(self) -> float:
        """Average of the raw distance readings from the last
        AVG_WINDOW_SEC seconds - this is what's actually compared against
        the min/max band, so it's what dashboard tuning should show
        against the limits."""
        window = self._readings_within(AVG_WINDOW_SEC, datetime.now())
        if not window:
            return float(self._last_distance_cm)
        return sum(window) / len(window)

    @property
    def is_stable(self) -> bool:
        """Whether the raw readings have stayed within
        STABILITY_TOLERANCE_CM of each other for the last steady_sec
        seconds - see steady_sec in __init__. Always True if steady_sec
        is 0 (disabled)."""
        if self.steady_sec <= 0:
            return True
        if not self._recent_readings:
            return False
        now = datetime.now()
        # Need a full steady_sec of history to judge, not just one fresh
        # sample right after a spike.
        oldest = self._recent_readings[0][0]
        if (now - oldest).total_seconds() < self.steady_sec:
            return False
        window = self._readings_within(self.steady_sec, now)
        if len(window) < 2:
            return False
        return (max(window) - min(window)) <= STABILITY_TOLERANCE_CM

    @property
    def is_car_present(self) -> bool:
        """Whether a car is currently present."""
        return self._state == PresenceState.CAR_PRESENT

    def process_event(self, event: str) -> None:
        """
        Process a serial event from the ESP32.

        Args:
            event: Raw event string (CAR_ARRIVED, CAR_LEFT, or HB <distance>)
        """
        event = event.strip()

        if event == "CAR_ARRIVED":
            self._handle_car_arrived()
        elif event == "CAR_LEFT":
            self._handle_car_left()
        elif event.startswith("HB "):
            try:
                distance = int(event[3:])
                self._last_distance_cm = distance
            except ValueError:
                pass  # Ignore malformed heartbeat
        elif event == "SENSOR_READY":
            # Sensor just started, reset state
            self._state = PresenceState.IDLE
            self._car_arrived_at = None
            self._state_entered_at = None

    def process_distance(self, distance_cm: int) -> None:
        """
        Process a raw distance reading (cm) from a sensor that has no
        onboard arrival/departure filtering of its own. Averages the last
        AVG_WINDOW_SEC seconds to smooth out single-reading noise, then
        runs a min/max-band + hysteresis state machine (a banded version
        of the ESP32 firmware's updateState() in
        esp32/sensor_node/sensor_node.ino) so a bare distance-only sensor
        gets the same pedestrian/transient filtering a CAR_ARRIVED/CAR_LEFT
        -capable sensor would do onboard - plus only counts a car that's
        actually in the [min_distance_cm, max_distance_cm] band, not just
        "close enough".

        Readings that are still bouncing around (see steady_sec /
        is_stable - real interference/noise with nothing actually in
        front of the sensor, as opposed to a car sitting still) never
        count as a confident "car is here" reading - that's what stops
        noise from ever *starting* or *confirming* an arrival, or from
        cancelling a departure already in progress. But unsteady readings
        are still treated as "nothing confidently there", not ignored
        outright: a car that's genuinely departed and left the sensor
        reading empty-lane noise must still be able to count as departed
        without needing readings to first go quiet on their own - freezing
        state entirely while unstable (an earlier version of this method)
        left CAR_PRESENT/DEPARTING stuck forever once the sensor got noisy
        after the car left, requiring a manual dashboard reset every time.
        """
        self._last_distance_cm = distance_cm
        now = datetime.now()

        self._recent_readings.append((now, float(distance_cm)))
        window_sec = max(AVG_WINDOW_SEC, self.steady_sec)
        cutoff = now.timestamp() - window_sec
        while self._recent_readings and self._recent_readings[0][0].timestamp() < cutoff:
            self._recent_readings.popleft()

        avg_distance = self.avg_distance_cm
        confidently_near = self.is_stable and self.min_distance_cm <= avg_distance <= self.max_distance_cm

        if self._state == PresenceState.IDLE:
            if confidently_near:
                self._state = PresenceState.DETECTING
                self._state_entered_at = now

        elif self._state == PresenceState.DETECTING:
            if not confidently_near:
                # Object moved away, or the reading's too noisy to trust -
                # either way, not a confirmed arrival in progress.
                self._state = PresenceState.IDLE
                self._state_entered_at = None
            elif self._state_entered_at and (now - self._state_entered_at).total_seconds() >= self.arrival_hold_sec:
                self._handle_car_arrived()

        elif self._state == PresenceState.CAR_PRESENT:
            if not confidently_near:
                self._state = PresenceState.DEPARTING
                self._state_entered_at = now

        elif self._state == PresenceState.DEPARTING:
            if confidently_near:
                # Object returned, with a steady reading to prove it -
                # cancel departure. A noisy/unsteady reading here does
                # NOT cancel departure (see docstring) - it just isn't
                # confident enough to prove the car came back.
                self._state = PresenceState.CAR_PRESENT
                self._state_entered_at = None
            elif self._state_entered_at and (now - self._state_entered_at).total_seconds() >= self.departure_hold_sec:
                self._handle_car_left()

    def _handle_car_arrived(self) -> None:
        """Handle CAR_ARRIVED event."""
        if self._state != PresenceState.CAR_PRESENT:
            self._state = PresenceState.CAR_PRESENT
            self._car_arrived_at = datetime.now()
            if self.on_car_arrived:
                try:
                    self.on_car_arrived()
                except Exception:
                    pass  # Don't let callback errors affect state machine

    def _handle_car_left(self) -> None:
        """Handle CAR_LEFT event (or the hysteresis-confirmed end of a
        DEPARTING window from process_distance())."""
        if self._state in (PresenceState.CAR_PRESENT, PresenceState.DEPARTING):
            service_duration = 0.0
            if self._car_arrived_at:
                service_duration = (datetime.now() - self._car_arrived_at).total_seconds()

            self._state = PresenceState.IDLE
            self._car_arrived_at = None
            self._state_entered_at = None

            if self.on_car_left:
                try:
                    self.on_car_left(service_duration)
                except Exception:
                    pass  # Don't let callback errors affect state machine

    def reset(self) -> None:
        """Reset state machine to initial state."""
        self._state = PresenceState.IDLE
        self._car_arrived_at = None
        self._last_distance_cm = 0
        self._state_entered_at = None
        self._recent_readings.clear()

    def force_departure(self) -> None:
        """Manually force the state machine back to empty/idle - for the
        dashboard's reset button, when the sensor gets stuck (noise, a
        stationary object left in the detection zone) instead of cleanly
        seeing the car actually leave. If a car was considered present or
        already departing, this logs a proper departure (with duration)
        exactly like a real CAR_LEFT would; otherwise (stuck mid-DETECTING
        from a false trigger, or already idle) it's just a clean reset -
        no departure is logged since no arrival ever was either."""
        if self._state in (PresenceState.CAR_PRESENT, PresenceState.DEPARTING):
            self._handle_car_left()
        else:
            self.reset()

    def get_waiting_time_sec(self) -> float:
        """Get how long the current car has been waiting."""
        if self._car_arrived_at and self._state == PresenceState.CAR_PRESENT:
            return (datetime.now() - self._car_arrived_at).total_seconds()
        return 0.0

    def update_settings(
        self,
        min_distance_cm: Optional[int] = None,
        max_distance_cm: Optional[int] = None,
        arrival_hold_sec: Optional[float] = None,
        departure_hold_sec: Optional[float] = None,
        steady_sec: Optional[float] = None,
    ) -> None:
        """Live-tune the detection band/hysteresis without resetting
        current state - used by the dashboard's Sensor Limits control."""
        if min_distance_cm is not None:
            self.min_distance_cm = min_distance_cm
        if max_distance_cm is not None:
            self.max_distance_cm = max_distance_cm
        if arrival_hold_sec is not None:
            self.arrival_hold_sec = arrival_hold_sec
        if departure_hold_sec is not None:
            self.departure_hold_sec = departure_hold_sec
        if steady_sec is not None:
            self.steady_sec = steady_sec
