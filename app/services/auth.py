"""Short-window login throttling for the demo and local deployments."""
from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timedelta, timezone

LOGIN_ATTEMPT_LIMIT = 5
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_LOCKOUT_SECONDS = 15 * 60


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def login_lockout_remaining(conn: sqlite3.Connection, subjects: list[str], now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    remaining = 0
    for subject in subjects:
        row = conn.execute("SELECT locked_until FROM login_attempts WHERE subject=?", (subject,)).fetchone()
        locked_until = _parse_timestamp(row["locked_until"] if row else None)
        if locked_until and locked_until > now:
            remaining = max(remaining, math.ceil((locked_until - now).total_seconds()))
    return remaining


def record_failed_login(conn: sqlite3.Connection, subjects: list[str], now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    stamp = now.isoformat(timespec="seconds")
    window_start = now - timedelta(seconds=LOGIN_WINDOW_SECONDS)
    for subject in subjects:
        row = conn.execute(
            "SELECT failure_count, window_started_at, locked_until FROM login_attempts WHERE subject=?",
            (subject,),
        ).fetchone()
        previous_start = _parse_timestamp(row["window_started_at"] if row else None)
        previous_lock = _parse_timestamp(row["locked_until"] if row else None)
        if not row or previous_start is None or previous_start < window_start or (previous_lock and previous_lock <= now):
            failures = 1
            started = stamp
        else:
            failures = int(row["failure_count"]) + 1
            started = row["window_started_at"]
        locked_until = (now + timedelta(seconds=LOGIN_LOCKOUT_SECONDS)).isoformat(timespec="seconds") if failures >= LOGIN_ATTEMPT_LIMIT else None
        conn.execute(
            """INSERT INTO login_attempts(subject, failure_count, window_started_at, locked_until)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(subject) DO UPDATE SET failure_count=excluded.failure_count,
                 window_started_at=excluded.window_started_at, locked_until=excluded.locked_until""",
            (subject, failures, started, locked_until),
        )


def clear_login_failures(conn: sqlite3.Connection, subjects: list[str]) -> None:
    conn.executemany("DELETE FROM login_attempts WHERE subject=?", [(subject,) for subject in subjects])
