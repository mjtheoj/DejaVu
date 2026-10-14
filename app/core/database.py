"""SQLite connections, migrations, audit events and optional demo seeding."""
from __future__ import annotations
import hashlib, json, sqlite3, uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from PIL import UnidentifiedImageError
from app.core.config import *
from app.core.images import perceptual_hash_from_bytes
from app.core.security import hash_password

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
            CREATE TABLE IF NOT EXISTS login_attempts (
                subject TEXT PRIMARY KEY,
                failure_count INTEGER NOT NULL DEFAULT 0,
                window_started_at TEXT NOT NULL,
                locked_until TEXT
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
