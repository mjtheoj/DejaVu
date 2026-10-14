# LostLink — AI-Assisted Campus Lost & Found

LostLink turns scattered lost-and-found posts into a traceable recovery workflow. Students report items and discover possible matches; authorised campus-office staff record physical custody, verify claims and confirm the final handover using the exact physical Tag ID.

**Core principle:** a submitted form or a high matching score is not proof of ownership. An item is returned only after the office verification process and recorded physical handover.

[Watch the 90-second jury demo](https://share.videomagic.ai/H8Kcs) · [Technical architecture](Architecture.md) · [Round 1 jury overview and Q&A](ROUND_1_JURY.md)

## The problem and the solution

Lost property is usually reported through disconnected chats, notices and informal desks. Descriptions can be vague, a genuine owner may never see the post, and a submitted claim does not establish ownership or physical return.

LostLink combines structured reporting, explainable candidate matching, private ownership evidence, office-controlled intake and storage, a unique Tag ID, a handover record and verified-contribution recognition.

## What is implemented

### Student workflow
- Submit lost-item and found-item reports with title, description, category, approximate date/time and campus location; brand, colour, visible features and a photo can add detail.
- Search and filter available found items by text, category, block/area, room and date.
- View item details and explainable possible-match suggestions.
- Receive in-app report and possible-match notifications.
- Submit private ownership evidence, track the claim status, respond to requests for more evidence and request a formal review after rejection.
- View activity, verified reward points, leaderboard standing and prototype milestone certificates.

### Authorised office workflow
- Confirm that a found item has physically arrived before it becomes publicly searchable.
- Record its actual storage location and private verification details, then assign a unique LostLink Tag ID.
- Update storage locations with audit history.
- Review private claim evidence, run the risk-based verification checklist, request further evidence, reject, approve or dispute a claim.
- Retrieve the item from its recorded location and confirm the exact physical Tag ID, claimant identity and actual handover.
- View notifications and office summaries; record the handover and its audit event.

### Privacy and accountability controls
- Public/student responses omit private Tag IDs, storage locations, ownership clues, internal verification details and private claim evidence.
- Office-only operations are protected by server-side role checks.
- Uploaded images are validated, orientation-corrected and re-encoded; embedded image metadata is removed.
- Exact SHA-256 and perceptual image fingerprints help reject duplicated or near-duplicate uploaded photos. This is a deterrent, not a guarantee against screenshots or transformed images.
- Login failures are tracked and temporarily locked after repeated invalid attempts. Session cookies use strict SameSite settings and an eight-hour lifetime; HTTPS-only cookies can be enabled for deployment.
- Audit events track important intake, storage, claim and handover actions. Unique event keys help prevent duplicate notifications and reward awards.

## End-to-end workflow

    Student reports lost item ───────────────┐
                                            ▼
    Student reports found item ──► Office confirms physical receipt
                                            │
                                            ▼
                              Record private details and real location
                                            │
                                            ▼
                                  Assign physical LostLink Tag ID
                                            │
                                            ▼
                                  Item becomes available for search
                                            │
                                            ▼
                                  Rank possible matches and notify
                                            │
                                            ▼
                                   Student submits private evidence
                                            │
                                            ▼
                                    Office verifies claim and identity
                                            │
                                ┌───────────┴───────────┐
                                ▼                       ▼
                         More evidence /             Approved
                           dispute                    claim
                                                        │
                                                        ▼
                                     Retrieve item and check exact Tag ID
                                                        │
                                                        ▼
                                      Confirm physical handover and audit

A found-item report starts in **Awaiting office intake** and is hidden from student search. Only after staff confirm receipt, record custody and tag the object can it enter the available-found inventory. Claim approval and physical handover are separate states.

## Architecture

    ┌──────────────────────────────────────────────────────────┐
    │                         Client                           │
    │               Student UI / Office UI                     │
    │                 HTML + CSS + JavaScript                  │
    └──────────────────────────┬───────────────────────────────┘
                               │ HTTP requests
                               ▼
    ┌──────────────────────────────────────────────────────────┐
    │                    FastAPI application                   │
    │  Session authentication and server-side role checks      │
    │  ├─ Auth routes                                          │
    │  ├─ Reports, images, intake and storage routes            │
    │  ├─ Claims, evidence, decisions, disputes and handover    │
    │  ├─ Notifications, activity, rewards and certificates     │
    │  ├─ Explainable matching engine                           │
    │  └─ Report, notification and reward services              │
    └──────────────────────────┬───────────────────────────────┘
                               │
                ┌──────────────┴─────────────┐
                ▼                            ▼
    ┌──────────────────────┐    ┌─────────────────────────────┐
    │ SQLite database      │    │ Local image storage         │
    │ users and reports    │    │ validated/re-encoded photos │
    │ claims and evidence  │    │ private claim evidence      │
    │ Tag IDs and handovers│    └─────────────────────────────┘
    │ notifications/rewards│
    │ audit events         │
    └──────────────────────┘

### Code structure

| Path | Responsibility |
|---|---|
| <code>app/main.py</code> | Creates FastAPI app, configures sessions/static files, registers routers and initialises the database |
| <code>app/api/routes/auth.py</code> | Login, logout, current session and app configuration |
| <code>app/api/routes/reports.py</code> | Report creation/search/closure, photos, match lookup, office intake and storage updates |
| <code>app/api/routes/claims.py</code> | Claims, private evidence, decisions, disputes and physical handover |
| <code>app/api/routes/engagement.py</code> | Notifications, activity, leaderboard, office summary and PDF certificates |
| <code>app/core/database.py</code> | SQLite schema, migrations, transaction lifecycle, audit events and demo seed data |
| <code>app/core/images.py</code> | Image validation, canonicalisation, fingerprints and watermarked previews |
| <code>app/core/security.py</code> | Password hashing and verification |
| <code>app/matching.py</code> | Candidate scoring, optional semantic/image similarity and match explanations |
| <code>app/services/</code> | Report serialisation, notification logic and verified reward/certificate logic |
| <code>app/static/</code> | Student/office interface, JavaScript and styling |
| <code>scripts/run-jury-demo.ps1</code> | Single-terminal Windows demo launcher |
| <code>scripts/evaluate_matching.py</code> | Labelled synthetic retrieval benchmark runner |
| <code>tests/</code> | Matching, workflow, rewards and frontend-contract tests |

See [Architecture.md](Architecture.md) for module boundaries, API ownership and invariants.

## Matching engine and AI models

LostLink is **AI-assisted, not AI-dependent**. The default matching path is a deterministic lexical baseline and does not require a model download or external inference API.

- **Lexical baseline:** normalises tokens and synonyms, then combines Jaccard overlap, Python’s <code>difflib.SequenceMatcher</code> and overlap on distinguishing terms.
- **Structured context:** compares category, location (block/floor/room/area) and reported time when those fields are available.
- **Optional semantic text model:** <code>sentence-transformers/all-MiniLM-L6-v2</code>, enabled with <code>USE_SEMANTIC_MODEL=true</code> after installing <code>requirements-ml.txt</code>.
- **Optional visual model:** <code>openai/clip-vit-base-patch32</code>, enabled with <code>USE_CLIP_MODEL=true</code> and its Transformers/PyTorch dependencies installed. It can compare two images or compare an image to a report description when one photo is absent.

Both pretrained models are optional and disabled by default. If semantic or image inference is unavailable, LostLink can fall back to the lexical baseline. The match endpoint considers up to 500 currently available found-item candidates and returns up to five ranked suggestions; this bound is a current implementation detail, not an unlimited retrieval guarantee.

### Matching evaluation

The repository includes 15 manually labelled **synthetic** scenarios, each with one relevant candidate and five distractors (90 candidate pairs total). A recorded development run reported:

| Metric | Lexical baseline | Sentence Transformers |
|---|---:|---:|
| Top-1 hit rate | 80.0% (12/15) | 93.3% (14/15) |
| Top-3 hit rate | 100% (15/15) | 100% (15/15) |
| Mean reciprocal rank | 0.8778 | 0.9667 |

These are small synthetic retrieval checks, not real-campus accuracy, ownership probabilities or load-test results. Top-3 is already at the benchmark ceiling, so the semantic model did not improve that particular metric. Real deployment needs a representative, privacy-reviewed labelled campus dataset and measurement of false suggestions and missed matches.

## Technology stack

| Layer | Technology |
|---|---|
| API and application | Python, FastAPI, Uvicorn, Pydantic |
| Session middleware | Starlette SessionMiddleware |
| Prototype database | SQLite / Python <code>sqlite3</code> |
| Images | Pillow |
| Certificates | ReportLab |
| Optional semantic matching | Sentence Transformers |
| Optional image matching | Transformers, PyTorch and CLIP |
| Frontend | HTML, CSS, vanilla JavaScript |
| Quality checks | Python unittest, Node.js syntax check and GitHub Actions |

## Run the jury demo on Windows

The recommended evaluation mode is **one terminal, one server and one shared SQLite database**. Do not start separate student and office servers.

### 1. Create the environment and install dependencies

From the repository root in PowerShell:

    py -3.11 -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    Copy-Item .env.example .env

### 2. Set a real session secret

Generate a unique secret:

    python -c "import secrets; print(secrets.token_urlsafe(48))"

Open the local environment file:

    notepad .env

Replace the placeholder value on the <code>SESSION_SECRET=</code> line with the generated value, then save the file. Never commit <code>.env</code> or share its secret.

### 3. Start the demo

    .\scripts\run-jury-demo.ps1

The launcher checks the environment, runs an application import preflight, starts one Uvicorn process and opens [http://127.0.0.1:8000](http://127.0.0.1:8000). Keep the terminal open; press **Ctrl+C** to stop the server. If another server is already using port 8000, stop it before starting the demo.

Demo-only accounts:

| Role | Email | Password |
|---|---|---|
| Student | <code>student@lostlink.local</code> | <code>student123</code> |
| Office staff | <code>office@lostlink.local</code> | <code>office123</code> |

Use the in-app **Switch to office** / **Switch to student** control to change roles within the same browser session. Reopen or revisit the target view after switching so it fetches the latest state. The demo database persists at <code>data/lostlink.db</code> between runs; keep or reset local demo data deliberately. These credentials are for local demonstrations only. Do not expose this development server to the public internet.

## Tests and evaluation commands

Install test dependencies:

    python -m pip install -r requirements-dev.txt

Run the automated tests and source checks:

    python -m compileall -q app tests
    node --check app/static/app.js
    python -m unittest discover -s tests -v

Run the matching benchmark with the lightweight baseline:

    python scripts/evaluate_matching.py

To test the optional semantic model, install its dependencies first:

    python -m pip install -r requirements-ml.txt
    $env:SEMANTIC_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
    python scripts/evaluate_matching.py --require-semantic-model

The GitHub Actions workflow compiles Python, checks JavaScript syntax, runs the test suite and imports the application. Its optional matching job attempts to load the semantic model and is marked non-blocking because external model downloads may fail in CI environments.

## Current limitations and production work

LostLink is a **working standalone prototype**, not a production deployment. No campus-wide user capacity, uptime or request-throughput claim has been established.

Before a real institutional rollout:
- Replace local SQLite with an appropriately managed database such as PostgreSQL if measured concurrent writes and operational needs require it.
- Move images from local filesystem storage to access-controlled shared/object storage when deploying more than one application instance.
- Add managed backups, restore testing, monitoring, retention policy and incident procedures.
- Complete a security review of sessions, request protections, upload handling, access control, logs and institutional identity.
- Load-test realistic concurrent report, search, claim and handover workloads.
- Evaluate the matching engine on representative labelled campus data.
- Keep physical receipt, private evidence review, claimant identity checks and exact Tag ID handover as mandatory operational controls.

Automatic image captioning and keyword extraction are **not implemented**. CLIP similarity is not image captioning, and generated matching scores do not establish ownership.

## Repository documents

- [Architecture.md](Architecture.md) — technical module map and architecture boundaries.
- [ROUND_1_JURY.md](ROUND_1_JURY.md) — jury narrative, workflow diagrams, demo plan, pitch and likely questions.
