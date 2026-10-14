# LostLink — Local Development Guide

This guide contains the setup, run, demo and test commands. Use a local development environment only; demo accounts and sample locations are not production credentials or an approved campus directory.

## Prerequisites

- Python 3.10 or later. **Python 3.12 is recommended on Windows** for the current dependency set; CI is tested with Python 3.11. Avoid creating the environment with an experimental/new Python version if a dependency has no compatible wheel.
- Git.
- A terminal: PowerShell on Windows, or a shell on macOS/Linux.
- Node.js is only needed to run the frontend JavaScript syntax check locally.

## 1. Get the repository

If you have not cloned it:

```bash
git clone https://github.com/tanmayjain9059/DejaVu.git
cd DejaVu
```

If the repository is already on your machine, open a terminal in the repository directory and pull the latest `main` branch before testing.

## 2. Create a virtual environment

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

If PowerShell activation is restricted by your device policy, use Command Prompt instead:

```bat
py -3.12 -m venv .venv
.\.venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
copy .env.example .env
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

## 3. Configure the local environment

Open `.env`. For a local evaluation, `.env.example` enables `DEMO_MODE=true` and uses non-production settings. Keep the server bound to localhost.

- **Required:** replace the `SESSION_SECRET` placeholder with a unique random value. The app now fails fast if it is empty or still set to the example placeholder. Generate one with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
- Keep `SESSION_HTTPS_ONLY=false` only for local HTTP development. Use HTTPS and secure cookies for an approved deployment.
- `DATABASE_PATH` and `UPLOAD_DIR` point to local `data/` paths by default.
- `USE_SEMANTIC_MODEL` and `USE_CLIP_MODEL` are both false by default.
- Login attempts are throttled by both email and client IP after 5 failed attempts within 15 minutes. A student can have at most 5 open claims at one time. The built-in deterministic baseline works without downloading model weights.

Do not expose a demo-mode server to the public internet.

## 4. Start LostLink

With the virtual environment activated:

```bash
python -m uvicorn app.main:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). Keep the terminal open while using the application. Stop the server with `Ctrl+C`.

## 5. Local demo accounts

These accounts are created only when `DEMO_MODE=true`:

| Role | Email | Password |
|---|---|---|
| Student | `student@lostlink.local` | `student123` |
| Office staff | `office@lostlink.local` | `office123` |

These credentials are for local demos only. Do not reuse them in any shared or production environment.

## 6. Suggested end-to-end demo

1. Sign in as the demo student and open the seeded lost-backpack report under **My reports**. Select **Find possible matches** to show candidates and their explanation signals.
2. As a student, submit a found-item report. Include brand, colour and a visible characteristic to demonstrate the optional details used by matching. Sign in as office staff and open **Found items awaiting intake**.
3. Confirm that the physical item is in office custody, enter the real location used in the demo (room, cabinet and/or shelf), complete the private verification details and sensitivity fields, then confirm intake. The app assigns a tag such as `LL-CVR-YYYY-000001`; the item becomes searchable only after this step.
4. In **Items currently in custody**, show the private Tag ID and storage location. Use **Update storage location** to demonstrate how an internal campus move is tracked in the audit trail.
5. As a student, submit a claim with private ownership evidence and optionally select the original open lost report from **Link to your lost report**. As office staff, review the risk-based checklist and verify the claim. It moves to **Ready for physical handover** but is not yet marked returned.
6. In the handover queue, retrieve the item from the recorded location, read the physical tag, enter the exact Tag ID and confirm identity check plus actual handover. A wrong tag must fail; a correct tag closes the claim and automatically closes any linked lost report.
7. Return to the student's **Notifications** and **Activity & certificates** views to show workflow updates, verified contribution points, personal leaderboard rank and any earned certificate.
8. Demonstrate closure controls: close an open lost report with a reason, or withdraw a found report only while it is still awaiting intake. Withdrawal after intake must be rejected.
9. As office staff, reject a test claim, then sign in as the claimant and submit one review request. Return to the office queue to show the appeal note and review the claim again.

The physical item and its location in a demo are illustrative. A screen action cannot physically transfer an item; the office operator must confirm only events that actually happened.

## 7. Optional pretrained matching models

The default matcher is a deterministic baseline. To enable optional pretrained features, activate the virtual environment and run:

```bash
pip install -r requirements-ml.txt
```

Then set the required flags in `.env` and restart the server:

- `USE_SEMANTIC_MODEL=true` enables Sentence Transformers text embeddings.
- `USE_CLIP_MODEL=true` enables optional CLIP-based image/text similarity.

The first model load can download weights and increase startup time, disk usage and memory consumption. If a model is unavailable or fails to load, the matcher may fall back to the baseline. Verify the model actually loaded before describing a demo as semantic/image-model based. Similarity is not a probability of ownership.

## 8. Run tests

Install the development dependencies:

```bash
pip install -r requirements-dev.txt
python -m compileall -q app tests
python -m unittest discover -s tests -v
# Includes frontend selector/HTML contract checks.
```

If Node.js is installed, also check the frontend script:

```bash
node --check app/static/app.js
```

GitHub Actions runs these checks on pushes and pull requests to `main`.

## 9. Reset local demo data

Stop the server first. Local SQLite and uploaded images live under `data/` by default and are ignored by Git. To reset the demo, back up anything you need and remove the local `data/` directory before starting again. When `DEMO_MODE=true`, the app recreates the sample records. Do not delete data directories for any real/shared deployment.

## Troubleshooting

- **`py` is not recognised:** Install Python and enable its PATH/launcher option, then reopen the terminal.
- **PowerShell cannot activate the environment:** Use the temporary process-level execution-policy command above or use Command Prompt's `activate.bat`.
- **Port 8000 is busy:** Stop the other process or start on another port, for example `python -m uvicorn app.main:app --reload --port 8001`, then open the matching local URL.
- **Photo upload fails:** Use a valid JPG, PNG or WebP file smaller than 5 MB.
- **The app says the claim has not been verified:** Office review, required verification checks, exact Tag ID entry, identity confirmation and physical handover are separate steps by design.

## Not yet available

This run guide starts the standalone prototype. It does not connect the application to Campus Sync, institutional single sign-on, a campus-owned production database or a live physical lost-property desk. Those require approval and integration details from the college/Campus Sync administrators.


## 10. Jury demo with two independent portals

Complete the virtual-environment setup above first, then run this from the repository root in PowerShell:

```powershell
.\scripts\run-jury-demo.ps1
```

It opens a student session at `http://localhost:8000` and an office session at `http://127.0.0.1:8001`. Both use the same local SQLite database and upload folder, but the separate hostnames keep the session cookies isolated. Leave both PowerShell windows running during the presentation.

| Role | Email | Password |
|---|---|---|
| Student 1 | `student@lostlink.local` | `student123` |
| Student 2 | `student2@lostlink.local` | `student2123` |
| Student 3 | `student3@lostlink.local` | `student3123` |
| Student 4 | `student4@lostlink.local` | `student4123` |
| Office staff | `office@lostlink.local` | `office123` |

Use distinct student accounts to demonstrate competing claims and notifications. The database is shared between both app processes so updates made in one portal are visible to the other after refresh. These are demo credentials; do not use them on a shared/public deployment.
