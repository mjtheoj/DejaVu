# Utilities and Libraries Used

## Runtime and application libraries

| Library | Use in LostLink |
| --- | --- |
| FastAPI | HTTP routing, dependency injection and request handling. |
| Uvicorn | Runs FastAPI as an ASGI application. |
| Pydantic | Validates request bodies and field limits in app/schemas.py. |
| Starlette SessionMiddleware | Signed browser sessions for student/office login. |
| python-dotenv | Loads development configuration from .env. |
| SQLite / sqlite3 | Local persistence, parameterised queries, foreign keys, migrations and transactions. |
| Pillow (PIL) | Verifies image content, applies EXIF orientation, resizes/re-encodes JPEGs, removes metadata, watermarks images and calculates fingerprints. |
| ReportLab | Produces downloadable milestone recognition certificate PDFs. |
| Sentence Transformers (optional) | Semantic text embeddings when USE_SEMANTIC_MODEL=true and the model is installed. |
| Transformers + PyTorch / CLIP (optional) | Image similarity when USE_CLIP_MODEL=true. Model weights may be downloaded or need to be cached. |

## Standard-library utilities

| Module | Use |
| --- | --- |
| sqlite3 | DB access and transaction control. |
| hashlib and secrets | SHA-256 image fingerprints, salted password hashes, constant-time comparison and random tokens. |
| uuid | Opaque report, claim, notification and event IDs. |
| datetime, timezone and timedelta | Timestamps and date-sensitive matching. |
| pathlib.Path | Resolve database/upload paths and constrain image-file access. |
| io.BytesIO | Work with image bytes and build PDF/image responses in memory. |
| json | Audit details and claim verification/evidence payloads. |
| re and difflib.SequenceMatcher | Token normalisation and deterministic lexical matching. |
| contextlib.contextmanager | Commit successful SQLite operations, roll back failures, always close connections. |

## Related project files

- requirements.txt — runtime dependencies.
- requirements-ml.txt — adds Sentence Transformers.
- requirements-dev.txt — test dependencies used by CI.
- .env.example — environment variables and defaults.
- scripts/run-jury-demo.ps1 — Windows launcher for student/office demo sessions that share a local SQLite database.

## Configuration

DEMO_MODE=true seeds demonstration users and reports; turn it off outside local demos. SESSION_SECRET must be changed for a shared environment. SESSION_HTTPS_ONLY=true enables secure-only session cookies. DATABASE_PATH and UPLOAD_DIR control persistence. USE_SEMANTIC_MODEL and USE_CLIP_MODEL opt into ML models; the deterministic lexical matcher remains the fallback.

## Explicit limitation

Automatic image captioning and keyword extraction are not in the current implementation. Image utilities validate/fingerprint images, while optional CLIP compares images; neither creates a textual description for a short student report. This should be implemented as a separate image-enrichment service whose generated terms stay distinct from user-entered descriptions and private claim evidence.


## Measure matching quality

Run `python scripts/evaluate_matching.py` for baseline numbers. After installing `requirements-ml.txt`, run `USE_SEMANTIC_MODEL=true python scripts/evaluate_matching.py --require-semantic-model` to require a real Sentence Transformers model load. The fixture is synthetic and manually labelled, not real campus ground truth.
