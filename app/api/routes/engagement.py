"""HTTP route group."""
from fastapi import APIRouter
from app.core.runtime import *
from app.schemas import *

router = APIRouter()

@router.get("/api/notifications")
async def list_notifications(user: dict[str, Any] = Depends(authenticated_user)):
    with connect_db() as conn:
        rows = conn.execute(
            """SELECT id, title, message, entity_type, entity_id, read_at, created_at
               FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 100""",
            (user["id"],)
        ).fetchall()
        unread = conn.execute("SELECT COUNT(*) AS n FROM notifications WHERE user_id=? AND read_at IS NULL",
                              (user["id"],)).fetchone()["n"]
    return {"notifications": [dict(row) for row in rows], "unread_count": int(unread)}


@router.post("/api/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    user: dict[str, Any] = Depends(authenticated_user),
):
    with connect_db() as conn:
        cursor = conn.execute(
            "UPDATE notifications SET read_at=? WHERE id=? AND user_id=?",
            (now_iso(), notification_id, user["id"])
        )
        if not cursor.rowcount:
            raise HTTPException(status_code=404, detail="Notification not found.")
    return {"ok": True}


@router.post("/api/notifications/read-all")
async def mark_all_notifications_read(user: dict[str, Any] = Depends(authenticated_user)):
    with connect_db() as conn:
        conn.execute("UPDATE notifications SET read_at=? WHERE user_id=? AND read_at IS NULL",
                     (now_iso(), user["id"]))
    return {"ok": True}


@router.get("/api/activity/me")
async def my_activity(user: dict[str, Any] = Depends(authenticated_user)):
    if user["role"] != "student":
        raise HTTPException(status_code=403, detail="Activity rewards are available to student accounts.")
    with connect_db() as conn:
        total = points_total(conn, user["id"])
        ledger = conn.execute(
            """SELECT points, reason, report_id, created_at FROM reward_ledger
               WHERE user_id=? ORDER BY created_at DESC LIMIT 50""",
            (user["id"],)
        ).fetchall()
        certificates = conn.execute(
            """SELECT id, tier, threshold_points, points_at_issue, serial, issued_at
               FROM certificates WHERE user_id=? ORDER BY threshold_points""",
            (user["id"],)
        ).fetchall()
    next_milestone = next((m for m in CERTIFICATE_MILESTONES if total < m["threshold"]), None)
    return {
        "total_points": total,
        "rules": POINT_RULES,
        "ledger": [dict(row) for row in ledger],
        "certificates": [dict(row) for row in certificates],
        "next_milestone": next_milestone,
        "points_to_next_milestone": max(0, next_milestone["threshold"] - total) if next_milestone else 0,
        "milestones": [{"tier": m["tier"], "threshold": m["threshold"], "earned": total >= m["threshold"]}
                       for m in CERTIFICATE_MILESTONES],
    }


@router.get("/api/leaderboard")
async def contribution_leaderboard(user: dict[str, Any] = Depends(authenticated_user)):
    if user["role"] != "student":
        raise HTTPException(status_code=403, detail="The student contribution leaderboard is available to student accounts.")
    with connect_db() as conn:
        rows = conn.execute(
            """SELECT u.id, u.display_name, COALESCE(SUM(l.points), 0) AS total_points,
                      COUNT(DISTINCT l.report_id) AS verified_reports
               FROM users u JOIN reward_ledger l ON l.user_id=u.id
               WHERE u.role='student'
               GROUP BY u.id, u.display_name
               HAVING SUM(l.points) > 0
               ORDER BY total_points DESC, u.display_name COLLATE NOCASE ASC"""
        ).fetchall()
    leaders = []
    previous_points = None
    current_rank = 0
    my_rank = None
    my_points = 0
    for position, row in enumerate(rows, start=1):
        points = int(row["total_points"])
        if points != previous_points:
            current_rank = position
            previous_points = points
        entry = {
            "rank": current_rank,
            "display_name": row["display_name"],
            "total_points": points,
            "verified_reports": int(row["verified_reports"]),
            "is_me": int(row["id"]) == int(user["id"]),
        }
        if int(row["id"]) == int(user["id"]):
            my_rank = current_rank
            my_points = points
        if len(leaders) < 10:
            leaders.append(entry)
    return {
        "leaders": leaders,
        "my_rank": my_rank,
        "my_total_points": my_points,
        "participant_count": len(rows),
        "updated_at": now_iso(),
        "privacy_note": "Only display names and verified contribution totals are shown; emails and claim details are not included.",
    }


@router.get("/api/certificates/{certificate_id}/download")
async def download_certificate(
    certificate_id: str,
    user: dict[str, Any] = Depends(authenticated_user),
):
    with connect_db() as conn:
        certificate = conn.execute("SELECT * FROM certificates WHERE id=?", (certificate_id,)).fetchone()
        if not certificate:
            raise HTTPException(status_code=404, detail="Certificate not found.")
        if user["role"] != "office" and certificate["user_id"] != user["id"]:
            raise HTTPException(status_code=403, detail="You can only download your own certificates.")
        person = conn.execute("SELECT display_name FROM users WHERE id=?", (certificate["user_id"],)).fetchone()
    try:
        pdf = certificate_pdf(person["display_name"], certificate["tier"], certificate["points_at_issue"],
                              certificate["serial"], certificate["issued_at"])
    except ImportError:
        raise HTTPException(status_code=503, detail="Certificate generation dependency is not installed.")
    safe_name = "LostLink-" + certificate["tier"].lower().replace(" ", "-") + "-" + certificate["serial"] + ".pdf"
    return StreamingResponse(
        iter([pdf]),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="' + safe_name + '"',
                 "Cache-Control": "private, no-store"},
    )


@router.get("/api/office/summary")
async def office_summary(user: dict[str, Any] = Depends(authenticated_user)):
    require_office(user)
    with connect_db() as conn:
        intake = conn.execute("SELECT COUNT(*) AS n FROM reports WHERE report_type='found' AND status='awaiting_intake'").fetchone()["n"]
        available = conn.execute("SELECT COUNT(*) AS n FROM reports WHERE report_type='found' AND status='available'").fetchone()["n"]
        claims = conn.execute("SELECT COUNT(*) AS n FROM claims WHERE status IN ('pending','disputed','needs_more_evidence')").fetchone()["n"]
        disputed = conn.execute("SELECT COUNT(*) AS n FROM claims WHERE status='disputed'").fetchone()["n"]
        approved_handover = conn.execute("SELECT COUNT(*) AS n FROM claims WHERE status='approved_for_collection'").fetchone()["n"]
        returned = conn.execute("SELECT COUNT(*) AS n FROM handovers").fetchone()["n"]
        points_awarded = conn.execute("SELECT COALESCE(SUM(points),0) AS n FROM reward_ledger").fetchone()["n"]
    return {"awaiting_intake": intake, "available_items": available, "active_claims": claims,
            "disputed_claims": disputed, "approved_handover": approved_handover,
            "returned_items": returned, "total_activity_points": points_awarded}
