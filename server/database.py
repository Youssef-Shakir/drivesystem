"""SQLite database for visit logging and statistics."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, date
from pathlib import Path
from typing import Generator, Optional

from .models import Stats, Visit


class Database:
    """SQLite database for storing visit records."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        with self._connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS visits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    arrived_at TIMESTAMP NOT NULL,
                    left_at TIMESTAMP,
                    service_duration_sec REAL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_visits_arrived_at
                ON visits(arrived_at)
            """)
            conn.commit()

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Get a database connection."""
        conn = sqlite3.connect(
            self.db_path,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
        )
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def log_arrival(self) -> int:
        """Log a car arrival. Returns the visit ID."""
        with self._connection() as conn:
            cursor = conn.execute(
                "INSERT INTO visits (arrived_at) VALUES (?)",
                (datetime.now(),)
            )
            conn.commit()
            return cursor.lastrowid or 0

    def log_departure(self, service_duration_sec: float) -> Optional[int]:
        """
        Log a car departure for the most recent open visit.
        Returns the visit ID or None if no open visit.
        """
        with self._connection() as conn:
            # Find the most recent visit without a departure
            row = conn.execute(
                "SELECT id FROM visits WHERE left_at IS NULL ORDER BY arrived_at DESC LIMIT 1"
            ).fetchone()

            if row:
                visit_id = row["id"]
                conn.execute(
                    "UPDATE visits SET left_at = ?, service_duration_sec = ? WHERE id = ?",
                    (datetime.now(), service_duration_sec, visit_id)
                )
                conn.commit()
                return visit_id
            return None

    def get_stats(self, for_date: Optional[date] = None) -> Stats:
        """Get statistics for a given date (defaults to today)."""
        if for_date is None:
            for_date = date.today()

        start_of_day = datetime.combine(for_date, datetime.min.time())
        end_of_day = datetime.combine(for_date, datetime.max.time())

        with self._connection() as conn:
            # Cars today (completed visits only)
            row = conn.execute(
                """
                SELECT COUNT(*) as count
                FROM visits
                WHERE arrived_at >= ? AND arrived_at <= ?
                AND left_at IS NOT NULL
                """,
                (start_of_day, end_of_day)
            ).fetchone()
            cars_today = row["count"] if row else 0

            # Average service time today
            row = conn.execute(
                """
                SELECT AVG(service_duration_sec) as avg_time
                FROM visits
                WHERE arrived_at >= ? AND arrived_at <= ?
                AND service_duration_sec IS NOT NULL
                """,
                (start_of_day, end_of_day)
            ).fetchone()
            avg_service_time = row["avg_time"] if row and row["avg_time"] else 0.0

            # Total cars all time
            row = conn.execute(
                "SELECT COUNT(*) as count FROM visits WHERE left_at IS NOT NULL"
            ).fetchone()
            total_cars = row["count"] if row else 0

            return Stats(
                cars_today=cars_today,
                avg_service_time_sec=round(avg_service_time, 1),
                total_cars_all_time=total_cars
            )

    def get_recent_visits(self, limit: int = 10) -> list[Visit]:
        """Get recent visits."""
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT id, arrived_at, left_at, service_duration_sec
                FROM visits
                ORDER BY arrived_at DESC
                LIMIT ?
                """,
                (limit,)
            ).fetchall()

            return [
                Visit(
                    id=row["id"],
                    arrived_at=row["arrived_at"],
                    left_at=row["left_at"],
                    service_duration_sec=row["service_duration_sec"]
                )
                for row in rows
            ]


# Global database instance
_db: Optional[Database] = None


def get_database() -> Database:
    """Get the global database instance."""
    global _db
    if _db is None:
        from .config import get_config
        _db = Database(get_config().database_path)
    return _db


def init_database(db_path: str | Path) -> Database:
    """Initialize the global database instance."""
    global _db
    _db = Database(db_path)
    return _db
