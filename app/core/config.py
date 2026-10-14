"""Environment-backed configuration and shared privacy/category policy."""
from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[2]  # app/core/config.py -> repository root
DATA_DIR = Path(os.getenv("DATA_DIR", str(ROOT / "data"))).resolve()
DB_PATH = Path(os.getenv("DATABASE_PATH", str(DATA_DIR / "lostlink.db"))).resolve()
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(DATA_DIR / "uploads"))).resolve()
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"
SESSION_SECRET = os.getenv("SESSION_SECRET", "").strip()
MAX_OPEN_CLAIMS_PER_STUDENT = 5
HTTPS_ONLY = os.getenv("SESSION_HTTPS_ONLY", "false").lower() == "true"
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_EVIDENCE_TYPES = {
    "distinctive_features", "purchase_or_receipt", "packaging_or_accessory",
    "timeline_and_location", "device_or_account_context", "other"
}

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
