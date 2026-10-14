# DejaVu · LostLink

LostLink is a focused campus lost-and-found prototype for the first five Campus Solve outcomes: structured lost/found reports, optional photos, search and filters, AI-assisted candidate ranking, and explanations. It also includes office-side physical intake, internal tag assignment, and claim verification so the first five outcomes can be demonstrated against a realistic workflow.

This is a standalone prototype. It is not connected to the official CVR College of Engineering Android app or its identity system.

## Scope in this version

- Student: submit lost/found reports, optionally attach an image, search office-held found items, see possible matches for their own lost reports, submit private claims, and see their claim status.
- Office: confirm physical receipt of a found item, assign a physical tag ID, record private verification information and risk inputs, and approve, reject, dispute, or request more evidence for claims.
- Privacy boundary: students receive public references, a public item description and a status. Physical tag IDs, private verification details, value bands, sensitivity levels, verification levels and claim evidence are only returned to the authorised office role. Claimants can see their own claim status but not the office's private notes.
- The app stops at the verification decision. It does not record physical collection, send notifications, integrate with Campus Sync, or connect to college login.

## Run locally

Python 3.10 or later is recommended.

1. Create and activate a virtual environment.
2. Install dependencies: pip install -r requirements.txt
3. Copy .env.example to .env.
4. Start the app from the repository root: python -m uvicorn app.main:app --reload
5. Open http://127.0.0.1:8000.

On Windows PowerShell, the usual setup commands are:

    py -m venv .venv
    .venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    Copy-Item .env.example .env
    python -m uvicorn app.main:app --reload

When DEMO_MODE=true, the local app seeds sample records and these demo accounts:

- Student: student@lostlink.local / student123
- Office: office@lostlink.local / office123

Demo credentials are for local evaluation only. Do not expose a demo-mode server to the public internet. Set a strong random session secret before any shared deployment. For a real campus launch, replace the demo login with an approved authentication integration and review all access controls.

SQLite data and uploaded, metadata-stripped JPEG images are stored under the local data/ directory. That directory is ignored by Git.

## Matching behaviour

The default mode uses a deterministic text baseline with category, location and date signals. It is useful for local development and a comparison baseline, but it is not a learned semantic model. The explanation is generated from the actual signals used by the ranker. Similarity scores are never treated as ownership proof.

For semantic text embeddings and optional image/text similarity, install the additional model dependencies:

    pip install -r requirements-ml.txt

Then set USE_SEMANTIC_MODEL=true and/or USE_CLIP_MODEL=true in .env. The first model load may download pretrained weights and can require significant disk space, RAM and startup time. If a model is unavailable, the matcher falls back to the lightweight text baseline; verify which mode actually loaded before presenting results as model-based. Photo uploads remain optional in every mode.

## Verification policy

The office sets private category/risk information at physical intake. The effective level is raised by the configured category default, high estimated value, and sensitivity level. The exact thresholds are an initial prototype policy and must be approved by the college before production use. Conflicting claims must be resolved before approval. AI ranking does not approve ownership automatically.

Found reports remain hidden from the public browse list until office staff confirm physical receipt and assign a tag. The physical tag ID is an internal inventory identifier, not proof of ownership. Sensitive categories have limited public location/image disclosure.

## Tests

Run the matching unit tests with:

    python -m unittest discover -s tests

## Before any real deployment

- Replace sample blocks/floors with the verified campus directory.
- Integrate an approved college authentication method.
- Review privacy, retention, image access, session handling and office permissions.
- Configure HTTPS, a strong session secret, backups and operational logging.
- Add rate limits, CSRF protection appropriate to the deployment, and institutional policy for restricted items.
- Evaluate matching on a labelled local dataset; never publish unmeasured accuracy claims.
- Add notifications and physical handover only through the team's agreed API contracts.
