"""Tests for the presence filter state machine."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from server.presence_filter import PresenceFilter, PresenceState


class TestPresenceFilter:
    """Tests for PresenceFilter state machine."""

    def test_initial_state(self):
        """Filter starts in IDLE state with no car."""
        pf = PresenceFilter()
        assert pf.state == PresenceState.IDLE
        assert pf.car_arrived_at is None
        assert pf.is_car_present is False
        assert pf.last_distance_cm == 0

    def test_car_arrived_event(self):
        """CAR_ARRIVED transitions to CAR_PRESENT state."""
        arrived_callback = MagicMock()
        pf = PresenceFilter(on_car_arrived=arrived_callback)

        pf.process_event("CAR_ARRIVED")

        assert pf.state == PresenceState.CAR_PRESENT
        assert pf.is_car_present is True
        assert pf.car_arrived_at is not None
        arrived_callback.assert_called_once()

    def test_car_left_event(self):
        """CAR_LEFT transitions from CAR_PRESENT to IDLE."""
        arrived_callback = MagicMock()
        left_callback = MagicMock()
        pf = PresenceFilter(
            on_car_arrived=arrived_callback,
            on_car_left=left_callback
        )

        # Car arrives first
        pf.process_event("CAR_ARRIVED")
        assert pf.is_car_present is True

        # Car leaves
        pf.process_event("CAR_LEFT")

        assert pf.state == PresenceState.IDLE
        assert pf.is_car_present is False
        assert pf.car_arrived_at is None
        left_callback.assert_called_once()

        # Callback receives service duration
        args = left_callback.call_args[0]
        assert isinstance(args[0], float)
        assert args[0] >= 0

    def test_car_left_without_arrival_ignored(self):
        """CAR_LEFT when no car is present does nothing."""
        left_callback = MagicMock()
        pf = PresenceFilter(on_car_left=left_callback)

        pf.process_event("CAR_LEFT")

        assert pf.state == PresenceState.IDLE
        left_callback.assert_not_called()

    def test_duplicate_car_arrived_ignored(self):
        """Multiple CAR_ARRIVED events don't re-trigger."""
        arrived_callback = MagicMock()
        pf = PresenceFilter(on_car_arrived=arrived_callback)

        pf.process_event("CAR_ARRIVED")
        pf.process_event("CAR_ARRIVED")
        pf.process_event("CAR_ARRIVED")

        # Should only call once
        arrived_callback.assert_called_once()

    def test_heartbeat_updates_distance(self):
        """HB <distance> updates last_distance_cm."""
        pf = PresenceFilter()

        pf.process_event("HB 120")
        assert pf.last_distance_cm == 120

        pf.process_event("HB 85")
        assert pf.last_distance_cm == 85

        pf.process_event("HB 200")
        assert pf.last_distance_cm == 200

    def test_malformed_heartbeat_ignored(self):
        """Malformed HB messages don't crash."""
        pf = PresenceFilter()

        pf.process_event("HB 100")
        assert pf.last_distance_cm == 100

        pf.process_event("HB abc")  # Invalid
        assert pf.last_distance_cm == 100  # Unchanged

        pf.process_event("HB")  # Missing value
        assert pf.last_distance_cm == 100  # Unchanged

        pf.process_event("HB ")  # Empty value
        assert pf.last_distance_cm == 100  # Unchanged

    def test_sensor_ready_resets_state(self):
        """SENSOR_READY resets state machine."""
        pf = PresenceFilter()

        pf.process_event("CAR_ARRIVED")
        assert pf.is_car_present is True

        pf.process_event("SENSOR_READY")

        assert pf.state == PresenceState.IDLE
        assert pf.car_arrived_at is None

    def test_empty_event_ignored(self):
        """Empty/whitespace events are ignored."""
        pf = PresenceFilter()

        pf.process_event("")
        pf.process_event("   ")
        pf.process_event("\n")

        assert pf.state == PresenceState.IDLE

    def test_unknown_event_ignored(self):
        """Unknown events are ignored without error."""
        pf = PresenceFilter()

        pf.process_event("UNKNOWN_EVENT")
        pf.process_event("random garbage 123")

        assert pf.state == PresenceState.IDLE

    def test_waiting_time_calculation(self):
        """get_waiting_time_sec returns correct duration."""
        pf = PresenceFilter()

        # No car = 0 wait time
        assert pf.get_waiting_time_sec() == 0.0

        pf.process_event("CAR_ARRIVED")

        # Should return a positive value (at least a tiny bit of time has passed)
        wait_time = pf.get_waiting_time_sec()
        assert wait_time >= 0.0

    def test_reset_clears_state(self):
        """reset() returns filter to initial state."""
        pf = PresenceFilter()

        pf.process_event("CAR_ARRIVED")
        pf.process_event("HB 50")

        pf.reset()

        assert pf.state == PresenceState.IDLE
        assert pf.car_arrived_at is None
        assert pf.last_distance_cm == 0

    def test_callback_exception_handled(self):
        """Exceptions in callbacks don't crash filter."""
        def bad_callback():
            raise RuntimeError("Test error")

        pf = PresenceFilter(on_car_arrived=bad_callback)

        # Should not raise
        pf.process_event("CAR_ARRIVED")
        assert pf.is_car_present is True

    def test_callback_exception_on_left_handled(self):
        """Exceptions in on_car_left callback don't crash filter."""
        def bad_callback(duration):
            raise RuntimeError("Test error")

        pf = PresenceFilter(on_car_left=bad_callback)

        pf.process_event("CAR_ARRIVED")
        # Should not raise
        pf.process_event("CAR_LEFT")
        assert pf.state == PresenceState.IDLE
