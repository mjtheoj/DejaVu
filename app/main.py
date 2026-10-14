from __future__ import annotations

import hashlib
import json
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
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from PIL import Image, ImageOps, UnidentifiedImageError
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
                category TEXT NOT NULL,
                occurred_at TEXT,
                location_block TEXT,
                location_floor TEXT,
                location_room TEXT,
                location_area TEXT,
                image_path TEXT,
                status TEXT NOT NULL,
                created_by INTEGER NOT NULL REFERENCES users(id),
                tag_id TEXT UNIQUE,
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
                claimant_id INTEGER NOT NULL REFERENCES users(id),
                evidence TEXT NOT NULL,
                status TEXT NOT NULL,
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
            CREATE INDEX IF NOT EXISTS idx_reports_status_type ON reports(status, report_type);
            CREATE INDEX IF NOT EXISTS idx_reports_category ON reports(category);
            CREATE INDEX IF NOT EXISTS idx_claims_report ON claims(report_id, status);
            CREATE INDEX IF NOT EXISTS idx_claims_claimant ON claims(claimant_id, created_at);
            """
        )
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
            "storage_location": "Campus Lost & Found Office" if row["tag_id"] else None,
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
    occurred_at: str | None = None
    location_block: str | None = Field(default=None, max_length=80)
    location_floor: str | None = Field(default=None, max_length=40)
    location_room: str | None = Field(default=None, max_length=80)
    location_area: str | None = Field(default=None, max_length=120)


class IntakeBody(BaseModel):
    confirmed_physical_receipt: bool
    private_detail: str | None = Field(default=None, max_length=1200)
    value_band: Literal["low", "medium", "high", "unknown"] = "unknown"
    sensitivity_level: int = Field(default=1, ge=1, le=4)


class ClaimBody(BaseModel):
    report_id: str
    evidence: str = Field(min_length=20, max_length=1800)


class ClaimEvidenceBody(BaseModel):
    evidence: str = Field(min_length=20, max_length=1800)


class ClaimDecisionBody(BaseModel):
    action: Literal["approve", "reject", "request_more_evidence", "mark_disputed"]
    note: str | None = Field(default=None, max_length=800)


@app.get("/")
def home():
    return FileResponse(ROOT / "app" / "static" / "index.html")


@app.get("/api/config")
def public_config():
    return {
        "demo_mode": DEMO_MODE,
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
        conditions.append("(LOWER(r.title) LIKE ? OR LOWER(r.description) LIKE ? OR LOWER(r.public_ref) LIKE ? OR LOWER(COALESCE(r.location_area,'')) LIKE ?)")
        params.extend([term, term, term, term])
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
    return {"reports": [serialise_report(row, internal=internal) for row in rows]}


@app.post("/api/reports")
async def create_report(body: ReportBody, user: dict[str, Any] = Depends(authenticated_user)):
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
            """INSERT INTO reports(id, public_ref, report_type, title, description, category,
               occurred_at, location_block, location_floor, location_room, location_area, status,
               created_by, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (report_id, public_ref, body.report_type, body.title.strip(), body.description.strip(),
             body.category, body.occurred_at, body.location_block, body.location_floor,
             body.location_room, body.location_area, status, user["id"], timestamp, timestamp),
        )
        audit(conn, user["id"], "report_created", "report", report_id, {"report_type": body.report_type})
        row = read_report(conn, report_id)
    return {"report": serialise_report(row, internal=user["role"] == "office"),
            "message": "Lost report submitted." if body.report_type == "lost" else "Found-item report submitted for office intake. It will become searchable after staff confirm receipt."}


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
    Image.MAX_IMAGE_PIXELS = 24_000_000
    try:
        with Image.open(BytesIO(raw)) as check:
            if check.format not in {"JPEG", "PNG", "WEBP"}:
                raise HTTPException(status_code=415, detail="Use a JPG, PNG or WebP image.")
            check.verify()
        with Image.open(BytesIO(raw)) as source:
            safe = ImageOps.exif_transpose(source).convert("RGB")
            safe.thumbnail((1800, 1800))
            filename = uuid.uuid4().hex + ".jpg"
            safe.save(UPLOAD_DIR / filename, format="JPEG", quality=88, optimize=True)
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(status_code=415, detail="The file is not a valid supported image.")
    with connect_db() as conn:
        row = read_report(conn, report_id)
        old = row["image_path"]
        conn.execute("UPDATE reports SET image_path=?, updated_at=? WHERE id=?", (filename, now_iso(), report_id))
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
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})


@app.get("/api/reports/{report_id}/matches")
async def get_matches(report_id: str, user: dict[str, Any] = Depends(authenticated_user)):
    from app.matching import matching_engine

    with connect_db() as conn:
        lost = read_report(conn, report_id)
        if lost["report_type"] != "lost":
            raise HTTPException(status_code=400, detail="Matches are generated from a lost-item report.")
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
            """UPDATE reports SET status='available', tag_id=?, private_detail=?, value_band=?,
               sensitivity_level=?, verification_level=?, updated_at=? WHERE id=?""",
            (tag_id, (body.private_detail or "").strip() or None, body.value_band,
             body.sensitivity_level, level, now_iso(), report_id),
        )
        audit(conn, user["id"], "found_item_received_and_tagged", "report", report_id,
              {"tag_id": tag_id, "verification_level": "L" + str(level)})
        updated = read_report(conn, report_id)
    return {"report": serialise_report(updated, internal=True), "message": "Physical receipt recorded and tag assigned."}


@app.post("/api/claims")
async def create_claim(body: ClaimBody, user: dict[str, Any] = Depends(authenticated_user)):
    if user["role"] != "student":
        raise HTTPException(status_code=403, detail="Claims must be submitted from a student account.")
    with connect_db() as conn:
        report = read_report(conn, body.report_id)
        if report["report_type"] != "found" or report["status"] != "available":
            raise HTTPException(status_code=409, detail="This item is not accepting claims.")
        if report["created_by"] == user["id"]:
            raise HTTPException(status_code=400, detail="You cannot claim your own found-item report.")
        existing_own = conn.execute(
            "SELECT id FROM claims WHERE report_id=? AND claimant_id=? AND status IN ('pending','disputed','needs_more_evidence','approved_for_collection')",
            (body.report_id, user["id"])
        ).fetchone()
        if existing_own:
            raise HTTPException(status_code=409, detail="You already have an active claim for this item.")
        active = conn.execute(
            "SELECT id FROM claims WHERE report_id=? AND status IN ('pending','disputed','needs_more_evidence')",
            (body.report_id,)
        ).fetchall()
        status = "disputed" if active else "pending"
        claim_id = uuid.uuid4().hex
        timestamp = now_iso()
        conn.execute(
            """INSERT INTO claims(id, report_id, claimant_id, evidence, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (claim_id, body.report_id, user["id"], body.evidence.strip(), status, timestamp, timestamp),
        )
        if active:
            conn.execute(
                "UPDATE claims SET status='disputed', updated_at=? WHERE report_id=? AND status IN ('pending','disputed','needs_more_evidence')",
                (timestamp, body.report_id),
            )
        audit(conn, user["id"], "claim_submitted", "claim", claim_id,
              {"report_id": body.report_id, "competing_claims": bool(active)})
        claim = conn.execute("SELECT * FROM claims WHERE id=?", (claim_id,)).fetchone()
    return {"claim": {"id": claim["id"], "status": claim["status"], "created_at": claim["created_at"],
                      "report": serialise_report(report), "message": "Claim submitted for review."}}


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
            entry = {
                "id": claim["id"],
                "status": claim["status"],
                "created_at": claim["created_at"],
                "updated_at": claim["updated_at"],
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
        updated = conn.execute("SELECT * FROM claims WHERE id=?", (claim_id,)).fetchone()
        report = read_report(conn, updated["report_id"])
    return {"claim": {"id": updated["id"], "status": updated["status"],
                      "report": serialise_report(report), "message": "Additional evidence submitted."}}


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
        if claim["status"] in {"rejected", "approved_for_collection"}:
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
        audit(conn, user["id"], "claim_review_decision", "claim", claim_id,
              {"decision": body.action, "new_status": new_status})
        updated = conn.execute("SELECT * FROM claims WHERE id=?", (claim_id,)).fetchone()
    return {"claim": {"id": updated["id"], "status": updated["status"]},
            "message": "Claim review updated. Physical collection is not recorded by this module."}


@app.get("/api/office/summary")
async def office_summary(user: dict[str, Any] = Depends(authenticated_user)):
    require_office(user)
    with connect_db() as conn:
        intake = conn.execute("SELECT COUNT(*) AS n FROM reports WHERE report_type='found' AND status='awaiting_intake'").fetchone()["n"]
        available = conn.execute("SELECT COUNT(*) AS n FROM reports WHERE report_type='found' AND status='available'").fetchone()["n"]
        claims = conn.execute("SELECT COUNT(*) AS n FROM claims WHERE status IN ('pending','disputed','needs_more_evidence')").fetchone()["n"]
        disputed = conn.execute("SELECT COUNT(*) AS n FROM claims WHERE status='disputed'").fetchone()["n"]
    return {"awaiting_intake": intake, "available_items": available, "active_claims": claims, "disputed_claims": disputed}
