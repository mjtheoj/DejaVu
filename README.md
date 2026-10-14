# LostLink — Campus Lost-and-Found Workflow

LostLink is a web application for managing campus lost property from initial report through verified physical return. Students submit lost or found reports and receive possible-match suggestions. Authorised office staff manage physical intake, item tagging and storage, private ownership-claim review, disputes and recorded handover.

**The central rule is that a match is a lead, not proof of ownership.** A found item becomes visible for student discovery only after authorised staff confirm physical receipt and record custody. Claim approval and physical handover are separate steps; the application requires the exact physical LostLink Tag ID and identity/handover confirmations before recording a return.

> **Project status:** working standalone prototype. It uses SQLite and local image files. It has not yet been validated for production-scale load or connected to an institutional identity provider.

## Contents

- [Problem and goals](#problem-and-goals)
- [Features](#features)
- [End-to-end workflow](#end-to-end-workflow)
- [Architecture](#architecture)
- [Repository structure](#repository-structure)
- [Matching engine](#matching-engine)
- [Security and privacy](#security-and-privacy)
- [HTTP API reference](#http-api-reference)
- [Technology stack](#technology-stack)
- [Local installation](#local-installation)
- [Configuration](#configuration)
- [Testing and matching evaluation](#testing-and-matching-evaluation)
- [Limitations and production considerations](#limitations-and-production-considerations)

## Problem and goals

Lost-and-found information is often scattered across group chats, notices and informal desks. Descriptions can be incomplete, students may not see a relevant announcement, and a claim or image similarity alone cannot establish ownership. Staff also need to know where a physical item is stored and whether it was actually returned.

LostLink brings the process into one traceable workflow:

1. Capture structured lost and found reports.
2. Keep found-item listings hidden until staff confirm physical receipt.
3. Rank possible matches and explain which recorded signals overlap.
4. Keep claim explanations and evidence private to the claimant and authorised office staff.
5. Track the item's Tag ID, real storage location, claim decision and physical handover.
6. Record audit events and award contribution points only for defined verified actions.

## Features

### Student-facing features

- Create a lost-item report or a found-item report through separate guided paths.
- Record title, description, category, approximate occurrence time and campus location. Brand, primary colour, visible characteristics and a photo can add detail.
- Browse and filter available found items by keywords, category, block, room and date.
- Open item details and suggested-match explanations.
- Receive in-app notifications about report status and possible matches.
- Submit a claim with a private explanation and evidence categories; attach a private supporting image.
- Track claim state, respond when more evidence is requested and request one formal review after a rejection.
- View personal activity, verified contribution points, leaderboard information and milestone certificate PDFs.

### Office-facing features

- Review found-item reports awaiting physical intake.
- Confirm actual receipt of the object before making the report available to students.
- Record the actual room, cabinet, shelf or other storage location; capture private verification information; set value and sensitivity fields; and assign a unique LostLink Tag ID.
- Update a stored item's location and retain the movement in the audit history.
- Review private claim evidence and checklist results; approve, reject, request more evidence or mark a claim disputed.
- Resolve competing claims rather than treating the first submitted claim as automatically valid.
- Retrieve the object from the recorded location, check the exact physical Tag ID and claimant identity, confirm actual handover, and record the return.
- Inspect office summary information and review in-app notifications.

### Recognition and accountability

The prototype records a reward ledger. The configured rules award 10 points when a student-submitted found item is physically received and tagged by office staff, and 5 points when an eligible verified return is recorded. Unique event keys help prevent duplicate awards. Milestone certificates are generated at configured thresholds of 20, 50 and 100 points.

These are prototype recognition features; the generated certificates are not official college credentials.

## End-to-end workflow

    STUDENT REPORTS LOST ITEM ───────────────────────────────┐
                                                            │
    STUDENT REPORTS FOUND ITEM                              │
              │                                             │
              ▼                                             │
    OFFICE CONFIRMS PHYSICAL RECEIPT                        │
              │                                             │
              ▼                                             │
    RECORD PRIVATE DETAILS AND ACTUAL STORAGE LOCATION     │
              │                                             │
              ▼                                             │
    ASSIGN PHYSICAL LOSTLINK TAG ID                         │
              │                                             │
              └───────────────► AVAILABLE FOUND INVENTORY ◄─┘
                                      │
                                      ▼
                           SEARCH AND RANK CANDIDATES
                                      │
                                      ▼
                             STUDENT SUBMITS CLAIM
                                      │
                                      ▼
                        OFFICE REVIEWS EVIDENCE AND IDENTITY
                                      │
                          ┌───────────┴────────────┐
                          │                        │
                          ▼                        ▼
                  MORE EVIDENCE / DISPUTE       APPROVED
                          │                        │
                          └──────► REVIEW          ▼
                                       RETRIEVE PHYSICAL ITEM
                                                  │
                                                  ▼
                                     VERIFY EXACT TAG ID AND IDENTITY
                                                  │
                                                  ▼
                                      CONFIRM ACTUAL HANDOVER
                                                  │
                                                  ▼
                                       AUDIT, STATUS AND NOTIFICATIONS

### Report lifecycle

| Situation | Behaviour |
|---|---|
| Lost report is submitted | Starts as an open search record and may receive possible-match suggestions. |
| Found report is submitted | Starts in an awaiting-intake state and is not visible in the student found-item search. |
| Office confirms intake | Staff record actual storage and private verification details, assign a Tag ID, and make the found item available. |
| Stored item is moved | Office staff update the location; the change is audited. |
| Claim is created | Private evidence is linked to a claim for authorised office review. |
| More evidence is required or a dispute exists | The claim stays in the review process; the item is not automatically released. |
| Claim is approved | It becomes eligible for collection but is not yet marked returned. |
| Physical handover is confirmed | The office checks the physical tag and claimant identity, records handover and marks the item returned. |
| Student closes or withdraws an eligible report | Closure rules apply; a found item cannot be withdrawn by the student after the office has accepted physical custody. |

The database uses explicit report and claim status values to enforce these transitions. The API performs validation and role checks on state-changing operations.

## Architecture

LostLink uses a single FastAPI application composed of route groups, shared infrastructure utilities and domain services.

    Browser: student and office interface
        HTML + CSS + vanilla JavaScript
                         │ HTTP / JSON
                         ▼
    FastAPI application (app/main.py)
        ├── Session middleware and role dependencies
        ├── Authentication routes
        ├── Report/search/photo/intake/storage routes
        ├── Claim/evidence/decision/dispute/handover routes
        ├── Notification/activity/reward/certificate routes
        ├── Matching engine
        └── Report, notification and reward services
                         │
             ┌───────────┴───────────┐
             ▼                       ▼
    SQLite database           Local image directory
        ├── Users                  ├── Report images
        ├── Reports                └── Private claim evidence
        ├── Claims
        ├── Notifications
        ├── Storage and Tag IDs
        ├── Handover records
        ├── Reward ledger
        ├── Certificates
        └── Audit events

### Module responsibilities

| Component | Responsibility |
|---|---|
| <code>app/main.py</code> | Creates the FastAPI application, validates the session-secret configuration, adds session middleware, mounts static assets, registers routers and initialises the database. |
| <code>app/api/dependencies.py</code> | Resolves the current session and enforces office-role access where required. |
| <code>app/api/routes/auth.py</code> | Login, logout, current-user and public app configuration endpoints. |
| <code>app/api/routes/reports.py</code> | Report creation/search/closure, report photos, candidate matching, office intake and storage updates. |
| <code>app/api/routes/claims.py</code> | Claim creation/listing, private evidence, office decisions, disputes and physical handover. |
| <code>app/api/routes/engagement.py</code> | Notifications, activity, leaderboard, certificate downloads and office summary. |
| <code>app/core/config.py</code> | Environment configuration, data paths, categories, sensitivity levels and workflow constants. |
| <code>app/core/database.py</code> | SQLite connections, schema creation, additive migrations, indexes, transactions, audit writing and optional demo seeding. |
| <code>app/core/images.py</code> | Image validation/canonicalisation, hashing, perceptual fingerprints and watermarked student previews. |
| <code>app/core/security.py</code> | Password hashing and verification. |
| <code>app/services/auth.py</code> | Persistent login-failure tracking and temporary lockout calculations. |
| <code>app/services/reports.py</code> | Report serialisation, role-aware response filtering and related report helpers. |
| <code>app/services/notifications.py</code> | In-app notifications and possible-match notification logic. |
| <code>app/services/rewards.py</code> | Idempotent verified-contribution points, reward ledger and certificate generation. |
| <code>app/matching.py</code> | Candidate scoring, optional ML model loading, ranking and explanation signals. |
| <code>app/schemas.py</code> | Pydantic request models and field constraints. |
| <code>app/static/</code> | Frontend HTML, CSS and JavaScript. |

More implementation notes are available in [Architecture.md](Architecture.md).

## Repository structure

    DejaVu/
    ├── .env.example
    ├── .github/workflows/lostlink-checks.yml
    ├── Architecture.md
    ├── README.md
    ├── app/
    │   ├── main.py
    │   ├── matching.py
    │   ├── schemas.py
    │   ├── api/
    │   │   ├── dependencies.py
    │   │   └── routes/
    │   │       ├── auth.py
    │   │       ├── reports.py
    │   │       ├── claims.py
    │   │       └── engagement.py
    │   ├── core/
    │   │   ├── config.py
    │   │   ├── database.py
    │   │   ├── images.py
    │   │   ├── security.py
    │   │   └── runtime.py
    │   ├── services/
    │   │   ├── auth.py
    │   │   ├── reports.py
    │   │   ├── notifications.py
    │   │   └── rewards.py
    │   └── static/
    │       ├── index.html
    │       ├── app.js
    │       └── styles.css
    ├── scripts/
    │   ├── run-demo.ps1
    │   └── evaluate_matching.py
    ├── tests/
    │   ├── data/matching_benchmark.json
    │   ├── test_frontend_contract.py
    │   ├── test_matching.py
    │   ├── test_matching_benchmark.py
    │   ├── test_rewards.py
    │   └── test_workflow.py
    ├── requirements.txt
    ├── requirements-dev.txt
    └── requirements-ml.txt

The local runtime creates the <code>data/</code> directory for the SQLite database and uploaded images. This runtime data is ignored by Git.

## Matching engine

LostLink is designed to work without an external AI service. The deterministic lexical baseline is the default; pretrained models are optional and disabled by default.

### Baseline text similarity

The lexical baseline:
1. Converts text to lowercase and tokenises letters/numbers.
2. Removes common stop words.
3. Normalises selected synonyms, for example “backpack” and “rucksack” to “bag”, and “navy” to “blue”.
4. Calculates Jaccard token overlap, sequence similarity using Python's <code>difflib.SequenceMatcher</code>, and overlap on selected distinguishing details such as colours, scratches, stickers, zippers, logos and cases.
5. Combines these parts as: 55% Jaccard overlap, 30% sequence similarity and 15% distinguishing-detail overlap.

This calculation is deterministic and does not require network access or model weights.

### Structured signals and ranking

Candidate comparison may use:
- Description text assembled from title, description, brand, primary colour, visible features and category.
- Category agreement.
- Location agreement using block, floor, room and area.
- Difference between the reported occurrence times.
- Optional image similarity if CLIP is enabled and image files are available.

When a CLIP result is available, the component weights are text 0.42, category 0.18, image 0.20, location 0.10 and time 0.10. Without an image result, text is weighted 0.50, category 0.20, location 0.15 and time 0.15. Missing location/time signals are omitted and the available component weights are normalised. These are ranking weights, not calibrated probabilities of ownership.

The report matching endpoint currently retrieves up to 500 of the most recently created available found-item records, scores them in application code and returns up to five ranked candidates. This explicit candidate limit helps bound a request but means the implementation is not a full-corpus search index.

### Optional pretrained models

| Model | Purpose | Enablement |
|---|---|---|
| <code>sentence-transformers/all-MiniLM-L6-v2</code> | Creates sentence embeddings to compare the semantic similarity of report text. | Install <code>requirements-ml.txt</code> and set <code>USE_SEMANTIC_MODEL=true</code>. |
| <code>openai/clip-vit-base-patch32</code> | Compares two item photos, or compares an available photo with the opposite report's text when only one image is present. | Install ML dependencies and set <code>USE_CLIP_MODEL=true</code>. |

Semantic embeddings are compared using cosine similarity. CLIP produces visual or image-text similarity features. If an optional model cannot load or inference fails, the matcher falls back to the deterministic text baseline or omits the unavailable image signal. Optional inference consumes additional memory and CPU/GPU resources; models should not be described as active unless their flags are enabled and loading has been verified.

Automatic image caption generation and keyword extraction are not implemented. CLIP similarity is not image captioning.

### Synthetic retrieval benchmark

The repository includes 15 manually labelled synthetic scenarios. Each scenario contains one relevant candidate and five distractors, for 90 candidate pairs.

A recorded development evaluation produced the following retrieval measurements:

| Metric | Lexical baseline | Sentence Transformers |
|---|---:|---:|
| Top-1 hit rate | 80.0% (12 of 15) | 93.3% (14 of 15) |
| Top-3 hit rate | 100% (15 of 15) | 100% (15 of 15) |
| Mean reciprocal rank | 0.8778 | 0.9667 |

These measurements are a small synthetic development check—not validated real-campus accuracy, a probability that a person owns an item, or a load test. The top-3 metric is already at the benchmark's ceiling. Before operational use, matching should be evaluated on a representative, privacy-reviewed labelled campus dataset with false positives, missed matches and top-k retrieval measured separately.

## Security and privacy

LostLink applies prototype-level controls to keep sensitive information out of public search and maintain a record of office actions.

### Authentication and authorisation
- Passwords are stored as PBKDF2-HMAC-SHA256 hashes with random salts and 180,000 iterations.
- Starlette session middleware signs session cookies, uses strict SameSite settings and an eight-hour maximum age.
- Failed login attempts are tracked by email and client address. Five invalid attempts within the configured window trigger a temporary lockout.
- Office operations are protected by server-side role checks; the frontend role selector is only a convenience for the local demo, not an identity provider.
- Set <code>SESSION_HTTPS_ONLY=true</code> when served over HTTPS. It remains false in the local example so localhost demo cookies work.

### Data minimisation and private fields
- Public/student report serialisation omits private Tag IDs, exact storage locations, private verification details and internal risk fields.
- Claim explanations and evidence are available only to the claimant and authorised office staff.
- Image routes are role-aware; sensitive categories have additional student-facing image restrictions.
- Student-facing photo responses are watermarked. Watermarks and disabled right-click/drag actions cannot prevent screenshots or access through browser developer tools, so they are deterrents rather than access controls.

### Image processing and duplicate detection
- Uploads are capped at 5 MB and must pass image validation.
- Images are orientation-corrected, resized and re-encoded as canonical JPEGs, removing embedded image metadata.
- Exact SHA-256 hashes and perceptual hashes help identify duplicate or near-duplicate photos.
- Private claim evidence is stored separately from public report metadata and served through authorised endpoints.

### Auditability
Intake, storage changes, claim decisions, handovers and reward events are written into application records. Unique event keys are used to make selected side effects such as notifications and reward awards idempotent.

These are prototype protections. A production system still requires a security review, HTTPS and deployment hardening, request-origin/CSRF review, managed secrets, access-controlled backups, retention policy, monitoring and a documented incident process.

## HTTP API reference

All API paths below are served by the FastAPI application. Endpoints that require a signed-in user need a valid session. Office actions additionally require the office role. Request payloads are validated using Pydantic models.

### Authentication and configuration

| Method | Path | Purpose |
|---|---|---|
| GET | <code>/</code> | Serve the application interface. |
| GET | <code>/api/config</code> | Return public configuration including category/location examples and demo settings. |
| POST | <code>/api/login</code> | Authenticate and start a session. |
| POST | <code>/api/logout</code> | End the current session. |
| GET | <code>/api/me</code> | Return the signed-in user's public account details. |

### Reports, photos and matching

| Method | Path | Purpose |
|---|---|---|
| GET | <code>/api/reports</code> | Search/list reports with supported filters. Student visibility is restricted to available found items except their own records; office visibility is wider. |
| POST | <code>/api/reports</code> | Create a lost or found report. |
| POST | <code>/api/reports/{report_id}/close</code> | Close an eligible owned lost report or withdraw a found report before intake. |
| POST | <code>/api/reports/{report_id}/image</code> | Upload or replace a permitted report image. |
| GET | <code>/api/reports/{report_id}/image</code> | Retrieve an image subject to role, status and category checks. |
| GET | <code>/api/reports/{report_id}/matches</code> | Rank up to five possible matches for an owned open lost report or an office user. |
| POST | <code>/api/reports/{report_id}/intake</code> | Office-only: confirm physical receipt, record storage/verification data and assign the Tag ID. |
| POST | <code>/api/reports/{report_id}/storage</code> | Office-only: update the item's recorded storage location. |

### Claims, evidence and handover

| Method | Path | Purpose |
|---|---|---|
| POST | <code>/api/claims</code> | Create a claim with a private explanation and evidence categories. |
| GET | <code>/api/claims</code> | List claims visible to the current user; office staff can review the office queue. |
| POST | <code>/api/claims/{claim_id}/evidence</code> | Update claim evidence text. |
| POST | <code>/api/claims/{claim_id}/evidence-image</code> | Upload private supporting evidence image. |
| GET | <code>/api/claims/{claim_id}/evidence-image</code> | Retrieve the evidence image subject to claimant/office access rules. |
| POST | <code>/api/claims/{claim_id}/dispute</code> | Submit an eligible claim review/dispute request. |
| POST | <code>/api/claims/{claim_id}/decision</code> | Office-only: request more evidence, approve, reject or mark disputed, with validation of required verification checks. |
| POST | <code>/api/claims/{claim_id}/handover</code> | Office-only: record physical handover after tag and identity confirmations. |

### Notifications, activity and rewards

| Method | Path | Purpose |
|---|---|---|
| GET | <code>/api/notifications</code> | List recent notifications and unread count for the signed-in user. |
| POST | <code>/api/notifications/{notification_id}/read</code> | Mark one owned notification read. |
| POST | <code>/api/notifications/read-all</code> | Mark the user's notifications read. |
| GET | <code>/api/activity/me</code> | Return the user's activity and verified contribution summary. |
| GET | <code>/api/leaderboard</code> | Return leaderboard information based on verified points. |
| GET | <code>/api/certificates/{certificate_id}/download</code> | Download an eligible milestone certificate PDF. |
| GET | <code>/api/office/summary</code> | Return the office dashboard summary. |

This is a route overview, not a replacement for endpoint schema validation. The authoritative request field limits and allowed values are defined in <code>app/schemas.py</code> and the route handlers.

## Technology stack

| Layer | Technology | Use |
|---|---|---|
| Application server | Python, FastAPI and Uvicorn | API routing and application hosting. |
| Request validation | Pydantic | Request payload validation and field length/range constraints. |
| Browser session | Starlette SessionMiddleware | Signed cookie-based sessions. |
| Database | SQLite and Python <code>sqlite3</code> | Prototype persistence, parameterised queries, foreign keys and transactions. |
| Password primitives | Python <code>hashlib</code> and <code>secrets</code> | PBKDF2 password hashing and constant-time verification comparison. |
| Image utilities | Pillow | Image verification, EXIF correction, resize/re-encoding and fingerprints. |
| PDF certificates | ReportLab | Generate downloadable milestone certificates. |
| Optional semantic model | Sentence Transformers | Text embeddings. |
| Optional visual model | Transformers, PyTorch and CLIP | Image-image or image-text similarity. |
| Frontend | HTML, CSS and vanilla JavaScript | Student and office workflows. |
| Testing and CI | Python unittest, Node.js syntax check and GitHub Actions | Workflow, matching, rewards, frontend contract and import checks. |

## Local installation

The documented launcher is for Windows PowerShell. Python 3.11 is used in CI.

### Windows PowerShell

Run these commands from the repository root.

1. Create a virtual environment and install runtime dependencies.

       py -3.11 -m venv .venv
       .\.venv\Scripts\Activate.ps1
       python -m pip install --upgrade pip
       python -m pip install -r requirements.txt

2. Create the local environment file if it does not already exist.

       Copy-Item .env.example .env

   If you already have a local <code>.env</code>, keep it rather than overwriting it.

3. Generate a unique session secret.

       python -c "import secrets; print(secrets.token_urlsafe(48))"

   Open <code>.env</code> with Notepad, replace the placeholder on the <code>SESSION_SECRET=</code> line with the generated value, save the file and close the editor. Do not commit the local <code>.env</code> file.

4. Start the single-server local demo.

       .\scripts\run-demo.ps1

The launcher checks the virtual-environment Python, verifies the secret, performs an import preflight, creates the local data directories and starts one Uvicorn process at <code>http://127.0.0.1:8000</code>. Keep the terminal open while using the application and press Ctrl+C to stop it. Stop any older local server that is occupying port 8000 before starting.

### Linux or macOS (manual run)

Create and activate a virtual environment, install dependencies, create the environment file and set a secret as described above. Then start the server manually:

       python3 -m venv .venv
       source .venv/bin/activate
       python -m pip install --upgrade pip
       python -m pip install -r requirements.txt
       cp .env.example .env
       python -c "import secrets; print(secrets.token_urlsafe(48))"
       python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

Before launching, edit <code>.env</code> and replace the placeholder session secret. If the file already exists, do not overwrite it. The PowerShell launcher is Windows-specific; on other platforms set the environment options in <code>.env</code> and run Uvicorn directly.

### Local-only demo accounts

When <code>DEMO_MODE=true</code>, startup creates demonstration users and sample records. The built-in demo accounts are intended for local development only:

| Role | Email | Password |
|---|---|---|
| Student | <code>student@lostlink.local</code> | <code>student123</code> |
| Office staff | <code>office@lostlink.local</code> | <code>office123</code> |

Use the in-app role-switching control to change between student and office views in the same browser session. Both roles operate against the same database. Reopen or revisit a view after switching to refresh its data. Do not use these credentials for a public deployment and do not expose the local development server to the public internet.

The prototype database defaults to <code>data/lostlink.db</code> and local images to <code>data/uploads/</code>. Those runtime files are excluded from Git.

## Configuration

Values are loaded from environment variables and the local <code>.env</code> file.

| Variable | Purpose | Example/default behaviour |
|---|---|---|
| <code>DEMO_MODE</code> | Seed demo accounts and sample records. | Example file sets <code>true</code>; set <code>false</code> outside local demonstrations. |
| <code>SESSION_SECRET</code> | Secret used to sign session cookies. | Required; startup rejects an empty or known placeholder value. Use a unique random secret. |
| <code>SESSION_HTTPS_ONLY</code> | Restrict session cookies to HTTPS. | <code>false</code> for localhost; set <code>true</code> for HTTPS deployment. |
| <code>DATABASE_PATH</code> | SQLite database file path. | Defaults to <code>data/lostlink.db</code>. |
| <code>UPLOAD_DIR</code> | Directory for uploaded report images and private claim evidence. | Defaults to <code>data/uploads</code>. |
| <code>USE_SEMANTIC_MODEL</code> | Enable semantic text embeddings. | <code>false</code> unless dependencies/model are installed and explicitly enabled. |
| <code>SEMANTIC_MODEL</code> | Sentence Transformers model identifier. | <code>sentence-transformers/all-MiniLM-L6-v2</code>. |
| <code>USE_CLIP_MODEL</code> | Enable CLIP-based image/image-text similarity. | <code>false</code> unless dependencies/model are installed and explicitly enabled. |
| <code>CLIP_MODEL</code> | CLIP model identifier. | <code>openai/clip-vit-base-patch32</code>. |

Keep secrets out of source control. The committed <code>.env.example</code> intentionally contains a placeholder and is not ready to use unchanged.

## Testing and matching evaluation

Install development dependencies:

       python -m pip install -r requirements-dev.txt

Run the automated checks from the repository root:

       python -m compileall -q app tests
       node --check app/static/app.js
       python -m unittest discover -s tests -v

The automated suite covers workflow behaviour, matching, rewards and frontend selector/navigation contracts. GitHub Actions runs Python compilation, JavaScript syntax validation, the unit/workflow tests and application import. A separate optional job attempts semantic-model evaluation; it is non-blocking because model downloads can fail in automated environments.

To run the deterministic baseline retrieval evaluation:

       python scripts/evaluate_matching.py

To request an evaluation using the actual Sentence Transformers model, install the optional model requirements and require the model to load:

       python -m pip install -r requirements-ml.txt
       python scripts/evaluate_matching.py --require-semantic-model

The benchmark is at <code>tests/data/matching_benchmark.json</code>. Its measurements are development data only and should not be represented as deployment accuracy.

## Limitations and production considerations

The current application is not a production deployment and has not been assigned a validated user-capacity or throughput claim.

- **Persistence:** SQLite is suitable for the prototype. If measured concurrent writes or operational needs require it, migrate to a managed database such as PostgreSQL and review connection management, query plans, transaction boundaries and uniqueness constraints.
- **File storage:** local images work for a single instance. Multiple instances would need shared, access-controlled object storage and a plan for private evidence retrieval.
- **Matching scale:** retrieval currently scores a bounded set of at most 500 available found records in application code. Larger collections may require better candidate pre-filtering, a search index, cached embeddings and a separate inference worker.
- **AI dependency:** optional model loading and image inference need memory/CPU/GPU planning. The default lexical mode should remain an explicit fallback.
- **Institutional identity:** the current app provides standalone login and student/office roles. Institutional SSO and automated college role provisioning are not implemented.
- **Security operations:** production requires HTTPS, secure secret management, a session/CSRF review, tested backups, data retention and deletion policy, monitoring, incident handling and a formal security review.
- **Data governance:** private evidence and custody information need an institution-approved retention/access policy. Demonstration data should not be real student data.
- **Matching validation:** test on a labelled, representative dataset and measure false matches and missed matches before using the system operationally.
- **Physical custody:** the database does not use sensors to determine where an object is. Staff must physically store the item and update its recorded location.
- **Image enrichment:** automatic image captioning and keyword generation are not implemented.

## Related documentation

- [Architecture.md](Architecture.md) — module boundaries, request flow and implementation invariants.

