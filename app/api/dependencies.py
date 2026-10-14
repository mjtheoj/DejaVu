"""Session authentication and office-role dependency helpers."""
from __future__ import annotations
from typing import Any
from fastapi import HTTPException, Request
from app.core.database import connect_db

def user_payload(row: sqlite3.Row) -> dict[str, Any]:
    return {"id": row["id"], "email": row["email"], "display_name": row["display_name"], "role": row["role"]}


async def authenticated_user(request: Request) -> dict[str, Any]:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Please sign in.")
    with connect_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not row:
        request.session.clear()
        raise HTTPException(status_code=401, detail="Session expired. Please sign in again.")
    return user_payload(row)


def require_office(user: dict[str, Any]) -> None:
    if user["role"] != "office":
        raise HTTPException(status_code=403, detail="Office staff access required.")
