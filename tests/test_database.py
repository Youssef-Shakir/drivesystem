"""Tests for the database module."""

import os
import tempfile
from datetime import datetime, date, timedelta

import pytest

from server.database import Database
from server.models import Stats


class TestDatabase:
    """Tests for Database class."""

    @pytest.fixture
    def db(self):
        """Create a temporary database for testing."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        database = Database(path)
        yield database
        os.unlink(path)

    def test_database_creation(self, db):
        """Database initializes with empty tables."""
        stats = db.get_stats()
        assert stats.cars_today == 0
        assert stats.avg_service_time_sec == 0.0
        assert stats.total_cars_all_time == 0

    def test_log_arrival(self, db):
        """log_arrival creates a visit record."""
        visit_id = db.log_arrival()
        assert visit_id > 0

        visits = db.get_recent_visits()
        assert len(visits) == 1
        assert visits[0].id == visit_id
        assert visits[0].arrived_at is not None
        assert visits[0].left_at is None

    def test_log_departure(self, db):
        """log_departure completes the most recent visit."""
        visit_id = db.log_arrival()

        departed_id = db.log_departure(service_duration_sec=120.5)

        assert departed_id == visit_id

        visits = db.get_recent_visits()
        assert len(visits) == 1
        assert visits[0].left_at is not None
        assert visits[0].service_duration_sec == 120.5

    def test_log_departure_no_open_visit(self, db):
        """log_departure with no open visit returns None."""
        result = db.log_departure(60.0)
        assert result is None

    def test_log_departure_matches_most_recent(self, db):
        """log_departure updates the most recent open visit."""
        db.log_arrival()  # First visit
        visit2_id = db.log_arrival()  # Second visit (most recent)

        departed_id = db.log_departure(30.0)
        assert departed_id == visit2_id

    def test_stats_cars_today(self, db):
        """get_stats returns correct cars_today count."""
        # Create some completed visits
        db.log_arrival()
        db.log_departure(60.0)
        db.log_arrival()
        db.log_departure(90.0)

        # One incomplete visit (shouldn't count)
        db.log_arrival()

        stats = db.get_stats()
        assert stats.cars_today == 2  # Only completed visits

    def test_stats_avg_service_time(self, db):
        """get_stats returns correct average service time."""
        db.log_arrival()
        db.log_departure(60.0)  # 1 minute
        db.log_arrival()
        db.log_departure(120.0)  # 2 minutes

        stats = db.get_stats()
        # Average of 60 and 120 = 90
        assert stats.avg_service_time_sec == 90.0

    def test_stats_total_all_time(self, db):
        """get_stats returns correct total_cars_all_time."""
        for i in range(5):
            db.log_arrival()
            db.log_departure(float(i * 30))

        stats = db.get_stats()
        assert stats.total_cars_all_time == 5

    def test_stats_empty_database(self, db):
        """get_stats handles empty database gracefully."""
        stats = db.get_stats()
        assert stats.cars_today == 0
        assert stats.avg_service_time_sec == 0.0
        assert stats.total_cars_all_time == 0

    def test_stats_for_specific_date(self, db):
        """get_stats can query specific dates."""
        # Add visits today
        db.log_arrival()
        db.log_departure(60.0)

        # Query for tomorrow (should be empty)
        tomorrow = date.today() + timedelta(days=1)
        stats = db.get_stats(for_date=tomorrow)
        assert stats.cars_today == 0

    def test_get_recent_visits_limit(self, db):
        """get_recent_visits respects limit parameter."""
        for i in range(10):
            db.log_arrival()
            db.log_departure(float(i * 10))

        visits = db.get_recent_visits(limit=5)
        assert len(visits) == 5

    def test_get_recent_visits_order(self, db):
        """get_recent_visits returns most recent first."""
        db.log_arrival()
        db.log_departure(10.0)
        db.log_arrival()
        db.log_departure(20.0)
        db.log_arrival()
        db.log_departure(30.0)

        visits = db.get_recent_visits()
        # Most recent should have highest service duration (30)
        assert visits[0].service_duration_sec == 30.0
        assert visits[2].service_duration_sec == 10.0

    def test_multiple_arrivals_and_departures(self, db):
        """Handles rapid arrivals and departures correctly."""
        # Simulate busy period
        ids = []
        for _ in range(3):
            ids.append(db.log_arrival())

        # Depart in reverse order
        for _ in range(3):
            db.log_departure(45.0)

        stats = db.get_stats()
        assert stats.cars_today == 3

    def test_avg_service_time_rounds(self, db):
        """Average service time is rounded to 1 decimal."""
        db.log_arrival()
        db.log_departure(33.333)
        db.log_arrival()
        db.log_departure(66.667)

        stats = db.get_stats()
        # (33.333 + 66.667) / 2 = 50.0
        assert stats.avg_service_time_sec == 50.0
