"""Idempotent contribution rewards and milestone certificate PDFs."""
from __future__ import annotations
import secrets, sqlite3, uuid
from datetime import datetime
from typing import Any
from app.core.database import audit, now_iso
from app.services.notifications import notify_user

POINT_RULES = {
    "verified_intake": 10,
    "verified_return": 5,
}
CERTIFICATE_MILESTONES = [
    {"tier": "Verified Finder", "threshold": 20, "key": "verified-finder"},
    {"tier": "Campus Helper", "threshold": 50, "key": "campus-helper"},
    {"tier": "Community Champion", "threshold": 100, "key": "community-champion"},
]

def points_total(conn: sqlite3.Connection, user_id: int) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(points), 0) AS total FROM reward_ledger WHERE user_id=?",
        (user_id,),
    ).fetchone()
    return int(row["total"] if row else 0)


def issue_milestone_certificates(conn: sqlite3.Connection, user_id: int) -> list[dict[str, Any]]:
    total = points_total(conn, user_id)
    user = conn.execute("SELECT display_name FROM users WHERE id=?", (user_id,)).fetchone()
    if not user:
        return []
    issued: list[dict[str, Any]] = []
    for milestone in CERTIFICATE_MILESTONES:
        if total < milestone["threshold"]:
            continue
        certificate_id = uuid.uuid4().hex
        serial = "LL-CERT-" + datetime.now().strftime("%Y") + "-" + secrets.token_hex(4).upper()
        timestamp = now_iso()
        cursor = conn.execute(
            """INSERT OR IGNORE INTO certificates
               (id, user_id, tier, threshold_points, points_at_issue, serial, issued_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (certificate_id, user_id, milestone["tier"], milestone["threshold"], total, serial, timestamp),
        )
        if cursor.rowcount:
            issued.append({"id": certificate_id, "tier": milestone["tier"], "serial": serial})
            notify_user(
                conn, user_id, "certificate:" + milestone["key"],
                "Recognition certificate earned",
                "You reached the " + milestone["tier"] + " milestone. Your LostLink certificate is ready in Activity & Certificates.",
                "certificate", certificate_id,
            )
    return issued


def award_points(
    conn: sqlite3.Connection,
    user_id: int,
    points: int,
    event_key: str,
    reason: str,
    report_id: str,
    actor_id: int,
) -> bool:
    """Award exactly once for an auditable, office-confirmed event."""
    recipient = conn.execute("SELECT role FROM users WHERE id=?", (user_id,)).fetchone()
    if not recipient or recipient["role"] != "student" or points <= 0:
        return False
    cursor = conn.execute(
        """INSERT OR IGNORE INTO reward_ledger
           (id, user_id, event_key, points, reason, report_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (uuid.uuid4().hex, user_id, event_key, points, reason, report_id, now_iso()),
    )
    if not cursor.rowcount:
        return False
    audit(conn, actor_id, "reward_points_awarded", "report", report_id,
          {"recipient_id": user_id, "points": points, "reason": reason, "event_key": event_key})
    notify_user(
        conn, user_id, "points:" + event_key,
        "You earned " + str(points) + " activity points",
        reason + ". Your verified contribution balance is now " + str(points_total(conn, user_id)) + " points.",
        "report", report_id,
    )
    issue_milestone_certificates(conn, user_id)
    return True

def certificate_pdf(display_name: str, tier: str, points_at_issue: int, serial: str, issued_at: str) -> bytes:
    from io import BytesIO
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfgen import canvas

    buffer = BytesIO()
    width, height = landscape(A4)
    pdf = canvas.Canvas(buffer, pagesize=(width, height))
    pdf.setTitle("LostLink Recognition Certificate - " + tier)
    pdf.setAuthor("LostLink")
    pdf.setFillColor(colors.HexColor("#f6f7f2"))
    pdf.rect(0, 0, width, height, fill=1, stroke=0)
    pdf.setStrokeColor(colors.HexColor("#176c57"))
    pdf.setLineWidth(3)
    pdf.roundRect(24, 24, width - 48, height - 48, 20, stroke=1, fill=0)
    pdf.setStrokeColor(colors.HexColor("#cfddcf"))
    pdf.setLineWidth(1)
    pdf.roundRect(34, 34, width - 68, height - 68, 15, stroke=1, fill=0)
    pdf.setFillColor(colors.HexColor("#16322f"))
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawCentredString(width / 2, height - 83, "LOSTLINK  /  CAMPUS CONTRIBUTION")
    pdf.setFillColor(colors.HexColor("#136d60"))
    pdf.setFont("Helvetica-Bold", 31)
    pdf.drawCentredString(width / 2, height - 145, "Certificate of Recognition")
    pdf.setFillColor(colors.HexColor("#536961"))
    pdf.setFont("Helvetica", 13)
    pdf.drawCentredString(width / 2, height - 186, "This certificate recognises the verified campus contribution of")
    pdf.setFillColor(colors.HexColor("#16322f"))
    pdf.setFont("Helvetica-Bold", 26)
    pdf.drawCentredString(width / 2, height - 230, display_name[:90])
    pdf.setFillColor(colors.HexColor("#136d60"))
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawCentredString(width / 2, height - 270, tier)
    pdf.setFillColor(colors.HexColor("#536961"))
    pdf.setFont("Helvetica", 12)
    pdf.drawCentredString(width / 2, height - 300, "For supporting campus lost-property recovery through verified contributions.")
    pdf.drawCentredString(width / 2, height - 323, str(points_at_issue) + " activity points at the time of issue")
    pdf.setStrokeColor(colors.HexColor("#d7e1d6"))
    pdf.line(110, 90, width - 110, 90)
    pdf.setFillColor(colors.HexColor("#64766d"))
    pdf.setFont("Helvetica", 9)
    pdf.drawString(62, 66, "Certificate ID: " + serial)
    pdf.drawRightString(width - 62, 66, "Issued: " + issued_at[:10])
    pdf.setFont("Helvetica-Oblique", 8)
    pdf.drawCentredString(width / 2, 48, "Prototype recognition certificate; not an official CVR College credential.")
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
