# LostLink Backend Architecture

## Purpose

This describes the actual modular layout of the LostLink prototype. The refactor preserves existing API URLs and workflow behaviour while separating route handlers from infrastructure and domain services.

## Project layout

- app/main.py — FastAPI composition root, session middleware, static files, router registration and DB initialisation.
- app/schemas.py — Pydantic request-body validation.
- app/matching.py — explainable lost/found matching, text similarity and optional CLIP similarity.
- app/core/config.py — environment settings, directories and shared category/privacy policy.
- app/core/database.py — SQLite lifecycle, schema, migrations, audit events and demo seed data.
- app/core/images.py — image validation, canonical JPEG conversion, SHA-256/perceptual fingerprints and watermarking.
- app/core/security.py — PBKDF2 password hash and verification helpers.
- app/core/runtime.py — compatibility facade re-exporting shared helpers to route modules and legacy imports.
- app/api/dependencies.py — current-session validation and office-role checks.
- app/api/routes/auth.py — home/config, login, logout and current-user endpoints.
- app/api/routes/reports.py — report create/search/close, report photos, match lookup, office intake and storage updates.
- app/api/routes/claims.py — claims, private evidence images, decisions, disputes and physical handover.
- app/api/routes/engagement.py — notifications, activity, leaderboard, certificates and office summary.
- app/services/reports.py — report serialisation, location labels and visibility/risk helpers.
- app/services/notifications.py — in-app notifications and possible-match alerts.
- app/services/rewards.py — idempotent contribution points and milestone certificate PDFs.
- app/static/ — frontend HTML, JavaScript and CSS.
- tests/ — matching, rewards and full workflow checks.
- scripts/run-jury-demo.ps1 — local student/office demo launcher.

## Request flow and dependency direction

1. app/main.py creates the FastAPI instance, applies Starlette session middleware, mounts static assets and registers four routers.
2. app/schemas.py validates login, report, claim, evidence, decision, dispute, intake, storage and handover request bodies.
3. The selected route calls shared domain helpers and the SQLite layer.
4. app/core/config.py provides environment-backed settings and privacy/category constants; app/core/database.py handles transactions, migrations and audit writes.
5. app/core/images.py and app/core/security.py handle image/password primitives. app/api/dependencies.py enforces sessions and office-only actions.
6. app/services owns report visibility/serialization, notification side effects and reward/certificate side effects.
7. app/matching.py ranks candidates from available text/category/location/time signals and optional learned-model signals.

## Main boundaries

### Database and configuration

The SQLite connection context manager commits on success, rolls back on exceptions, enables foreign keys and always closes the connection. Initialisation creates tables/indexes, applies additive migrations, backfills hashes for legacy report images where possible and seeds examples only when DEMO_MODE=true.

### Image and security utilities

Images are limited to supported formats, verified, EXIF-oriented, resized, re-encoded as JPEG and fingerprinted. Re-encoding removes original metadata. Exact SHA-256 plus perceptual similarity checks discourage reuse of report/claim images. Labelled previews discourage casual copying but cannot prevent screenshots.

Password helpers use PBKDF2-HMAC-SHA256 with a random salt and 180,000 iterations. Session middleware uses strict SameSite cookies, an eight-hour lifetime and the SESSION_HTTPS_ONLY option.

### Domain services

- reports.py keeps public/student serialisation separate from internal/office serialisation. Tag IDs, storage locations, private owner clues and risk details are only returned internally.
- notifications.py uses unique event keys to de-duplicate notifications, and ranks candidates to notify students of possible matches. A match is a lead, not ownership proof.
- rewards.py awards points only for configured verified events, writes idempotent ledger entries, audits awards and generates threshold certificates.
- matching.py uses a deterministic lexical baseline by default. Sentence Transformers and CLIP are optional and controlled by environment flags.

### API route ownership

- auth.py: GET /, GET /api/config, login/logout/me.
- reports.py: report list/search/create/close, report image upload/read, match list, physical intake and storage update.
- claims.py: claim create/list, evidence upload/read/update, dispute, decision and handover.
- engagement.py: notification read/list, activity, leaderboard, certificate download, office dashboard summary.

### Compatibility facade

app/core/runtime.py currently re-exports existing imports so the frontend/API behaviour and older tests remain compatible during the extraction. New functionality should be added to the owning module and imported directly rather than growing this facade further.

## Preserved invariants

- Found items remain outside student search until staff confirm physical receipt and tagging.
- Claim evidence is private to the claimant and office role.
- Private custody/verification information is not returned in public report responses.
- Match suggestions never approve claims; verified physical handover is a separate step.
- Notification and reward event keys prevent duplicate side effects.
- All existing /api/... paths are preserved.

## Not implemented

Automatic image captioning and keyword generation are not implemented. They should be added as a separate image-enrichment service integrated with report photo uploads and search indexing, while keeping AI-generated text distinct from user-written descriptions and private claim evidence.


## Matching evaluation

`tests/data/matching_benchmark.json` contains 15 manually labelled synthetic retrieval scenarios with one relevant candidate and five distractors per query. `scripts/evaluate_matching.py` reports top-1/top-3 hit rates and mean reciprocal rank for the lexical baseline, then for Sentence Transformers if its model loads. These figures are a development sanity check only; they do not estimate performance on real campus reports.
