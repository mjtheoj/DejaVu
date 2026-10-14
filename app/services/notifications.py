"""Deduplicated notifications and possible-match alerts."""
from __future__ import annotations
import sqlite3, uuid
from app.core.config import UPLOAD_DIR
from app.core.database import now_iso

def notify_user(
    conn: sqlite3.Connection,
    user_id: int,
    event_key: str,
    title: str,
    message: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
) -> None:
    conn.execute(
        """INSERT OR IGNORE INTO notifications
           (id, user_id, event_key, title, message, entity_type, entity_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (uuid.uuid4().hex, user_id, event_key, title, message, entity_type, entity_id, now_iso()),
    )


def notify_role(
    conn: sqlite3.Connection,
    role: str,
    event_key: str,
    title: str,
    message: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
) -> None:
    for row in conn.execute("SELECT id FROM users WHERE role=?", (role,)).fetchall():
        notify_user(conn, row["id"], event_key, title, message, entity_type, entity_id)

def notify_possible_matches(conn: sqlite3.Connection, found_row: sqlite3.Row) -> int:
    """Create deduplicated in-app alerts for students' open lost reports."""
    from app.matching import matching_engine

    found = dict(found_row)
    if found.get("image_path"):
        found["image_path"] = str(UPLOAD_DIR / found["image_path"])
    lost_rows = conn.execute(
        """SELECT r.* FROM reports r JOIN users u ON u.id=r.created_by
           WHERE r.report_type='lost' AND r.status='open' AND u.role='student'
           ORDER BY r.created_at DESC LIMIT 200"""
    ).fetchall()
    sent = 0
    for lost_row in lost_rows:
        lost = dict(lost_row)
        if lost.get("image_path"):
            lost["image_path"] = str(UPLOAD_DIR / lost["image_path"])
        result = matching_engine.compare(lost, found)
        # This threshold is a notification heuristic. Matching scores are not probabilities.
        if result["score"] < 0.58:
            continue
        prior = conn.execute("SELECT 1 FROM notifications WHERE user_id=? AND event_key=?",
                             (lost_row["created_by"], "match:" + lost_row["id"] + ":" + found_row["id"])).fetchone()
        if prior:
            continue
        notify_user(
            conn, lost_row["created_by"], "match:" + lost_row["id"] + ":" + found_row["id"],
            "A possible item match was found",
            "A found item may be relevant to your lost report " + lost_row["public_ref"] + ". Open LostLink to review the suggested match.",
            "report", lost_row["id"],
        )
        sent += 1
    return sent


def notify_matches_for_lost_report(conn: sqlite3.Connection, lost_row: sqlite3.Row) -> int:
    """Notify the reporter when a newly created lost report matches existing office-held items."""
    from app.matching import matching_engine

    lost = dict(lost_row)
    if lost.get("image_path"):
        lost["image_path"] = str(UPLOAD_DIR / lost["image_path"])
    found_rows = conn.execute(
        """SELECT * FROM reports WHERE report_type='found' AND status='available'
           ORDER BY created_at DESC LIMIT 200"""
    ).fetchall()
    sent = 0
    for found_row in found_rows:
        found = dict(found_row)
        if found.get("image_path"):
            found["image_path"] = str(UPLOAD_DIR / found["image_path"])
        result = matching_engine.compare(lost, found)
        if result["score"] < 0.58:
            continue
        event_key = "match:" + lost_row["id"] + ":" + found_row["id"]
        prior = conn.execute(
            "SELECT 1 FROM notifications WHERE user_id=? AND event_key=?",
            (lost_row["created_by"], event_key),
        ).fetchone()
        if prior:
            continue
        notify_user(
            conn, lost_row["created_by"], event_key,
            "A possible item match was found",
            "An item already held by the campus office may be relevant to your lost report "
            + lost_row["public_ref"] + ". Open LostLink to review the suggested match.",
            "report", lost_row["id"],
        )
        sent += 1
    return sent
