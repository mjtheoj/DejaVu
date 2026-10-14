"""HTTP route group."""
from fastapi import APIRouter
from app.core.runtime import *
from app.schemas import *

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
    with connect_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE email=?", (body.email.strip().lower(),)).fetchone()
    if not row or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    request.session.clear()
    request.session["user_id"] = row["id"]
    return {"user": user_payload(row)}


@router.post("/api/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/api/me")
async def me(user: dict[str, Any] = Depends(authenticated_user)):
    return {"user": user}
