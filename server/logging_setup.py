"""
Persistent, rotating log file for later diagnosis.

journalctl already captures stdout (`journalctl --user -u drivethru`), but
that requires SSH access and knowing the right incantation. This mirrors
everything the app already logs into a plain file under logs/ that's easy
to pull up, download, or view from the dashboard - subject to its own
rotation so it never grows unbounded.
"""

import logging
import logging.handlers
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_FILE = LOG_DIR / "drivethru.log"

# 10MB x 5 backups (~50MB max) - enough history to diagnose a problem from
# the last few days without eating the disk over the system's lifetime.
MAX_BYTES = 10 * 1024 * 1024
BACKUP_COUNT = 5


def setup_logging(level: int = logging.INFO) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    root = logging.getLogger()
    root.setLevel(level)

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT,
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)


def read_recent_log_lines(n: int = 200) -> list[str]:
    """Read up to the last n lines from the current (non-rotated) log file."""
    if not LOG_FILE.exists():
        return []
    try:
        with open(LOG_FILE, "r", errors="replace") as f:
            lines = f.readlines()
        return [line.rstrip("\n") for line in lines[-n:]]
    except Exception:
        return []
