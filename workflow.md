# LostLink Backend Workflow

This walks through the current backend in execution order. The modular split keeps the existing API routes and workflow.

## 1. Startup

1. app/main.py creates the FastAPI application and registers the route modules.
2. app/core/config.py loads values from .env, resolves database/upload paths and defines category/privacy rules.
3. Session middleware uses an eight-hour max age, strict SameSite cookies and SESSION_HTTPS_ONLY.
4. initialise_db() creates tables/indexes, adds compatible schema migrations, backfills fingerprints on older report images where possible, and seeds sample users/items only when DEMO_MODE=true.

Never use demo credentials or the fallback session secret in a public deployment.

## 2. Authentication

Routes: POST /api/login, POST /api/logout, GET /api/me.

1. The backend looks up the user and verifies the password using PBKDF2-HMAC-SHA256.
2. On success, the account ID is stored in the signed session cookie.
3. Protected routes use app/api/dependencies.py to reload the user record and clear invalid/expired sessions.
4. Office-only routes enforce role checks; students cannot perform staff custody or claim-decision actions.

## 3. Report creation

Route: POST /api/reports. ReportBody in app/schemas.py validates the submitted shape.

1. The student chooses Lost or Found in the UI and submits title, description, category and optional brand, colour, visible features, date and place.
2. Pydantic checks field types/lengths and route logic checks the minimum meaningful title/description.
3. Lost reports start open. Student-submitted found reports start in awaiting_intake and do not appear publicly yet.
4. If a photo is uploaded, the image route verifies content/type, corrects orientation, resizes and re-encodes it, removes embedded metadata and records SHA-256/perceptual fingerprints.
5. Reused exact or perceptually near-identical stored images are rejected. Private owner-only clues should not be entered in public description fields.

Automatic description generation and keyword extraction from images are not implemented yet.

## 4. Search and matching

Routes: GET /api/reports and GET /api/reports/{report_id}/matches. Engine: app/matching.py.

1. Search applies optional query, category, block, room and date filters. Text matching covers title, description, public reference, location area, brand, colour, visible characteristics and location components.
2. Student search exposes available found items and only the relevant public fields; office-only and sensitive data stay restricted.
3. Matching compares textual characteristics and category, then adds location/date signals when those fields exist on both reports.
4. Sentence Transformers can be enabled for semantic text similarity; CLIP can add image similarity. Both are optional; the lexical baseline works without model downloads.
5. The service returns ranked candidates, strength and reasons. New possible matches can create a deduplicated in-app notification when the score meets a heuristic threshold.
6. A match is only a lead. It is not proof of ownership and cannot bypass the claim workflow.

## 5. Office intake and custody

Routes: POST /api/reports/{report_id}/intake and POST /api/reports/{report_id}/storage.

1. The found report remains in awaiting_intake until authorised staff confirm physical receipt.
2. Staff record the storage location, private identifying clue, value/sensitivity information and intake confirmation.
3. The backend assigns a physical LostLink Tag ID, changes the report to available, awards configured verified-intake points and records an audit event.
4. Only then is the found item made searchable by students.
5. Storage changes update the cabinet/room/shelf record and create an audit trail.

## 6. Claim and private evidence

Routes: POST /api/claims, GET /api/claims, POST /api/claims/{claim_id}/evidence, POST/GET /api/claims/{claim_id}/evidence-image.

1. A student chooses an available found item, provides a written ownership explanation and selects at least one evidence category.
2. The claim may link to the student's own open lost report. Claim proof remains private rather than becoming public item-search text.
3. An optional supporting image is normalised and checked against report and claim image fingerprints.
4. Only the claimant and office role can access the claim image; other students cannot view the evidence.
5. Staff review identity, proof and private item-specific details, then record a decision/checklist.

## 7. Dispute, decision and handover

Routes: POST /api/claims/{claim_id}/decision, POST /api/claims/{claim_id}/dispute and POST /api/claims/{claim_id}/handover.

1. Approval places the claim in the collection/handover queue; it does not automatically return the item.
2. A rejected claim can use the supported appeal/dispute path, subject to the one-appeal limit.
3. At handover, office staff verify the exact recorded tag, claimant details and physical transfer.
4. A successful transfer creates a handover record, updates claim/report state, closes a linked lost report where appropriate, records audit activity and sends notifications.
5. Invalid tag checks and repeated handover attempts are rejected.

## 8. Notifications, activity and rewards

Routes include /api/notifications, /api/activity/me, /api/leaderboard, /api/certificates/{certificate_id}/download and /api/office/summary.

- Notifications use unique event keys to avoid duplicate alerts.
- The reward ledger's unique user/event key ensures an event awards points only once.
- Verified-intake and verified-return rules award points; milestone thresholds create at most one certificate per user/tier.
- Activity and leaderboard views do not disclose email addresses or private claim evidence.

## 9. Privacy and failure handling

- Sensitive categories limit public location/photo detail.
- Tag IDs, storage locations, owner-only clues and claim proof are withheld from public report data.
- Image re-encoding removes original metadata and normalises orientation.
- SHA-256 catches exact normalised duplicates; perceptual hashes catch many close copies, but neither prevents screenshots or all transformations.
- Invalid uploads and unauthorised requests are rejected; the DB context manager rolls back failed transactions.
- Optional ML model errors fall back to the lexical baseline when possible.

## 10. Route map

| Area | Endpoints |
| --- | --- |
| Auth/config | GET /, GET /api/config, POST /api/login, POST /api/logout, GET /api/me |
| Reports | GET/POST /api/reports, close, image upload/read, matches |
| Office | intake, storage and GET /api/office/summary |
| Claims | create/list, evidence upload/read/update, dispute, decision and handover |
| Engagement | notifications, activity, leaderboard and certificate download |


## Matching evaluation

The CI `matching-evaluation` job installs the optional semantic dependency and tries to run `scripts/evaluate_matching.py --require-semantic-model`. It prints baseline and semantic top-1/top-3 hit rates for 15 synthetic labelled queries. The job is allowed to fail independently if model installation/download is unavailable; no semantic hit rate is claimed unless the evaluator confirms the model actually loaded.
