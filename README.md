# DejaVu · LostLink

LostLink is a campus lost-and-found prototype. It supports structured reports, optional photos, search and filtering, explainable candidate matching, office-confirmed physical intake, private claim review, in-app notifications, return tracking, and verified-contribution rewards.

It is a standalone prototype, not a live integration with the official CVR College of Engineering Android app or its identity system.

## Student workflow

1. Submit a lost or found report with description, category, date, block, floor, room/area and an optional photo.
2. Search office-held found items by keyword, category, block/area, room and date range.
3. Open possible matches for a lost report. Explanations use the available text, category, date, location and optional image signals.
4. Submit private evidence for a found-item claim and track the review status.
5. View in-app notifications, verified activity points and milestone certificates.

Found reports remain unavailable in public search until office staff physically receive the item and assign a tag. Public records do not expose physical tag IDs, private verification details, estimated value bands, verification levels or raw matching scores.

## Office workflow

1. Review found reports awaiting physical intake.
2. Confirm physical receipt, record a private identifying detail or approved verification method, set internal value/sensitivity inputs, and assign a unique LostLink physical tag.
3. Review private claim evidence. Resolve competing/disputed claims before approval.
4. Approve, reject, request additional evidence or place a claim on hold.
5. For an approved claim, compare the physical item's tag ID, check the claimant's identity and confirm the physical handover. The app records the handover and closes the claim.

The AI ranker suggests candidates only; it does not prove ownership or approve a claim.

## Verified contribution points and certificates

Points are awarded only for auditable office-confirmed events. Submitting a form alone earns no points.

- +10 points when the campus office physically receives and tags a student-submitted found item.
- +5 points when the office records a verified return after an approved claim.
- Duplicate event keys are ignored, so repeating the same API request cannot award points twice.

Milestone certificates are issued once per student and can be downloaded as PDFs:

- **Verified Finder:** 20 points
- **Campus Helper:** 50 points
- **Community Champion:** 100 points

Certificate downloads state that they are prototype recognition documents and are not official CVR College credentials. Official branding or institutional recognition requires college approval.

## Notifications

The app creates in-app notifications for possible matches, found-item intake, claim submission/review, additional evidence requests, handover completion, points and certificate milestones. Users can see and mark only their own notifications as read. Notifications are not email, SMS or push notifications.

## Matching modes

The default engine is a deterministic text baseline combined with category, location and date signals. It is intended as a reproducible baseline, not a learned semantic model.

Optional pretrained modes can be enabled after installing the ML dependencies:

    pip install -r requirements-ml.txt

Set USE_SEMANTIC_MODEL=true for Sentence Transformers semantic text embeddings, and/or USE_CLIP_MODEL=true for optional image/image or image/text similarity. The first model load may download weights and require additional disk space, RAM and startup time. Confirm which mode actually loads before describing a demo as model-based. Missing or failed model loads fall back to the lightweight baseline. Similarity is not a probability of ownership.

## Run locally on Windows

Python 3.10 or later is recommended.

    py -m venv .venv
    .venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    Copy-Item .env.example .env
    python -m uvicorn app.main:app --reload

Open http://127.0.0.1:8000.

When DEMO_MODE=true, local sample data and demo accounts are available:

- Student: student@lostlink.local / student123
- Office: office@lostlink.local / office123

These credentials are for local evaluation only. Do not expose a demo-mode server to the public internet. Set a strong random session secret before any shared deployment. SQLite data and uploaded images live under the local data/ directory, which is ignored by Git.

## Suggested local demo sequence

1. Sign in as the demo student and open the seeded lost backpack report under My Reports. Use Find possible matches to demonstrate candidate ranking and explanations.
2. Submit a found-item report as the student. Sign in as the campus office and confirm physical receipt. The item receives a physical tag and the reporter earns 10 points.
3. Repeat with a second found report and confirm intake. The student reaches the 20-point Verified Finder milestone and can download the prototype PDF certificate in Activity & Certificates.
4. As the student, claim an available found item using private evidence. As office staff, review the evidence, approve the claim, then record the physical handover by entering the exact tag ID and confirming the identity/hand-over check.
5. Return to the student's Notifications and Activity & Certificates sections to show match/review updates, the point ledger and the issued certificate.

The demo data is illustrative. A demo intake action represents an office-confirmed event in the local database; it is not evidence of an actual campus recovery.

## Tests

Install test dependencies and run the full unit and workflow tests:

    pip install -r requirements-dev.txt
    python -m unittest discover -s tests -v

The GitHub Actions workflow also compiles Python, checks JavaScript syntax, runs tests and imports the application.

## Integration and production requirements

- Replace the prototype block/floor/room options with the verified campus directory.
- Obtain an approved integration point and authentication contract before linking to the official CVR Android app.
- Replace demo login with institutional authentication.
- Review role permissions, privacy, retention, upload controls, rate limiting, CSRF protection and operational logging.
- Configure HTTPS, a strong session secret, data backups and controlled office access.
- Approve reward policy, point thresholds and certificate language with the college before institutional use.
- Evaluate matching against a labelled dataset and keyword baseline; do not publish unmeasured accuracy claims.
