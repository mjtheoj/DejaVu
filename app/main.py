from __future__ import annotations

import hashlib
import json
import math
import os
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError
from starlette.middleware.sessions import SessionMiddleware

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(ROOT / "data"))).resolve()
DB_PATH = Path(os.getenv("DATABASE_PATH", str(DATA_DIR / "lostlink.db"))).resolve()
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(DATA_DIR / "uploads"))).resolve()
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"
SESSION_SECRET = os.getenv("SESSION_SECRET", "local-development-only-change-this")
HTTPS_ONLY = os.getenv("SESSION_HTTPS_ONLY", "false").lower() == "true"
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_EVIDENCE_TYPES = {
    "distinctive_features", "purchase_or_receipt", "packaging_or_accessory",
    "timeline_and_location", "device_or_account_context", "other"
}


def perceptual_image_hash(image: Image.Image) -> str:
    """Low-frequency image fingerprint: tolerant of re-encoding and light watermarks."""
    gray = image.convert("L").resize((32, 32))
    pixels = list(gray.getdata())
    cosines = [[math.cos((2 * x + 1) * u * math.pi / 64) for x in range(32)] for u in range(8)]
    coefficients = []
    for v in range(8):
        for u in range(8):
            total = 0.0
            for y in range(32):
                row_offset = y * 32
                cy = cosines[v][y]
                for x in range(32):
                    total += pixels[row_offset + x] * cosines[u][x] * cy
            coefficients.append(total)
    values = coefficients[1:]
    median = sorted(values)[len(values) // 2]
    bits = "".join("1" if value > median else "0" for value in coefficients)
    return f"{int(bits, 2):016x}"


def perceptual_hash_from_bytes(raw: bytes) -> str:
    with Image.open(BytesIO(raw)) as source:
        safe = ImageOps.exif_transpose(source).convert("RGB")
        safe.thumbnail((1800, 1800))
        return perceptual_image_hash(safe)


def canonicalise_image(raw: bytes) -> tuple[bytes, str, str]:
    """Validate, normalize orientation/size, strip metadata, and fingerprint an image."""
    Image.MAX_IMAGE_PIXELS = 24_000_000
    try:
        with Image.open(BytesIO(raw)) as check:
            if check.format not in {"JPEG", "PNG", "WEBP"}:
                raise HTTPException(status_code=415, detail="Use a JPG, PNG or WebP image.")
            check.verify()
        with Image.open(BytesIO(raw)) as source:
            safe = ImageOps.exif_transpose(source).convert("RGB")
            safe.thumbnail((1800, 1800))
            phash = perceptual_image_hash(safe)
            output = BytesIO()
            safe.save(output, format="JPEG", quality=88, optimize=True)
            normalized = output.getvalue()
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(status_code=415, detail="The file is not a valid supported image.")
    return normalized, hashlib.sha256(normalized).hexdigest(), phash


def image_fingerprint_matches(conn: sqlite3.Connection, image_sha256: str, image_phash: str) -> bool:
    """Check exact hashes and visually near-identical photos across reports and claim evidence."""
    existing = conn.execute(
        """SELECT image_sha256, image_phash FROM reports WHERE image_path IS NOT NULL
           UNION ALL
           SELECT image_sha256, image_phash FROM claim_evidence_images"""
    ).fetchall()
    candidate = int(image_phash, 16)
    for row in existing:
        if row["image_sha256"] and secrets.compare_digest(str(row["image_sha256"]), image_sha256):
            return True
        if row["image_phash"]:
            try:
                if (candidate ^ int(row["image_phash"], 16)).bit_count() <= 4:
                    return True
            except (TypeError, ValueError):
                continue
    return False


def watermark_image(path: Path, label: str) -> bytes:
    """Serve labelled previews to discourage saving/reusing photos as claim evidence."""
    with Image.open(path) as source:
        image = source.convert("RGB")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    text = "LostLink - " + label
    bounds = draw.textbbox((0, 0), text, font=font)
    bar_height = max(30, bounds[3] - bounds[1] + 14)
    top = max(0, image.height - bar_height)
    draw.rectangle((0, top, image.width, image.height), fill=(18, 44, 42))
    draw.text((12, top + 6), text, font=font, fill=(255, 255, 255))
    output = BytesIO()
    image.save(output, format="JPEG", quality=88, optimize=True)
    return output.getvalue()


DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

CATEGORY_LABELS = {
    "stationery": "Stationery & books",
    "clothing": "Clothing & everyday items",
    "bags_wallets": "Bags & wallets",
    "accessories": "Personal accessories",
    "electronics": "Electronics",
    "identity_documents": "Identity documents & cards",
    "keys_access": "Keys & access cards",
    "cash_jewellery": "Cash & jewellery",
    "sports_instruments": "Sports equipment & instruments",
    "other": "Other",
}
CATEGORY_DEFAULT_LEVEL = {
    "stationery": 1,
    "clothing": 1,
    "bags_wallets": 2,
    "accessories": 2,
    "electronics": 3,
    "identity_documents": 4,
    "keys_access": 4,
    "cash_jewellery": 3,
    "sports_instruments": 2,
    "other": 3,
}
SENSITIVE_CATEGORIES = {"identity_documents", "keys_access"}
ACTIVE_CLAIM_STATES = {"pending", "disputed", "needs_more_evidence"}

app = FastAPI(title="LostLink", version="0.1.0")
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    same_site="strict",
    https_only=HTTPS_ONLY,
    max_age=60 * 60 * 8,
)
app.mount("/static", StaticFiles(directory=str(ROOT / "app" / "static")), name="static")


@contextmanager
def connect_db():
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def hash_password(password: str, salt_hex: str | None = None) -> str:
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 180_000)
    return salt.hex() + "$" + digest.hex()


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, expected = stored.split("$", 1)
        actual = hash_password(password, salt_hex).split("$", 1)[1]
        return secrets.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def audit(conn: sqlite3.Connection, actor_id: int, action: str,
          entity_type: str, entity_id: str, details: dict[str, Any] | None = None) -> None:
    conn.execute(
        """INSERT INTO audit_events(actor_id, action, entity_type, entity_id, details_json, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (actor_id, action, entity_type, entity_id, json.dumps(details or {}), now_iso()),
    )


def initialise_db() -> None:
    with connect_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('student', 'office')),
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reports (
                id TEXT PRIMARY KEY,
                public_ref TEXT NOT NULL UNIQUE,
                report_type TEXT NOT NULL CHECK(report_type IN ('lost', 'found')),
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                brand TEXT,
                primary_color TEXT,
                visible_features TEXT,
                category TEXT NOT NULL,
                occurred_at TEXT,
                location_block TEXT,
                location_floor TEXT,
                location_room TEXT,
                location_area TEXT,
                image_path TEXT,
                image_sha256 TEXT,
                image_phash TEXT,
                status TEXT NOT NULL,
                closure_reason TEXT,
                closure_note TEXT,
                created_by INTEGER NOT NULL REFERENCES users(id),
                tag_id TEXT UNIQUE,
                storage_location TEXT,
                private_detail TEXT,
                value_band TEXT NOT NULL DEFAULT 'unknown',
                sensitivity_level INTEGER NOT NULL DEFAULT 1,
                verification_level INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS claims (
                id TEXT PRIMARY KEY,
                report_id TEXT NOT NULL REFERENCES reports(id),
                lost_report_id TEXT REFERENCES reports(id),
                claimant_id INTEGER NOT NULL REFERENCES users(id),
                evidence TEXT NOT NULL,
                evidence_types TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL,
                appeal_note TEXT,
                appeal_count INTEGER NOT NULL DEFAULT 0,
                reviewer_id INTEGER REFERENCES users(id),
                reviewer_note TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_id INTEGER NOT NULL REFERENCES users(id),
                action TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                details_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS notifications (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                event_key TEXT NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                entity_type TEXT,
                entity_id TEXT,
                read_at TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, event_key)
            );
            CREATE TABLE IF NOT EXISTS reward_ledger (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                event_key TEXT NOT NULL,
                points INTEGER NOT NULL CHECK(points > 0),
                reason TEXT NOT NULL,
                report_id TEXT REFERENCES reports(id),
                created_at TEXT NOT NULL,
                UNIQUE(user_id, event_key)
            );
            CREATE TABLE IF NOT EXISTS certificates (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                tier TEXT NOT NULL,
                threshold_points INTEGER NOT NULL,
                points_at_issue INTEGER NOT NULL,
                serial TEXT NOT NULL UNIQUE,
                issued_at TEXT NOT NULL,
                UNIQUE(user_id, tier)
            );
            CREATE TABLE IF NOT EXISTS handovers (
                id TEXT PRIMARY KEY,
                claim_id TEXT NOT NULL UNIQUE REFERENCES claims(id),
                report_id TEXT NOT NULL UNIQUE REFERENCES reports(id),
                tag_id TEXT NOT NULL,
                claimant_id INTEGER NOT NULL REFERENCES users(id),
                office_user_id INTEGER NOT NULL REFERENCES users(id),
                handover_note TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS claim_verifications (
                claim_id TEXT PRIMARY KEY REFERENCES claims(id),
                verifier_user_id INTEGER NOT NULL REFERENCES users(id),
                checks_json TEXT NOT NULL,
                verified_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS claim_evidence_images (
                id TEXT PRIMARY KEY,
                claim_id TEXT NOT NULL UNIQUE REFERENCES claims(id) ON DELETE CASCADE,
                uploader_id INTEGER NOT NULL REFERENCES users(id),
                image_path TEXT NOT NULL,
                image_sha256 TEXT NOT NULL,
                image_phash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_notifications_user_created ON notifications(user_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_reward_ledger_user_created ON reward_ledger(user_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_reports_status_type ON reports(status, report_type);
            CREATE INDEX IF NOT EXISTS idx_reports_category ON reports(category);
            CREATE INDEX IF NOT EXISTS idx_claims_report ON claims(report_id, status);
            CREATE INDEX IF NOT EXISTS idx_claims_claimant ON claims(claimant_id, created_at);
            """
        )
        # Keep existing local databases compatible as storage tracking is introduced.
        report_columns = {row["name"] for row in conn.execute("PRAGMA table_info(reports)").fetchall()}
        if "storage_location" not in report_columns:
            conn.execute("ALTER TABLE reports ADD COLUMN storage_location TEXT")
        conn.execute(
            "UPDATE reports SET storage_location=? WHERE tag_id IS NOT NULL AND (storage_location IS NULL OR TRIM(storage_location)='')",
            ("Location needs confirmation",),
        )
        # Backward-compatible migrations for richer item details and report closure.
        report_columns = {row["name"] for row in conn.execute("PRAGMA table_info(reports)").fetchall()}
        for column, declaration in (
            ("brand", "TEXT"),
            ("primary_color", "TEXT"),
            ("visible_features", "TEXT"),
            ("closure_reason", "TEXT"),
            ("closure_note", "TEXT"),
            ("image_sha256", "TEXT"),
            ("image_phash", "TEXT"),
        ):
            if column not in report_columns:
                conn.execute(f"ALTER TABLE reports ADD COLUMN {column} {declaration}")
        for image_row in conn.execute(
            "SELECT id, image_path, image_sha256, image_phash FROM reports WHERE image_path IS NOT NULL"
        ).fetchall():
            image_path = (UPLOAD_DIR / image_row["image_path"]).resolve()
            if image_path.parent != UPLOAD_DIR.resolve() or not image_path.is_file():
                continue
            if image_row["image_sha256"] and image_row["image_phash"]:
                continue
            try:
                image_bytes = image_path.read_bytes()
                image_digest = image_row["image_sha256"] or hashlib.sha256(image_bytes).hexdigest()
                image_phash = image_row["image_phash"] or perceptual_hash_from_bytes(image_bytes)
                conn.execute(
                    "UPDATE reports SET image_sha256=?, image_phash=? WHERE id=?",
                    (image_digest, image_phash, image_row["id"]),
                )
            except (OSError, UnidentifiedImageError, ValueError):
                continue
        claim_columns = {row["name"] for row in conn.execute("PRAGMA table_info(claims)").fetchall()}
        for column, declaration in (
            ("appeal_note", "TEXT"),
            ("appeal_count", "INTEGER NOT NULL DEFAULT 0"),
            ("lost_report_id", "TEXT REFERENCES reports(id)"),
            ("evidence_types", "TEXT NOT NULL DEFAULT '[]'"),
        ):
            if column not in claim_columns:
                conn.execute(f"ALTER TABLE claims ADD COLUMN {column} {declaration}")
        if not DEMO_MODE:
            return

        conn.execute(
            """INSERT OR IGNORE INTO users(email, display_name, role, password_hash, created_at)
               VALUES (?, ?, 'student', ?, ?)""",
            ("student@lostlink.local", "Demo Student", hash_password("student123"), now_iso()),
        )
        conn.execute(
            """INSERT OR IGNORE INTO users(email, display_name, role, password_hash, created_at)
               VALUES (?, ?, 'office', ?, ?)""",
            ("office@lostlink.local", "Campus Office", hash_password("office123"), now_iso()),
        )
        for email, display_name, password in (
            ("student2@lostlink.local", "Aarav Mehta", "student2123"),
            ("student3@lostlink.local", "Riya Sharma", "student3123"),
            ("student4@lostlink.local", "Kabir Rao", "student4123"),
        ):
            conn.execute(
                """INSERT OR IGNORE INTO users(email, display_name, role, password_hash, created_at)
                   VALUES (?, ?, 'student', ?, ?)""",
                (email, display_name, hash_password(password), now_iso()),
            )
        student_id = conn.execute("SELECT id FROM users WHERE email=?", ("student@lostlink.local",)).fetchone()["id"]
        office_id = conn.execute("SELECT id FROM users WHERE email=?", ("office@lostlink.local",)).fetchone()["id"]
        if conn.execute("SELECT COUNT(*) AS n FROM reports").fetchone()["n"] > 0:
            return

        today = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
        examples = [
            {
                "public_ref": "LL-P7K4Q2", "report_type": "found", "title": "Navy backpack",
                "description": "Dark blue backpack with two front pockets and a silver zipper pull.",
                "category": "bags_wallets", "days": 1, "block": "Block A", "floor": "1",
                "room": "A-101", "area": "Library entrance", "status": "available",
                "creator": office_id, "tag": "LL-CVR-" + str(today.year) + "-000001",
                "private": "Small silver zipper pull on the front pocket and a tiny stitched mark inside the left strap.",
                "value": "medium", "sensitivity": 1, "level": 2,
            },
            {
                "public_ref": "LL-M3T8H1", "report_type": "found", "title": "Steel water bottle",
                "description": "Silver insulated bottle with a black cap and a small scratch near the base.",
                "category": "accessories", "days": 2, "block": "Block B", "floor": "Ground",
                "room": "", "area": "Cafeteria", "status": "available",
                "creator": office_id, "tag": "LL-CVR-" + str(today.year) + "-000002",
                "private": "Small dent on the underside of the base.",
                "value": "low", "sensitivity": 1, "level": 2,
            },
            {
                "public_ref": "LL-R5N2D9", "report_type": "found", "title": "Wireless earbuds case",
                "description": "Black wireless earbud charging case found near the library study area.",
                "category": "accessories", "days": 1, "block": "Block A", "floor": "1",
                "room": "", "area": "Library study area", "status": "available",
                "creator": office_id, "tag": "LL-CVR-" + str(today.year) + "-000003",
                "private": "A tiny white sticker is placed on the back edge of the case.",
                "value": "medium", "sensitivity": 1, "level": 2,
            },
            {
                "public_ref": "LL-C9W4B6", "report_type": "found", "title": "Scientific calculator",
                "description": "Dark scientific calculator in a plain black protective cover.",
                "category": "electronics", "days": 3, "block": "Block C", "floor": "2",
                "room": "C-204", "area": "Classroom corridor", "status": "available",
                "creator": office_id, "tag": "LL-CVR-" + str(today.year) + "-000004",
                "private": "The cover has a small blue fabric tab near the zip.",
                "value": "medium", "sensitivity": 1, "level": 3,
            },
            {
                "public_ref": "LL-U2F6J8", "report_type": "found", "title": "Student identity card",
                "description": "A student identity card was handed to the campus office.",
                "category": "identity_documents", "days": 1, "block": "Block A", "floor": "Ground",
                "room": "", "area": "Reception", "status": "available",
                "creator": office_id, "tag": "LL-CVR-" + str(today.year) + "-000005",
                "private": "Verify against the authorised campus record; do not disclose the card number.",
                "value": "unknown", "sensitivity": 4, "level": 4,
            },
            {
                "public_ref": "LL-H6P1S3", "report_type": "found", "title": "Grey umbrella",
                "description": "Compact grey folding umbrella with a curved handle.",
                "category": "clothing", "days": 0, "block": "Block B", "floor": "Ground",
                "room": "", "area": "Cafeteria entrance", "status": "awaiting_intake",
                "creator": student_id, "tag": None, "private": None,
                "value": "unknown", "sensitivity": 1, "level": None,
            },
        ]
        for item in examples:
            occurred = (today - timedelta(days=item["days"])).isoformat(timespec="minutes")
            conn.execute(
                """INSERT INTO reports(id, public_ref, report_type, title, description, category,
                   occurred_at, location_block, location_floor, location_room, location_area,
                   status, created_by, tag_id, private_detail, value_band, sensitivity_level,
                   verification_level, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    uuid.uuid4().hex, item["public_ref"], item["report_type"], item["title"],
                    item["description"], item["category"], occurred, item["block"], item["floor"],
                    item["room"], item["area"], item["status"], item["creator"], item["tag"],
                    item["private"], item["value"], item["sensitivity"], item["level"], now_iso(), now_iso()
                ),
            )
        conn.execute(
            "UPDATE reports SET storage_location=? WHERE tag_id IS NOT NULL AND (storage_location IS NULL OR TRIM(storage_location)='')",
            ("Demo storage · shelf A-01",),
        )
        conn.execute(
            """INSERT INTO reports(id, public_ref, report_type, title, description, category,
               occurred_at, location_block, location_floor, location_room, location_area,
               status, created_by, created_at, updated_at)
               VALUES (?, ?, 'lost', ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?)""",
            (
                "demo-lost-backpack", "LL-MY-1024", "Dark blue backpack",
                "I lost a dark blue backpack with two front pockets around the library.",
                "bags_wallets", (today - timedelta(days=1)).isoformat(timespec="minutes"),
                "Block A", "1", "", "Library", student_id, now_iso(), now_iso()
            ),
        )


initialise_db()



POINT_RULES = {
    "verified_intake": 10,
    "verified_return": 5,
}
CERTIFICATE_MILESTONES = [
    {"tier": "Verified Finder", "threshold": 20, "key": "verified-finder"},
    {"tier": "Campus Helper", "threshold": 50, "key": "campus-helper"},
    {"tier": "Community Champion", "threshold": 100, "key": "community-champion"},
]


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


class LoginBody(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class ReportBody(BaseModel):
    report_type: Literal["lost", "found"]
    title: str = Field(min_length=4, max_length=100)
    description: str = Field(min_length=10, max_length=1200)
    category: str
    # Optional public characteristics improve search/matching; never put secret proof here.
    brand: str | None = Field(default=None, max_length=80)
    primary_color: str | None = Field(default=None, max_length=60)
    visible_features: str | None = Field(default=None, max_length=400)
    occurred_at: str | None = None
    location_block: str | None = Field(default=None, max_length=80)
    location_floor: str | None = Field(default=None, max_length=40)
    location_room: str | None = Field(default=None, max_length=80)
    location_area: str | None = Field(default=None, max_length=120)


class ReportCloseBody(BaseModel):
    reason: Literal["recovered_elsewhere", "no_longer_searching", "duplicate", "found_report_withdrawn"]
    note: str | None = Field(default=None, max_length=400)


class ClaimDisputeBody(BaseModel):
    reason: str = Field(min_length=20, max_length=1000)


class IntakeBody(BaseModel):
    confirmed_physical_receipt: bool
    storage_location: str = Field(min_length=4, max_length=160)
    private_detail: str | None = Field(default=None, max_length=1200)
    value_band: Literal["low", "medium", "high", "unknown"] = "unknown"
    sensitivity_level: int = Field(default=1, ge=1, le=4)


class StorageLocationBody(BaseModel):
    storage_location: str = Field(min_length=4, max_length=160)
    note: str | None = Field(default=None, max_length=800)


class ClaimBody(BaseModel):
    report_id: str
    evidence: str = Field(min_length=20, max_length=1800)
    lost_report_id: str | None = None
    evidence_types: list[str] = Field(min_length=1, max_length=6)


class ClaimEvidenceBody(BaseModel):
    evidence: str = Field(min_length=20, max_length=1800)


class ClaimDecisionBody(BaseModel):
    action: Literal["approve", "reject", "request_more_evidence", "mark_disputed"]
    note: str | None = Field(default=None, max_length=800)
    verification_checks: list[str] = Field(default_factory=list)


class HandoverBody(BaseModel):
    confirmed_physical_handover: bool
    claimant_identity_checked: bool
    tag_id: str = Field(min_length=4, max_length=80)
    note: str | None = Field(default=None, max_length=800)


@app.get("/")
def home():
    return FileResponse(ROOT / "app" / "static" / "index.html")


@app.get("/api/config")
def public_config():
    return {
        "demo_mode": DEMO_MODE,
        "points": POINT_RULES,
        "certificate_milestones": [{"tier": m["tier"], "threshold": m["threshold"]} for m in CERTIFICATE_MILESTONES],
        "categories": [{"value": key, "label": value} for key, value in CATEGORY_LABELS.items()],
        "locations": {
            "blocks": ["Block A", "Block B", "Block C", "Library", "Cafeteria", "Other / not sure"],
            "floors": ["Ground", "1", "2", "3", "Other / not sure"],
            "note": "Sample directory for the prototype. Replace with the verified campus directory before deployment."
        },
    }


@app.post("/api/login")
def login(body: LoginBody, request: Request):
    with connect_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE email=?", (body.email.strip().lower(),)).fetchone()
    if not row or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    request.session.clear()
    request.session["user_id"] = row["id"]
    return {"user": user_payload(row)}


@app.post("/api/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@app.get("/api/me")
async def me(user: dict[str, Any] = Depends(authenticated_user)):
    return {"user": user}


@app.get("/api/reports")
async def list_reports(
    report_type: str | None = None,
    category: str | None = None,
    block: str | None = None,
    room: str | None = None,
    q: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    status: str | None = None,
    mine: bool = False,
    user: dict[str, Any] = Depends(authenticated_user),
):
    conditions: list[str] = []
    params: list[Any] = []
    internal = user["role"] == "office"

    if not internal and mine:
        conditions.append("r.created_by=?")
        params.append(user["id"])
    elif not internal:
        conditions.extend(["r.report_type='found'", "r.status='available'"])
    elif mine:
        conditions.append("r.created_by=?")
        params.append(user["id"])

    if report_type in {"lost", "found"}:
        conditions.append("r.report_type=?")
        params.append(report_type)
    if category in CATEGORY_LABELS:
        conditions.append("r.category=?")
        params.append(category)
    if block:
        conditions.append("LOWER(COALESCE(r.location_block,'')) LIKE ?")
        params.append("%" + block.lower() + "%")
    if room:
        conditions.append("LOWER(COALESCE(r.location_room,'')) LIKE ?")
        params.append("%" + room.lower() + "%")
    if q:
        term = "%" + q.strip().lower() + "%"
        conditions.append("""(
            LOWER(r.title) LIKE ? OR LOWER(r.description) LIKE ? OR LOWER(r.public_ref) LIKE ?
            OR LOWER(COALESCE(r.location_area,'')) LIKE ? OR LOWER(COALESCE(r.brand,'')) LIKE ?
            OR LOWER(COALESCE(r.primary_color,'')) LIKE ? OR LOWER(COALESCE(r.visible_features,'')) LIKE ?
            OR LOWER(COALESCE(r.location_block,'')) LIKE ? OR LOWER(COALESCE(r.location_floor,'')) LIKE ?
            OR LOWER(COALESCE(r.location_room,'')) LIKE ?
        )""")
        params.extend([term] * 10)
    if date_from:
        conditions.append("COALESCE(r.occurred_at,'') >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("COALESCE(r.occurred_at,'') <= ?")
        params.append(date_to + "T23:59:59")
    if internal and status:
        conditions.append("r.status=?")
        params.append(status)

    sql = "SELECT r.* FROM reports r"
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY r.created_at DESC LIMIT 250"
    with connect_db() as conn:
        rows = conn.execute(sql, params).fetchall()
        reports = []
        for row in rows:
            report_data = serialise_report(row, internal=internal)
            if row["report_type"] == "lost" and int(row["created_by"]) == int(user["id"]):
                active_claim = conn.execute(
                    """SELECT 1 FROM claims WHERE lost_report_id=?
                       AND status IN ('pending','disputed','needs_more_evidence','approved_for_collection') LIMIT 1""",
                    (row["id"],),
                ).fetchone()
                report_data["has_active_linked_claim"] = active_claim is not None
            reports.append(report_data)
    return {"reports": reports}


@app.post("/api/reports")
async def create_report(body: ReportBody, user: dict[str, Any] = Depends(authenticated_user)):
    if len(body.title.strip()) < 4:
        raise HTTPException(status_code=422, detail="Enter an item name of at least 4 characters.")
    if len(body.description.strip()) < 10:
        raise HTTPException(status_code=422, detail="Add at least 10 characters describing the item.")
    if body.occurred_at:
        try:
            datetime.fromisoformat(body.occurred_at.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=422, detail="Use a valid ISO date and time, or leave the date blank if unknown.")
    if body.category not in CATEGORY_LABELS:
        raise HTTPException(status_code=422, detail="Choose a valid item category.")
    if not (body.location_block or body.location_area):
        raise HTTPException(status_code=422, detail="Choose a campus block or area.")
    report_id = uuid.uuid4().hex
    public_ref = new_public_ref()
    timestamp = now_iso()
    status = "open" if body.report_type == "lost" else "awaiting_intake"
    with connect_db() as conn:
        conn.execute(
            """INSERT INTO reports(id, public_ref, report_type, title, description, brand, primary_color,
               visible_features, category, occurred_at, location_block, location_floor, location_room,
               location_area, status, created_by, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (report_id, public_ref, body.report_type, body.title.strip(), body.description.strip(),
             (body.brand or "").strip() or None, (body.primary_color or "").strip() or None,
             (body.visible_features or "").strip() or None, body.category, body.occurred_at,
             body.location_block, body.location_floor, body.location_room, body.location_area,
             status, user["id"], timestamp, timestamp),
        )
        audit(conn, user["id"], "report_created", "report", report_id, {"report_type": body.report_type})
        if body.report_type == "found":
            notify_role(conn, "office", "found-report:" + report_id, "Found-item report awaiting intake",
                        "A new found-item report is waiting for physical office intake.", "report", report_id)
            notify_user(conn, user["id"], "report-created:" + report_id, "Found report submitted",
                        "Your found-item report is waiting for the office to confirm physical receipt.", "report", report_id)
        else:
            notify_user(conn, user["id"], "report-created:" + report_id, "Lost report submitted",
                        "Your lost-item report is saved. LostLink can suggest possible matches as found items are received.", "report", report_id)
            notify_matches_for_lost_report(conn, read_report(conn, report_id))
        row = read_report(conn, report_id)
    return {"report": serialise_report(row, internal=user["role"] == "office"),
            "message": "Lost report submitted." if body.report_type == "lost" else "Found-item report submitted for office intake. It will become searchable after staff confirm receipt."}


@app.post("/api/reports/{report_id}/close")
async def close_report(
    report_id: str,
    body: ReportCloseBody,
    user: dict[str, Any] = Depends(authenticated_user),
):
    if user["role"] != "student":
        raise HTTPException(status_code=403, detail="Only the report owner can close their report.")
    with connect_db() as conn:
        report = read_report(conn, report_id)
        if report["created_by"] != user["id"]:
            raise HTTPException(status_code=404, detail="Report not found.")
        if report["report_type"] == "lost" and report["status"] == "open":
            linked_active_claim = conn.execute(
                """SELECT 1 FROM claims WHERE lost_report_id=?
                   AND status IN ('pending','disputed','needs_more_evidence','approved_for_collection') LIMIT 1""",
                (report_id,),
            ).fetchone()
            if linked_active_claim:
                raise HTTPException(
                    status_code=409,
                    detail="This lost report is linked to a claim under review. Resolve that claim before closing the report."
                )
            if body.reason == "found_report_withdrawn":
                raise HTTPException(status_code=422, detail="Choose a reason for closing your lost-item search.")
            final_status = "closed"
            title = "Lost report closed"
            message = "Your lost report has been closed. It will no longer generate match suggestions, and its history remains visible in My Reports."
        elif report["report_type"] == "found" and report["status"] == "awaiting_intake":
            if body.reason != "found_report_withdrawn":
                raise HTTPException(status_code=422, detail="A found report can only be withdrawn before office intake.")
            final_status = "cancelled"
            title = "Found report withdrawn"
            message = "Your found report was withdrawn before the campus office accepted physical custody."
        else:
            raise HTTPException(status_code=409, detail="Only an open lost report or a found report awaiting office intake can be closed.")
        timestamp = now_iso()
        conn.execute(
            "UPDATE reports SET status=?, closure_reason=?, closure_note=?, updated_at=? WHERE id=?",
            (final_status, body.reason, (body.note or "").strip() or None, timestamp, report_id),
        )
        audit(conn, user["id"], "report_closed_or_withdrawn", "report", report_id,
              {"report_type": report["report_type"], "status": final_status,
               "reason": body.reason, "note": (body.note or "").strip() or None})
        notify_user(conn, user["id"], "report-closed:" + report_id, title, message, "report", report_id)
        if report["report_type"] == "found":
            notify_role(conn, "office", "found-report-withdrawn:" + report_id,
                        "Found report withdrawn before intake",
                        "A student withdrew a found-item report before the physical item was accepted into campus custody.",
                        "report", report_id)
        updated = read_report(conn, report_id)
    return {"report": serialise_report(updated), "message": title + "."}


@app.post("/api/reports/{report_id}/image")
async def upload_report_image(
    report_id: str,
    file: UploadFile = File(...),
    user: dict[str, Any] = Depends(authenticated_user),
):
    with connect_db() as conn:
        row = read_report(conn, report_id)
        is_office = user["role"] == "office"
        if not is_office and row["created_by"] != user["id"]:
            raise HTTPException(status_code=403, detail="You cannot update this report.")
        if not is_office and row["report_type"] == "found" and row["status"] != "awaiting_intake":
            raise HTTPException(status_code=409, detail="A found item's photo can only be changed before office intake.")
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Images must be 5 MB or smaller.")
    normalized, image_sha256, image_phash = canonicalise_image(raw)
    filename = uuid.uuid4().hex + ".jpg"
    (UPLOAD_DIR / filename).write_bytes(normalized)
    with connect_db() as conn:
        row = read_report(conn, report_id)
        old = row["image_path"]
        conn.execute(
            "UPDATE reports SET image_path=?, image_sha256=?, image_phash=?, updated_at=? WHERE id=?",
            (filename, image_sha256, image_phash, now_iso(), report_id),
        )
        audit(conn, user["id"], "report_image_added", "report", report_id)
        if old:
            try:
                (UPLOAD_DIR / old).unlink(missing_ok=True)
            except OSError:
                pass
        updated = read_report(conn, report_id)
    return {"report": serialise_report(updated, internal=user["role"] == "office")}


@app.get("/api/reports/{report_id}/image")
async def get_report_image(report_id: str, user: dict[str, Any] = Depends(authenticated_user)):
    with connect_db() as conn:
        row = read_report(conn, report_id)
    if not row["image_path"]:
        raise HTTPException(status_code=404, detail="No image is available.")
    if user["role"] != "office":
        if not report_visible_to_student(row, user):
            raise HTTPException(status_code=404, detail="Image not available.")
        if row["category"] in SENSITIVE_CATEGORIES:
            raise HTTPException(status_code=404, detail="Images of sensitive items are restricted.")
    path = (UPLOAD_DIR / row["image_path"]).resolve()
    if path.parent != UPLOAD_DIR.resolve() or not path.is_file():
        raise HTTPException(status_code=404, detail="Image not found.")
    headers = {
        "Cache-Control": "private, no-store",
        "Content-Disposition": "inline",
        "X-Content-Type-Options": "nosniff",
    }
    if user["role"] != "office":
        return StreamingResponse(BytesIO(watermark_image(path, row["public_ref"])),
                                 media_type="image/jpeg", headers=headers)
    return FileResponse(path, media_type="image/jpeg", headers=headers)


@app.get("/api/reports/{report_id}/matches")
async def get_matches(report_id: str, user: dict[str, Any] = Depends(authenticated_user)):
    from app.matching import matching_engine

    with connect_db() as conn:
        lost = read_report(conn, report_id)
        if lost["report_type"] != "lost":
            raise HTTPException(status_code=400, detail="Matches are generated from a lost-item report.")
        if lost["status"] != "open":
            raise HTTPException(status_code=409, detail="Only an open lost report can be matched.")
        if user["role"] != "office" and lost["created_by"] != user["id"]:
            raise HTTPException(status_code=403, detail="You can only view matches for your own lost reports.")
        candidates = conn.execute(
            "SELECT * FROM reports WHERE report_type='found' AND status='available' ORDER BY created_at DESC LIMIT 500"
        ).fetchall()
    lost_for_matching = dict(lost)
    if lost_for_matching.get("image_path"):
        lost_for_matching["image_path"] = str(UPLOAD_DIR / lost_for_matching["image_path"])
    candidate_data = []
    for candidate in candidates:
        candidate_item = dict(candidate)
        if candidate_item.get("image_path"):
            candidate_item["image_path"] = str(UPLOAD_DIR / candidate_item["image_path"])
        candidate_data.append(candidate_item)
    ranked = matching_engine.rank(lost_for_matching, candidate_data, limit=5)
    internal = user["role"] == "office"
    results = []
    for match in ranked:
        item = serialise_report(next(row for row in candidates if row["id"] == match["report"]["id"]), internal=internal)
        entry = {"report": item, "strength": match["strength"], "reasons": match["reasons"]}
        if internal:
            entry["internal_score"] = match["score"]
            entry["signals"] = match["signals"]
            entry["matching_engine"] = match["engine"]
        results.append(entry)
    return {"matches": results, "note": "Suggestions support discovery only; they do not establish ownership."}


@app.post("/api/reports/{report_id}/intake")
async def intake_found_item(
    report_id: str,
    body: IntakeBody,
    user: dict[str, Any] = Depends(authenticated_user),
):
    require_office(user)
    if not body.confirmed_physical_receipt:
        raise HTTPException(status_code=422, detail="Confirm that the physical item has been received by the office.")
    storage_location = body.storage_location.strip()
    if len(storage_location) < 4:
        raise HTTPException(status_code=422, detail="Record the actual campus room, cabinet, shelf or other storage location.")
    with connect_db() as conn:
        row = read_report(conn, report_id)
        if row["report_type"] != "found" or row["status"] != "awaiting_intake":
            raise HTTPException(status_code=409, detail="Only found-item reports awaiting intake can be accepted.")
        level = effective_level(row["category"], body.value_band, body.sensitivity_level)
        detail_length = len((body.private_detail or "").strip())
        minimum_detail = 8 if level >= 3 else (6 if level >= 2 else 0)
        if detail_length < minimum_detail:
            raise HTTPException(status_code=422, detail="For this risk level, record a private identifying detail or the approved verification method.")
        year = datetime.now().year
        prefix = "LL-CVR-" + str(year) + "-"
        latest = conn.execute("SELECT tag_id FROM reports WHERE tag_id LIKE ? ORDER BY tag_id DESC LIMIT 1", (prefix + "%",)).fetchone()
        number = int(latest["tag_id"].rsplit("-", 1)[1]) + 1 if latest else 1
        tag_id = prefix + str(number).zfill(6)
        conn.execute(
            """UPDATE reports SET status='available', tag_id=?, storage_location=?, private_detail=?, value_band=?,
               sensitivity_level=?, verification_level=?, updated_at=? WHERE id=?""",
            (tag_id, storage_location, (body.private_detail or "").strip() or None, body.value_band,
             body.sensitivity_level, level, now_iso(), report_id),
        )
        audit(conn, user["id"], "found_item_received_tagged_and_stored", "report", report_id,
              {"tag_id": tag_id, "storage_location": storage_location, "verification_level": "L" + str(level)})
        notify_user(
            conn, row["created_by"], "found-intake:" + report_id,
            "Found item received and stored",
            "Campus office confirmed physical receipt and storage of the item. It is now available for matching.",
            "report", report_id,
        )
        reporter = conn.execute("SELECT role FROM users WHERE id=?", (row["created_by"],)).fetchone()
        if reporter and reporter["role"] == "student":
            award_points(
                conn, row["created_by"], POINT_RULES["verified_intake"],
                "verified-intake:" + report_id,
                "Your found-item report was physically received and verified by the campus office",
                report_id, user["id"]
            )
        notify_possible_matches(conn, read_report(conn, report_id))
        updated = read_report(conn, report_id)
    return {"report": serialise_report(updated, internal=True), "message": "Physical receipt recorded, tag assigned and campus storage location saved."}


@app.post("/api/reports/{report_id}/storage")
async def update_storage_location(
    report_id: str,
    body: StorageLocationBody,
    user: dict[str, Any] = Depends(authenticated_user),
):
    require_office(user)
    storage_location = body.storage_location.strip()
    if len(storage_location) < 4:
        raise HTTPException(status_code=422, detail="Record the actual campus room, cabinet, shelf or other storage location.")
    with connect_db() as conn:
        report = read_report(conn, report_id)
        if report["report_type"] != "found" or not report["tag_id"]:
            raise HTTPException(status_code=409, detail="Only physically received and tagged found items can have a storage location.")
        if report["status"] not in {"available", "claim_approved"}:
            raise HTTPException(status_code=409, detail="Storage location can only be changed while the item is in campus custody.")
        previous_location = report["storage_location"]
        conn.execute("UPDATE reports SET storage_location=?, updated_at=? WHERE id=?",
                     (storage_location, now_iso(), report_id))
        audit(conn, user["id"], "storage_location_updated", "report", report_id,
              {"tag_id": report["tag_id"], "previous_location": previous_location,
               "new_location": storage_location, "note": (body.note or "").strip() or None})
        updated = read_report(conn, report_id)
    return {"report": serialise_report(updated, internal=True), "message": "Campus storage location updated."}


@app.post("/api/claims")
async def create_claim(body: ClaimBody, user: dict[str, Any] = Depends(authenticated_user)):
    if user["role"] != "student":
        raise HTTPException(status_code=403, detail="Claims must be submitted from a student account.")
    if any(item not in ALLOWED_EVIDENCE_TYPES for item in body.evidence_types):
        raise HTTPException(status_code=422, detail="Choose valid ownership evidence types.")
    if len(set(body.evidence_types)) != len(body.evidence_types):
        raise HTTPException(status_code=422, detail="Do not select the same evidence type twice.")
    evidence_types = list(body.evidence_types)
    with connect_db() as conn:
        report = read_report(conn, body.report_id)
        if report["report_type"] != "found" or report["status"] != "available":
            raise HTTPException(status_code=409, detail="This item is not accepting claims.")
        linked_lost = None
        if body.lost_report_id:
            linked_lost = read_report(conn, body.lost_report_id)
            if (linked_lost["report_type"] != "lost" or
                    linked_lost["created_by"] != user["id"] or
                    linked_lost["status"] != "open"):
                raise HTTPException(
                    status_code=409,
                    detail="Choose one of your own open lost reports to link this claim, or leave the link blank."
                )
            existing_linked = conn.execute(
                """SELECT id FROM claims WHERE lost_report_id=?
                   AND status IN ('pending','disputed','needs_more_evidence','approved_for_collection')""",
                (body.lost_report_id,),
            ).fetchone()
            if existing_linked:
                raise HTTPException(
                    status_code=409,
                    detail="That lost report is already linked to a claim under review. Resolve it before starting another claim for the same lost report."
                )
        if report["created_by"] == user["id"]:
            raise HTTPException(status_code=400, detail="You cannot claim your own found-item report.")
        existing_own = conn.execute(
            "SELECT id, status FROM claims WHERE report_id=? AND claimant_id=? AND status IN ('pending','disputed','needs_more_evidence','approved_for_collection','rejected')",
            (body.report_id, user["id"])
        ).fetchone()
        if existing_own:
            if existing_own["status"] == "rejected":
                raise HTTPException(
                    status_code=409,
                    detail="Your previous claim was not approved. Use the one-time review request on My Claims instead of submitting another claim."
                )
            raise HTTPException(status_code=409, detail="You already have an active claim for this item.")
        active = conn.execute(
            "SELECT id FROM claims WHERE report_id=? AND status IN ('pending','disputed','needs_more_evidence')",
            (body.report_id,)
        ).fetchall()
        status = "disputed" if active else "pending"
        claim_id = uuid.uuid4().hex
        timestamp = now_iso()
        conn.execute(
            """INSERT INTO claims(id, report_id, lost_report_id, claimant_id, evidence, evidence_types, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (claim_id, body.report_id, body.lost_report_id, user["id"], body.evidence.strip(),
             json.dumps(evidence_types), status, timestamp, timestamp),
        )
        if active:
            conn.execute(
                "UPDATE claims SET status='disputed', updated_at=? WHERE report_id=? AND status IN ('pending','disputed','needs_more_evidence')",
                (timestamp, body.report_id),
            )
        audit(conn, user["id"], "claim_submitted", "claim", claim_id,
              {"report_id": body.report_id, "competing_claims": bool(active)})
        notify_role(conn, "office", "claim-submitted:" + claim_id, "Ownership claim requires review",
                    "A new ownership claim was submitted for item " + report["public_ref"] + ".", "claim", claim_id)
        if active:
            previous = conn.execute(
                "SELECT DISTINCT claimant_id, id FROM claims WHERE report_id=? AND id<>? AND status='disputed'",
                (body.report_id, claim_id)
            ).fetchall()
            for previous_claim in previous:
                notify_user(
                    conn, previous_claim["claimant_id"],
                    "claim-dispute:" + previous_claim["id"] + ":" + claim_id,
                    "A competing claim was submitted",
                    "This item is on hold while authorised office staff review the competing claims.",
                    "claim", previous_claim["id"]
                )
        claim = conn.execute("SELECT * FROM claims WHERE id=?", (claim_id,)).fetchone()
    return {"claim": {"id": claim["id"], "status": claim["status"], "created_at": claim["created_at"],
                      "report": serialise_report(report), "message": "Claim submitted for review."}}



@app.post("/api/claims/{claim_id}/evidence-image")
async def upload_claim_evidence_image(
    claim_id: str,
    file: UploadFile = File(...),
    user: dict[str, Any] = Depends(authenticated_user),
):
    if user["role"] != "student":
        raise HTTPException(status_code=403, detail="Only the claimant can add an ownership-evidence image.")
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Evidence images must be 5 MB or smaller.")
    normalized, image_sha256, image_phash = canonicalise_image(raw)
    with connect_db() as conn:
        claim = conn.execute("SELECT * FROM claims WHERE id=?", (claim_id,)).fetchone()
        if not claim or claim["claimant_id"] != user["id"]:
            raise HTTPException(status_code=404, detail="Claim not found.")
        if claim["status"] not in {"pending", "disputed", "needs_more_evidence"}:
            raise HTTPException(status_code=409, detail="Evidence images can only be added while a claim is under review.")
        if conn.execute("SELECT 1 FROM claim_evidence_images WHERE claim_id=?", (claim_id,)).fetchone():
            raise HTTPException(status_code=409, detail="This claim already has an evidence image attached.")
        if image_fingerprint_matches(conn, image_sha256, image_phash):
            raise HTTPException(
                status_code=409,
                detail="This image duplicates or closely matches an image already in LostLink. Use a different, genuine proof image or explain another owner-only detail in text.",
            )
        filename = "claim-" + uuid.uuid4().hex + ".jpg"
        (UPLOAD_DIR / filename).write_bytes(normalized)
        conn.execute(
            """INSERT INTO claim_evidence_images
               (id, claim_id, uploader_id, image_path, image_sha256, image_phash, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (uuid.uuid4().hex, claim_id, user["id"], filename, image_sha256, image_phash, now_iso()),
        )
        audit(conn, user["id"], "claim_evidence_image_added", "claim", claim_id,
              {"sha256_prefix": image_sha256[:12]})
        notify_role(conn, "office", "claim-evidence-image:" + claim_id,
                    "Claim evidence image submitted", "A claimant attached private image evidence for review.",
                    "claim", claim_id)
    return {"ok": True, "message": "Private evidence image attached."}


@app.get("/api/claims/{claim_id}/evidence-image")
async def get_claim_evidence_image(
    claim_id: str,
    user: dict[str, Any] = Depends(authenticated_user),
):
    with connect_db() as conn:
        claim = conn.execute("SELECT * FROM claims WHERE id=?", (claim_id,)).fetchone()
        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found.")
        if user["role"] != "office" and claim["claimant_id"] != user["id"]:
            raise HTTPException(status_code=404, detail="Evidence image not available.")
        image_row = conn.execute(
            "SELECT image_path FROM claim_evidence_images WHERE claim_id=?", (claim_id,)
        ).fetchone()
    if not image_row:
        raise HTTPException(status_code=404, detail="No evidence image is attached.")
    path = (UPLOAD_DIR / image_row["image_path"]).resolve()
    if path.parent != UPLOAD_DIR.resolve() or not path.is_file():
        raise HTTPException(status_code=404, detail="Evidence image not found.")
    headers = {
        "Cache-Control": "private, no-store",
        "Content-Disposition": "inline",
        "X-Content-Type-Options": "nosniff",
    }
    label = "PRIVATE CLAIM " + claim_id[:8].upper()
    return StreamingResponse(BytesIO(watermark_image(path, label)),
                             media_type="image/jpeg", headers=headers)


@app.get("/api/claims")
async def list_claims(user: dict[str, Any] = Depends(authenticated_user)):
    internal = user["role"] == "office"
    with connect_db() as conn:
        if internal:
            rows = conn.execute(
                """SELECT c.*, u.display_name AS claimant_name, u.email AS claimant_email
                   FROM claims c JOIN users u ON u.id=c.claimant_id
                   ORDER BY CASE c.status WHEN 'disputed' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END, c.created_at"""
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM claims WHERE claimant_id=? ORDER BY created_at DESC", (user["id"],)
            ).fetchall()
        output = []
        for claim in rows:
            report = read_report(conn, claim["report_id"])
            linked_lost_report = None
            if claim["lost_report_id"]:
                linked_row = read_report(conn, claim["lost_report_id"])
                linked_lost_report = {
                    "id": linked_row["id"],
                    "public_ref": linked_row["public_ref"],
                    "title": linked_row["title"],
                    "status": linked_row["status"],
                }
            try:
                evidence_types = json.loads(claim["evidence_types"] or "[]")
            except (TypeError, ValueError):
                evidence_types = []
            evidence_image = conn.execute(
                "SELECT 1 FROM claim_evidence_images WHERE claim_id=?", (claim["id"],)
            ).fetchone()
            entry = {
                "id": claim["id"],
                "status": claim["status"],
                "evidence_types": evidence_types,
                "evidence_image_available": evidence_image is not None,
                "created_at": claim["created_at"],
                "updated_at": claim["updated_at"],
                "appeal_note": claim["appeal_note"],
                "appeal_count": claim["appeal_count"],
                "linked_lost_report": linked_lost_report,
                "report": serialise_report(report, internal=internal),
            }
            if internal:
                entry.update({
                    "evidence": claim["evidence"],
                    "claimant_name": claim["claimant_name"],
                    "claimant_email": claim["claimant_email"],
                    "reviewer_note": claim["reviewer_note"],
                })
            output.append(entry)
    return {"claims": output}


@app.post("/api/claims/{claim_id}/evidence")
async def update_claim_evidence(
    claim_id: str,
    body: ClaimEvidenceBody,
    user: dict[str, Any] = Depends(authenticated_user),
):
    if user["role"] != "student":
        raise HTTPException(status_code=403, detail="This action is available to the claimant.")
    with connect_db() as conn:
        claim = conn.execute("SELECT * FROM claims WHERE id=?", (claim_id,)).fetchone()
        if not claim or claim["claimant_id"] != user["id"]:
            raise HTTPException(status_code=404, detail="Claim not found.")
        if claim["status"] != "needs_more_evidence":
            raise HTTPException(status_code=409, detail="Additional evidence is not currently requested.")
        active_other = conn.execute(
            "SELECT id FROM claims WHERE report_id=? AND id<>? AND status IN ('pending','disputed','needs_more_evidence')",
            (claim["report_id"], claim_id)
        ).fetchall()
        status = "disputed" if active_other else "pending"
        conn.execute("UPDATE claims SET evidence=?, status=?, updated_at=? WHERE id=?",
                     (body.evidence.strip(), status, now_iso(), claim_id))
        if active_other:
            conn.execute(
                "UPDATE claims SET status='disputed', updated_at=? WHERE report_id=? AND status IN ('pending','disputed','needs_more_evidence')",
                (now_iso(), claim["report_id"])
            )
        audit(conn, user["id"], "claim_evidence_updated", "claim", claim_id)
        notify_role(conn, "office", "claim-evidence:" + claim_id + ":" + now_iso()[:16],
                    "Additional claim evidence submitted", "A claimant has added the requested evidence.", "claim", claim_id)
        updated = conn.execute("SELECT * FROM claims WHERE id=?", (claim_id,)).fetchone()
        report = read_report(conn, updated["report_id"])
    return {"claim": {"id": updated["id"], "status": updated["status"],
                      "report": serialise_report(report), "message": "Additional evidence submitted."}}


@app.post("/api/claims/{claim_id}/dispute")
async def dispute_rejected_claim(
    claim_id: str,
    body: ClaimDisputeBody,
    user: dict[str, Any] = Depends(authenticated_user),
):
    if user["role"] != "student":
        raise HTTPException(status_code=403, detail="Only a student claimant can request a review.")
    reason = body.reason.strip()
    if len(reason) < 20:
        raise HTTPException(status_code=422, detail="Explain why the decision should be reviewed (at least 20 characters).")
    with connect_db() as conn:
        claim = conn.execute("SELECT * FROM claims WHERE id=?", (claim_id,)).fetchone()
        if not claim or claim["claimant_id"] != user["id"]:
            raise HTTPException(status_code=404, detail="Claim not found.")
        if claim["status"] != "rejected":
            raise HTTPException(status_code=409, detail="Only a rejected claim can be disputed by its claimant.")
        if int(claim["appeal_count"] or 0) >= 1:
            raise HTTPException(status_code=409, detail="This claim has already used its one review request.")
        report = read_report(conn, claim["report_id"])
        if report["status"] != "available":
            raise HTTPException(status_code=409, detail="The item is no longer available for another claim review.")
        timestamp = now_iso()
        conn.execute(
            "UPDATE claims SET status='disputed', appeal_note=?, appeal_count=appeal_count+1, updated_at=? WHERE id=?",
            (reason, timestamp, claim_id),
        )
        audit(conn, user["id"], "claim_decision_disputed", "claim", claim_id,
              {"reason": reason, "appeal_count": 1})
        notify_role(conn, "office", "claim-appeal:" + claim_id, "Claim decision review requested",
                    "A claimant has requested a review of a rejected claim for item " + report["public_ref"] + ".",
                    "claim", claim_id)
        notify_user(conn, user["id"], "claim-appeal-confirmation:" + claim_id,
                    "Review request submitted", "Your claim decision has been sent to the campus office for review.",
                    "claim", claim_id)
        updated = conn.execute("SELECT * FROM claims WHERE id=?", (claim_id,)).fetchone()
    return {"claim": {"id": updated["id"], "status": updated["status"]},
            "message": "Review request submitted. Your claim is marked disputed until office staff review it."}


@app.post("/api/claims/{claim_id}/decision")
async def decide_claim(
    claim_id: str,
    body: ClaimDecisionBody,
    user: dict[str, Any] = Depends(authenticated_user),
):
    require_office(user)
    with connect_db() as conn:
        claim = conn.execute("SELECT * FROM claims WHERE id=?", (claim_id,)).fetchone()
        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found.")
        report = read_report(conn, claim["report_id"])
        if claim["status"] in {"rejected", "approved_for_collection", "returned"}:
            raise HTTPException(status_code=409, detail="This claim has already reached a final review state.")
        if body.action == "approve":
            others = conn.execute(
                "SELECT id FROM claims WHERE report_id=? AND id<>? AND status IN ('pending','disputed','needs_more_evidence')",
                (claim["report_id"], claim_id)
            ).fetchall()
            if others:
                raise HTTPException(status_code=409, detail="Other active claims exist. Resolve the competing claims before approving this one.")
            if report["status"] not in {"available"}:
                raise HTTPException(status_code=409, detail="The item is not available for claim approval.")
            allowed_checks = {
                "distinctive_features", "date_location", "physical_inspection",
                "supporting_evidence", "owner_specific_detail", "claimant_identity",
                "authorised_record",
            }
            checked = set(body.verification_checks)
            if checked - allowed_checks:
                raise HTTPException(status_code=422, detail="An unknown verification check was submitted.")
            level = int(report["verification_level"] or CATEGORY_DEFAULT_LEVEL.get(report["category"], 3))
            minimum_checks = {1: 2, 2: 3, 3: 4, 4: 4}.get(level, 4)
            if len(checked) < minimum_checks:
                raise HTTPException(status_code=422, detail=f"Verification level L{level} requires at least {minimum_checks} distinct checks.")
            if "claimant_identity" not in checked:
                raise HTTPException(status_code=422, detail="Confirm the claimant's identity before approving the claim.")
            if level >= 4 and "authorised_record" not in checked:
                raise HTTPException(status_code=422, detail="Restricted items require an authorised record/custodian check.")
            new_status = "approved_for_collection"
            conn.execute("UPDATE reports SET status='claim_approved', updated_at=? WHERE id=?",
                         (now_iso(), claim["report_id"]))
        elif body.action == "reject":
            new_status = "rejected"
        elif body.action == "request_more_evidence":
            new_status = "needs_more_evidence"
        else:
            new_status = "disputed"
        conn.execute(
            """UPDATE claims SET status=?, reviewer_id=?, reviewer_note=?, updated_at=? WHERE id=?""",
            (new_status, user["id"], body.note, now_iso(), claim_id),
        )
        if body.action == "approve":
            conn.execute(
                """INSERT OR REPLACE INTO claim_verifications(claim_id, verifier_user_id, checks_json, verified_at)
                   VALUES (?, ?, ?, ?)""",
                (claim_id, user["id"], json.dumps(sorted(checked)), now_iso()),
            )
        audit(conn, user["id"], "claim_review_decision", "claim", claim_id,
              {"decision": body.action, "new_status": new_status,
               "verification_checks": sorted(checked) if body.action == "approve" else []})
        notice_text = {
            "approve": "Your claim passed office verification. The office will complete the physical handover separately.",
            "reject": "Your claim was not approved. Contact the campus office if you believe further review is needed.",
            "request_more_evidence": "The office requested more evidence. Open My Claims to provide the requested information.",
            "mark_disputed": "Your claim is on hold while the office reviews a dispute.",
        }[body.action]
        notice_title = {
            "approve": "Claim verified",
            "reject": "Claim review updated",
            "request_more_evidence": "More evidence requested",
            "mark_disputed": "Claim on hold",
        }[body.action]
        notify_user(conn, claim["claimant_id"], "claim-decision:" + claim_id + ":" + new_status,
                    notice_title, notice_text, "claim", claim_id)
        if body.action == "reject":
            other_active = conn.execute(
                "SELECT 1 FROM claims WHERE report_id=? AND id<>? AND status IN ('pending','disputed','needs_more_evidence')",
                (claim["report_id"], claim_id)
            ).fetchone()
            if not other_active and report["status"] == "available":
                conn.execute("UPDATE reports SET status='available', updated_at=? WHERE id=?", (now_iso(), claim["report_id"]))
        updated = conn.execute("SELECT * FROM claims WHERE id=?", (claim_id,)).fetchone()
    return {"claim": {"id": updated["id"], "status": updated["status"]},
            "message": "Claim review updated. Physical collection is not recorded by this module."}




@app.post("/api/claims/{claim_id}/handover")
async def record_handover(
    claim_id: str,
    body: HandoverBody,
    user: dict[str, Any] = Depends(authenticated_user),
):
    require_office(user)
    if not body.confirmed_physical_handover or not body.claimant_identity_checked:
        raise HTTPException(status_code=422, detail="Confirm the physical handover and claimant identity.")
    with connect_db() as conn:
        claim = conn.execute("SELECT * FROM claims WHERE id=?", (claim_id,)).fetchone()
        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found.")
        if claim["status"] != "approved_for_collection":
            raise HTTPException(status_code=409, detail="Only an office-verified claim can proceed to handover.")
        report = read_report(conn, claim["report_id"])
        if report["status"] != "claim_approved" or not report["tag_id"]:
            raise HTTPException(status_code=409, detail="The item is not in the approved handover state.")
        if not secrets.compare_digest(str(body.tag_id).strip(), str(report["tag_id"])):
            raise HTTPException(status_code=422, detail="The entered tag ID does not match the office record.")
        timestamp = now_iso()
        conn.execute(
            """INSERT INTO handovers(id, claim_id, report_id, tag_id, claimant_id, office_user_id, handover_note, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (uuid.uuid4().hex, claim_id, report["id"], report["tag_id"], claim["claimant_id"],
             user["id"], body.note, timestamp),
        )
        conn.execute("UPDATE claims SET status='returned', reviewer_id=?, updated_at=? WHERE id=?",
                     (user["id"], timestamp, claim_id))
        conn.execute("UPDATE reports SET status='returned', updated_at=? WHERE id=?", (timestamp, report["id"]))
        if claim["lost_report_id"]:
            linked_lost = read_report(conn, claim["lost_report_id"])
            if linked_lost["status"] == "open":
                conn.execute(
                    """UPDATE reports SET status='closed', closure_reason=?, closure_note=?, updated_at=? WHERE id=?""",
                    ("recovered_through_verified_return",
                     "Closed automatically after verified handover of " + report["public_ref"] + ".",
                     timestamp, linked_lost["id"]),
                )
                audit(conn, user["id"], "linked_lost_report_closed_after_return", "report", linked_lost["id"],
                      {"claim_id": claim_id, "found_report_id": report["id"], "tag_id": report["tag_id"]})
                notify_user(
                    conn, claim["claimant_id"], "linked-lost-report-closed:" + linked_lost["id"],
                    "Lost report resolved",
                    "Your linked lost report " + linked_lost["public_ref"] +
                    " was closed automatically after the verified physical handover.",
                    "report", linked_lost["id"],
                )
        audit(conn, user["id"], "physical_handover_recorded", "claim", claim_id,
              {"report_id": report["id"], "tag_id": report["tag_id"]})
        award_points(
            conn, report["created_by"], POINT_RULES["verified_return"],
            "verified-return:" + report["id"],
            "The reported item was returned to a verified owner",
            report["id"], user["id"]
        )
        notify_user(conn, claim["claimant_id"], "handover:" + claim_id, "Item handover recorded",
                    "The campus office recorded the return of the item. The claim is complete.",
                    "claim", claim_id)
        notify_user(conn, report["created_by"], "item-returned:" + report["id"], "A reported item was returned",
                    "The office has completed a verified return associated with your found-item report.",
                    "report", report["id"])
    return {"claim_id": claim_id, "status": "returned", "message": "Physical handover recorded."}


@app.get("/api/notifications")
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


@app.post("/api/notifications/{notification_id}/read")
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


@app.post("/api/notifications/read-all")
async def mark_all_notifications_read(user: dict[str, Any] = Depends(authenticated_user)):
    with connect_db() as conn:
        conn.execute("UPDATE notifications SET read_at=? WHERE user_id=? AND read_at IS NULL",
                     (now_iso(), user["id"]))
    return {"ok": True}


@app.get("/api/activity/me")
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


@app.get("/api/leaderboard")
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


@app.get("/api/certificates/{certificate_id}/download")
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


@app.get("/api/office/summary")
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
