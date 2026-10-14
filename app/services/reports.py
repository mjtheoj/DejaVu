"""Report reads, visibility rules and serialisation."""
from __future__ import annotations
import secrets, sqlite3
from typing import Any
from fastapi import HTTPException
from app.core.config import CATEGORY_DEFAULT_LEVEL, CATEGORY_LABELS, SENSITIVE_CATEGORIES

def read_report(conn: sqlite3.Connection, report_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Report not found.")
    return row


def location_label(row: sqlite3.Row, internal: bool = False) -> str:
    parts = [row["location_block"], "Floor " + row["location_floor"] if row["location_floor"] else None]
    if internal or row["category"] not in SENSITIVE_CATEGORIES:
        parts.extend([row["location_room"], row["location_area"]])
    else:
        parts.append(row["location_area"])
    return " · ".join(x for x in parts if x) or "Location not specified"


def serialise_report(row: sqlite3.Row, internal: bool = False) -> dict[str, Any]:
    hidden_image = row["category"] in SENSITIVE_CATEGORIES and not internal
    result = {
        "id": row["id"],
        "public_ref": row["public_ref"],
        "report_type": row["report_type"],
        "title": row["title"],
        "description": row["description"],
        "brand": row["brand"],
        "primary_color": row["primary_color"],
        "visible_features": row["visible_features"],
        "category": row["category"],
        "category_label": CATEGORY_LABELS.get(row["category"], row["category"]),
        "occurred_at": row["occurred_at"],
        "location": location_label(row, internal=internal),
        "location_block": row["location_block"],
        "location_floor": row["location_floor"],
        "location_room": row["location_room"] if internal else None,
        "location_area": row["location_area"],
        "image_url": None if hidden_image or not row["image_path"] else "/api/reports/" + row["id"] + "/image",
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    if internal:
        result.update({
            "tag_id": row["tag_id"],
            "private_verification_detail": row["private_detail"],
            "value_band": row["value_band"],
            "sensitivity_level": row["sensitivity_level"],
            "verification_level": row["verification_level"],
            "storage_location": row["storage_location"] if row["tag_id"] else None,
            "created_by": row["created_by"],
        })
    return result


def new_public_ref() -> str:
    return "LL-" + secrets.token_hex(3).upper()


def effective_level(category: str, value_band: str, sensitivity_level: int) -> int:
    level = CATEGORY_DEFAULT_LEVEL.get(category, 3)
    if value_band == "high":
        level = max(level, 3)
    if sensitivity_level >= 3:
        level = 4
    elif sensitivity_level == 2:
        level = max(level, 3)
    return level


def report_visible_to_student(row: sqlite3.Row, user: dict[str, Any]) -> bool:
    if row["created_by"] == user["id"]:
        return True
    return row["report_type"] == "found" and row["status"] == "available"
