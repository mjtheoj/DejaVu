# LostLink — Campus Lost & Found

LostLink is a campus lost-property workflow designed to connect student reports with physical custody, staff-reviewed ownership claims and traceable handovers. It combines structured item reports, explainable candidate matching, private verification, a tag-based campus inventory and verified-contribution recognition.

## Solution approach

### One workflow from report to return

1. **Report:** Students submit lost or found reports with item details, approximate time/place and an optional photo. Reports are acknowledged and followed up through in-app notifications.
2. **Physical intake:** A found-item report remains outside public search until authorised office staff confirm physical receipt. Staff record the actual campus storage location, capture private identifying/verification details and assign a unique physical LostLink Tag ID.
3. **Campus storage register:** Office staff can look up tagged items by their private tag IDs and recorded room/cabinet/shelf location. If an item is moved within campus, staff update its location; the old and new location are included in the audit trail.
4. **Find possible matches:** Search and filtering help students discover available found items. Reports can include optional brand, primary colour and visible characteristics; these feed the deterministic match baseline along with description/category/date/location information. The service ranks candidates and explains available signals; a match is only a lead, never proof of ownership.
5. **Verify a claim:** A claimant submits private ownership evidence. Authorised staff review the evidence and risk-based checklist, check identity, and resolve competing claims before approving one. If a claim is rejected, the claimant can request one formal review with a reason; the appeal returns the claim to the office's disputed/review queue.
6. **Tag-based physical return:** An approved claim enters the handover queue but does not mark the item as returned. Staff retrieve the item from its recorded campus location, compare its physical tag with the exact Tag ID in the record, check the claimant's identity and confirm physical handover. A claim can optionally be linked to the student's open lost report. Incorrect tags and repeated handover attempts are rejected; a successful handover also closes the linked lost report automatically.
7. **Close the record:** The item and claim are marked returned, and the workflow creates an auditable handover record and sends in-app notifications. Students can close an open lost report or withdraw their own found report before office intake; once physical custody is accepted, withdrawal is blocked. Activity & Certificates also includes a leaderboard ranked by verified reward points without displaying emails or claim evidence.

The central rule is **no item is released solely because a match looks convincing**. Physical custody, an approved claim, identity checks and the exact recorded Tag ID are separate controls.

### Recognition for verified contributions

Rewards are attached to staff-confirmed events rather than raw form submissions: +10 points for a student-submitted found item after physical intake and tagging, and +5 points when a verified return is recorded. Idempotent event keys prevent duplicate awards. Milestone PDF certificates are available at 20, 50 and 100 points; prototype certificates explicitly state that they are not official college credentials.

### Privacy and accountability

Student-facing search does not expose private Tag IDs, storage locations, private ownership evidence, internal verification details, value/risk fields or raw matching scores. These details stay in the office workflow. Role checks protect office actions; item intake, storage changes, claim decisions, handovers and reward awards are audited. Uploaded images are validated and re-encoded to remove embedded metadata.

## Campus Sync integration direction

LostLink is being designed as a feature within the Campus Sync student experience, with Campus Sync serving as the entry point for students and the campus office workflow supporting custody and handovers. The repository currently contains a standalone prototype; **it is not yet connected to Campus Sync or the college identity system**.

The intended integration is to use college-approved institutional authentication and identity/role mapping, launch LostLink from Campus Sync (for example, through an approved embedded web view or application link), and host the API and item records in an environment approved by the college. The Campus Sync API/SDK, sign-in contract, deployment target and data-handling requirements must be confirmed before that integration can be implemented. See [Campus operations and integration](CAMPUS_OPERATIONS.md).

## Technology

| Layer | Technology and role |
|---|---|
| Application API | Python, FastAPI and Pydantic request validation |
| Prototype persistence | SQLite for reports, claims, private verification checks, notifications, storage records, handovers, reward ledger, certificates and audit events |
| User interface | HTML, CSS and vanilla JavaScript; role-specific student and office views |
| Image handling | Pillow validation, orientation correction and re-encoding |
| Matching | Deterministic text/category/date/location baseline; optional Sentence Transformers semantic text embeddings and CLIP image/text similarity |
| Recognition | ReportLab-generated milestone PDF certificates |
| Quality checks | Python unit/workflow tests, JavaScript syntax check and GitHub Actions CI |

The default matcher is a lightweight, reproducible baseline. Pretrained semantic/image models are optional and must be explicitly installed and enabled. Similarity scores are not ownership probabilities, and model-based accuracy should not be claimed without evaluation against labelled campus data.

SQLite and local file storage are suitable for prototype evaluation, not a claim of production readiness. A Campus Sync deployment should use college-approved hosting, institutional authentication, managed backups and retention rules, secure image/object storage, monitoring and a reviewed database/concurrency design.

## Project documentation

- [Round 1 jury overview](ROUND_1_JURY.md) — detailed solution narrative, architecture, Mermaid flowcharts, demo plan and jury Q&A.
- [Local development and run commands](LOCAL_DEVELOPMENT.md) — installation, environment, demo access, optional models and tests.
- [Campus operations and integration](CAMPUS_OPERATIONS.md) — item custody, Tag ID returns, staff procedure and Campus Sync integration prerequisites.


## Jury demo: student and office portals side by side

After installing dependencies in `.venv`, run this from the repository root in PowerShell:

```powershell
.\scripts\run-jury-demo.ps1
```

The script opens two local instances backed by the same demo SQLite database: the student portal at `http://localhost:8000` and the office portal at `http://127.0.0.1:8001`. The distinct hostnames keep the browser's session cookies separate while both portals see the same reports and claim workflow. Keep both terminal windows open. Stop each server with `Ctrl+C`.

Demo-only accounts:

| Role | Email | Password |
|---|---|---|
| Student 1 | `student@lostlink.local` | `student123` |
| Student 2 | `student2@lostlink.local` | `student2123` |
| Student 3 | `student3@lostlink.local` | `student3123` |
| Student 4 | `student4@lostlink.local` | `student4123` |
| Office | `office@lostlink.local` | `office123` |

This is a local jury demonstration, not a production deployment. Do not expose the ports to the public internet. The prototype watermarks public photo previews and blocks exact/near-duplicate report/evidence images; browsers cannot be made completely incapable of saving or screenshotting displayed images.
