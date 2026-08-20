"""Append-only log of QR scans, kept as CSV in data/scan_log.csv."""

import csv
from datetime import datetime, timezone
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parent / "data" / "scan_log.csv"
FIELDS = ["timestamp", "session_id", "location", "previous_location"]


def record_scan(location_name: str, session_id: str, previous_location: str | None) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    is_new = not LOG_PATH.exists()

    with LOG_PATH.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if is_new:
            writer.writeheader()
        writer.writerow({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "location": location_name,
            "previous_location": previous_location or "",
        })


def read_scans(limit: int = 50) -> list[dict]:
    if not LOG_PATH.exists():
        return []

    with LOG_PATH.open(newline="") as f:
        rows = list(csv.DictReader(f))

    return list(reversed(rows))[:limit]
