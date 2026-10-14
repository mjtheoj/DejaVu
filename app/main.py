"""FastAPI application composition root for LostLink."""
from __future__ import annotations
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from app.core.config import *
from app.core.database import *
from app.core.images import *
from app.core.security import *
from app.core.runtime import *
from app.schemas import *
from app.api.routes.auth import router as auth_router
from app.api.routes.reports import router as reports_router
from app.api.routes.claims import router as claims_router
from app.api.routes.engagement import router as engagement_router

if not SESSION_SECRET or SESSION_SECRET in {
    "replace-with-a-long-random-secret-before-running",
    "local-development-only-change-this",
}:
    raise RuntimeError("SESSION_SECRET is unset or a placeholder. Set a unique random secret in .env before starting LostLink.")

app = FastAPI(title="LostLink", version="0.1.0")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, same_site="strict", https_only=HTTPS_ONLY, max_age=60 * 60 * 8)
app.mount("/static", StaticFiles(directory=str(ROOT / "app" / "static")), name="static")
app.include_router(auth_router)
app.include_router(reports_router)
app.include_router(claims_router)
app.include_router(engagement_router)
initialise_db()
