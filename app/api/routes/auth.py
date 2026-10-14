"""HTTP route group."""
from fastapi import APIRouter, HTTPException, Request
from app.core.runtime import *
from app.schemas import *
from app.services.auth import clear_login_failures, login_lockout_remaining, record_failed_login

router = APIRouter()

@router.get("/")
def home():
    return FileResponse(ROOT / "app" / "static" / "index.html")


@router.get("/api/config")
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


@router.post("/api/login")
def login(body: LoginBody, request: Request):
    email = body.email.strip().lower()
    ip_address = request.client.host if request.client else "unknown"
    subjects = ["email:" + email, "ip:" + ip_address]
    locked_for = 0
    invalid_credentials = False
    user = None
    with connect_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        locked_for = login_lockout_remaining(conn, subjects)
        if not locked_for:
            row = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            if not row or not verify_password(body.password, row["password_hash"]):
                record_failed_login(conn, subjects)
                invalid_credentials = True
            else:
                clear_login_failures(conn, subjects)
                user = user_payload(row)
    if locked_for:
        raise HTTPException(
            status_code=429,
            detail="Too many sign-in attempts. Try again after the lockout period.",
            headers={"Retry-After": str(locked_for)},
        )
    if invalid_credentials or user is None:
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    request.session.clear()
    request.session["user_id"] = user["id"]
    return {"user": user}


@router.post("/api/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/api/me")
async def me(user: dict[str, Any] = Depends(authenticated_user)):
    return {"user": user}
