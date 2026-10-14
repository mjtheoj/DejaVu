"""HTTP route group."""
from fastapi import APIRouter
from app.core.runtime import *
from app.schemas import *

router = APIRouter()

@router.get("/api/reports")
async def list_reports(
    report_type: str | None = None,
    category: str | None = None,
    block: str | None = None,
    room: str | None = None,
    q: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    status: str | None = None,
    mine: bool = False,
    user: dict[str, Any] = Depends(authenticated_user),
):
    conditions: list[str] = []
    params: list[Any] = []
    internal = user["role"] == "office"

    if not internal and mine:
        conditions.append("r.created_by=?")
        params.append(user["id"])
    elif not internal:
        conditions.extend(["r.report_type='found'", "r.status='available'"])
    elif mine:
        conditions.append("r.created_by=?")
        params.append(user["id"])

    if report_type in {"lost", "found"}:
        conditions.append("r.report_type=?")
        params.append(report_type)
    if category in CATEGORY_LABELS:
        conditions.append("r.category=?")
        params.append(category)
    if block:
        conditions.append("LOWER(COALESCE(r.location_block,'')) LIKE ?")
        params.append("%" + block.lower() + "%")
    if room:
        conditions.append("LOWER(COALESCE(r.location_room,'')) LIKE ?")
        params.append("%" + room.lower() + "%")
    if q:
        term = "%" + q.strip().lower() + "%"
        conditions.append("""(
            LOWER(r.title) LIKE ? OR LOWER(r.description) LIKE ? OR LOWER(r.public_ref) LIKE ?
            OR LOWER(COALESCE(r.location_area,'')) LIKE ? OR LOWER(COALESCE(r.brand,'')) LIKE ?
            OR LOWER(COALESCE(r.primary_color,'')) LIKE ? OR LOWER(COALESCE(r.visible_features,'')) LIKE ?
            OR LOWER(COALESCE(r.location_block,'')) LIKE ? OR LOWER(COALESCE(r.location_floor,'')) LIKE ?
            OR LOWER(COALESCE(r.location_room,'')) LIKE ?
        )""")
        params.extend([term] * 10)
    if date_from:
        conditions.append("COALESCE(r.occurred_at,'') >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("COALESCE(r.occurred_at,'') <= ?")
        params.append(date_to + "T23:59:59")
    if internal and status:
        conditions.append("r.status=?")
        params.append(status)

    sql = "SELECT r.* FROM reports r"
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY r.created_at DESC LIMIT 250"
    with connect_db() as conn:
        rows = conn.execute(sql, params).fetchall()
        reports = []
        for row in rows:
            report_data = serialise_report(row, internal=internal)
            if row["report_type"] == "lost" and int(row["created_by"]) == int(user["id"]):
                active_claim = conn.execute(
                    """SELECT 1 FROM claims WHERE lost_report_id=?
                       AND status IN ('pending','disputed','needs_more_evidence','approved_for_collection') LIMIT 1""",
                    (row["id"],),
                ).fetchone()
                report_data["has_active_linked_claim"] = active_claim is not None
            reports.append(report_data)
    return {"reports": reports}


@router.post("/api/reports")
async def create_report(body: ReportBody, user: dict[str, Any] = Depends(authenticated_user)):
    if len(body.title.strip()) < 4:
        raise HTTPException(status_code=422, detail="Enter an item name of at least 4 characters.")
    if len(body.description.strip()) < 10:
        raise HTTPException(status_code=422, detail="Add at least 10 characters describing the item.")
    if body.occurred_at:
        try:
            datetime.fromisoformat(body.occurred_at.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=422, detail="Use a valid ISO date and time, or leave the date blank if unknown.")
    if body.category not in CATEGORY_LABELS:
        raise HTTPException(status_code=422, detail="Choose a valid item category.")
    if not (body.location_block or body.location_area):
        raise HTTPException(status_code=422, detail="Choose a campus block or area.")
    report_id = uuid.uuid4().hex
    public_ref = new_public_ref()
    timestamp = now_iso()
    status = "open" if body.report_type == "lost" else "awaiting_intake"
    with connect_db() as conn:
        conn.execute(
            """INSERT INTO reports(id, public_ref, report_type, title, description, brand, primary_color,
               visible_features, category, occurred_at, location_block, location_floor, location_room,
               location_area, status, created_by, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (report_id, public_ref, body.report_type, body.title.strip(), body.description.strip(),
             (body.brand or "").strip() or None, (body.primary_color or "").strip() or None,
             (body.visible_features or "").strip() or None, body.category, body.occurred_at,
             body.location_block, body.location_floor, body.location_room, body.location_area,
             status, user["id"], timestamp, timestamp),
        )
        audit(conn, user["id"], "report_created", "report", report_id, {"report_type": body.report_type})
        if body.report_type == "found":
            notify_role(conn, "office", "found-report:" + report_id, "Found-item report awaiting intake",
                        "A new found-item report is waiting for physical office intake.", "report", report_id)
            notify_user(conn, user["id"], "report-created:" + report_id, "Found report submitted",
                        "Your found-item report is waiting for the office to confirm physical receipt.", "report", report_id)
        else:
            notify_user(conn, user["id"], "report-created:" + report_id, "Lost report submitted",
                        "Your lost-item report is saved. LostLink can suggest possible matches as found items are received.", "report", report_id)
            notify_matches_for_lost_report(conn, read_report(conn, report_id))
        row = read_report(conn, report_id)
    return {"report": serialise_report(row, internal=user["role"] == "office"),
            "message": "Lost report submitted." if body.report_type == "lost" else "Found-item report submitted for office intake. It will become searchable after staff confirm receipt."}


@router.post("/api/reports/{report_id}/close")
async def close_report(
    report_id: str,
    body: ReportCloseBody,
    user: dict[str, Any] = Depends(authenticated_user),
):
    if user["role"] != "student":
        raise HTTPException(status_code=403, detail="Only the report owner can close their report.")
    with connect_db() as conn:
        report = read_report(conn, report_id)
        if report["created_by"] != user["id"]:
            raise HTTPException(status_code=404, detail="Report not found.")
        if report["report_type"] == "lost" and report["status"] == "open":
            linked_active_claim = conn.execute(
                """SELECT 1 FROM claims WHERE lost_report_id=?
                   AND status IN ('pending','disputed','needs_more_evidence','approved_for_collection') LIMIT 1""",
                (report_id,),
            ).fetchone()
            if linked_active_claim:
                raise HTTPException(
                    status_code=409,
                    detail="This lost report is linked to a claim under review. Resolve that claim before closing the report."
                )
            if body.reason == "found_report_withdrawn":
                raise HTTPException(status_code=422, detail="Choose a reason for closing your lost-item search.")
            final_status = "closed"
            title = "Lost report closed"
            message = "Your lost report has been closed. It will no longer generate match suggestions, and its history remains visible in My Reports."
        elif report["report_type"] == "found" and report["status"] == "awaiting_intake":
            if body.reason != "found_report_withdrawn":
                raise HTTPException(status_code=422, detail="A found report can only be withdrawn before office intake.")
            final_status = "cancelled"
            title = "Found report withdrawn"
            message = "Your found report was withdrawn before the campus office accepted physical custody."
        else:
            raise HTTPException(status_code=409, detail="Only an open lost report or a found report awaiting office intake can be closed.")
        timestamp = now_iso()
        conn.execute(
            "UPDATE reports SET status=?, closure_reason=?, closure_note=?, updated_at=? WHERE id=?",
            (final_status, body.reason, (body.note or "").strip() or None, timestamp, report_id),
        )
        audit(conn, user["id"], "report_closed_or_withdrawn", "report", report_id,
              {"report_type": report["report_type"], "status": final_status,
               "reason": body.reason, "note": (body.note or "").strip() or None})
        notify_user(conn, user["id"], "report-closed:" + report_id, title, message, "report", report_id)
        if report["report_type"] == "found":
            notify_role(conn, "office", "found-report-withdrawn:" + report_id,
                        "Found report withdrawn before intake",
                        "A student withdrew a found-item report before the physical item was accepted into campus custody.",
                        "report", report_id)
        updated = read_report(conn, report_id)
    return {"report": serialise_report(updated), "message": title + "."}


@router.post("/api/reports/{report_id}/image")
async def upload_report_image(
    report_id: str,
    file: UploadFile = File(...),
    user: dict[str, Any] = Depends(authenticated_user),
):
    with connect_db() as conn:
        row = read_report(conn, report_id)
        is_office = user["role"] == "office"
        if not is_office and row["created_by"] != user["id"]:
            raise HTTPException(status_code=403, detail="You cannot update this report.")
        if not is_office and row["report_type"] == "found" and row["status"] != "awaiting_intake":
            raise HTTPException(status_code=409, detail="A found item's photo can only be changed before office intake.")
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Images must be 5 MB or smaller.")
    normalized, image_sha256, image_phash = canonicalise_image(raw)
    filename = uuid.uuid4().hex + ".jpg"
    (UPLOAD_DIR / filename).write_bytes(normalized)
    with connect_db() as conn:
        row = read_report(conn, report_id)
        old = row["image_path"]
        conn.execute(
            "UPDATE reports SET image_path=?, image_sha256=?, image_phash=?, updated_at=? WHERE id=?",
            (filename, image_sha256, image_phash, now_iso(), report_id),
        )
        audit(conn, user["id"], "report_image_added", "report", report_id)
        if old:
            try:
                (UPLOAD_DIR / old).unlink(missing_ok=True)
            except OSError:
                pass
        updated = read_report(conn, report_id)
    return {"report": serialise_report(updated, internal=user["role"] == "office")}


@router.get("/api/reports/{report_id}/image")
async def get_report_image(report_id: str, user: dict[str, Any] = Depends(authenticated_user)):
    with connect_db() as conn:
        row = read_report(conn, report_id)
    if not row["image_path"]:
        raise HTTPException(status_code=404, detail="No image is available.")
    if user["role"] != "office":
        if not report_visible_to_student(row, user):
            raise HTTPException(status_code=404, detail="Image not available.")
        if row["category"] in SENSITIVE_CATEGORIES:
            raise HTTPException(status_code=404, detail="Images of sensitive items are restricted.")
    path = (UPLOAD_DIR / row["image_path"]).resolve()
    if path.parent != UPLOAD_DIR.resolve() or not path.is_file():
        raise HTTPException(status_code=404, detail="Image not found.")
    headers = {
        "Cache-Control": "private, no-store",
        "Content-Disposition": "inline",
        "X-Content-Type-Options": "nosniff",
    }
    if user["role"] != "office":
        return StreamingResponse(BytesIO(watermark_image(path, row["public_ref"])),
                                 media_type="image/jpeg", headers=headers)
    return FileResponse(path, media_type="image/jpeg", headers=headers)


@router.get("/api/reports/{report_id}/matches")
async def get_matches(report_id: str, user: dict[str, Any] = Depends(authenticated_user)):
    from app.matching import matching_engine

    with connect_db() as conn:
        lost = read_report(conn, report_id)
        if lost["report_type"] != "lost":
            raise HTTPException(status_code=400, detail="Matches are generated from a lost-item report.")
        if lost["status"] != "open":
            raise HTTPException(status_code=409, detail="Only an open lost report can be matched.")
        if user["role"] != "office" and lost["created_by"] != user["id"]:
            raise HTTPException(status_code=403, detail="You can only view matches for your own lost reports.")
        candidates = conn.execute(
            "SELECT * FROM reports WHERE report_type='found' AND status='available' ORDER BY created_at DESC LIMIT 500"
        ).fetchall()
    lost_for_matching = dict(lost)
    if lost_for_matching.get("image_path"):
        lost_for_matching["image_path"] = str(UPLOAD_DIR / lost_for_matching["image_path"])
    candidate_data = []
    for candidate in candidates:
        candidate_item = dict(candidate)
        if candidate_item.get("image_path"):
            candidate_item["image_path"] = str(UPLOAD_DIR / candidate_item["image_path"])
        candidate_data.append(candidate_item)
    ranked = matching_engine.rank(lost_for_matching, candidate_data, limit=5)
    internal = user["role"] == "office"
    results = []
    for match in ranked:
        item = serialise_report(next(row for row in candidates if row["id"] == match["report"]["id"]), internal=internal)
        entry = {"report": item, "strength": match["strength"], "reasons": match["reasons"]}
        if internal:
            entry["internal_score"] = match["score"]
            entry["signals"] = match["signals"]
            entry["matching_engine"] = match["engine"]
        results.append(entry)
    return {"matches": results, "note": "Suggestions support discovery only; they do not establish ownership."}


@router.post("/api/reports/{report_id}/intake")
async def intake_found_item(
    report_id: str,
    body: IntakeBody,
    user: dict[str, Any] = Depends(authenticated_user),
):
    require_office(user)
    if not body.confirmed_physical_receipt:
        raise HTTPException(status_code=422, detail="Confirm that the physical item has been received by the office.")
    storage_location = body.storage_location.strip()
    if len(storage_location) < 4:
        raise HTTPException(status_code=422, detail="Record the actual campus room, cabinet, shelf or other storage location.")
    with connect_db() as conn:
        row = read_report(conn, report_id)
        if row["report_type"] != "found" or row["status"] != "awaiting_intake":
            raise HTTPException(status_code=409, detail="Only found-item reports awaiting intake can be accepted.")
        level = effective_level(row["category"], body.value_band, body.sensitivity_level)
        detail_length = len((body.private_detail or "").strip())
        minimum_detail = 8 if level >= 3 else (6 if level >= 2 else 0)
        if detail_length < minimum_detail:
            raise HTTPException(status_code=422, detail="For this risk level, record a private identifying detail or the approved verification method.")
        year = datetime.now().year
        prefix = "LL-CVR-" + str(year) + "-"
        latest = conn.execute("SELECT tag_id FROM reports WHERE tag_id LIKE ? ORDER BY tag_id DESC LIMIT 1", (prefix + "%",)).fetchone()
        number = int(latest["tag_id"].rsplit("-", 1)[1]) + 1 if latest else 1
        tag_id = prefix + str(number).zfill(6)
        conn.execute(
            """UPDATE reports SET status='available', tag_id=?, storage_location=?, private_detail=?, value_band=?,
               sensitivity_level=?, verification_level=?, updated_at=? WHERE id=?""",
            (tag_id, storage_location, (body.private_detail or "").strip() or None, body.value_band,
             body.sensitivity_level, level, now_iso(), report_id),
        )
        audit(conn, user["id"], "found_item_received_tagged_and_stored", "report", report_id,
              {"tag_id": tag_id, "storage_location": storage_location, "verification_level": "L" + str(level)})
        notify_user(
            conn, row["created_by"], "found-intake:" + report_id,
            "Found item received and stored",
            "Campus office confirmed physical receipt and storage of the item. It is now available for matching.",
            "report", report_id,
        )
        reporter = conn.execute("SELECT role FROM users WHERE id=?", (row["created_by"],)).fetchone()
        if reporter and reporter["role"] == "student":
            award_points(
                conn, row["created_by"], POINT_RULES["verified_intake"],
                "verified-intake:" + report_id,
                "Your found-item report was physically received and verified by the campus office",
                report_id, user["id"]
            )
        notify_possible_matches(conn, read_report(conn, report_id))
        updated = read_report(conn, report_id)
    return {"report": serialise_report(updated, internal=True), "message": "Physical receipt recorded, tag assigned and campus storage location saved."}


@router.post("/api/reports/{report_id}/storage")
async def update_storage_location(
    report_id: str,
    body: StorageLocationBody,
    user: dict[str, Any] = Depends(authenticated_user),
):
    require_office(user)
    storage_location = body.storage_location.strip()
    if len(storage_location) < 4:
        raise HTTPException(status_code=422, detail="Record the actual campus room, cabinet, shelf or other storage location.")
    with connect_db() as conn:
        report = read_report(conn, report_id)
        if report["report_type"] != "found" or not report["tag_id"]:
            raise HTTPException(status_code=409, detail="Only physically received and tagged found items can have a storage location.")
        if report["status"] not in {"available", "claim_approved"}:
            raise HTTPException(status_code=409, detail="Storage location can only be changed while the item is in campus custody.")
        previous_location = report["storage_location"]
        conn.execute("UPDATE reports SET storage_location=?, updated_at=? WHERE id=?",
                     (storage_location, now_iso(), report_id))
        audit(conn, user["id"], "storage_location_updated", "report", report_id,
              {"tag_id": report["tag_id"], "previous_location": previous_location,
               "new_location": storage_location, "note": (body.note or "").strip() or None})
        updated = read_report(conn, report_id)
    return {"report": serialise_report(updated, internal=True), "message": "Campus storage location updated."}
