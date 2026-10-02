"""Validate proposed actions independently of report recommendations and measurement outcomes."""
from __future__ import annotations

from datetime import date
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from src.public_evidence_archive import verify_capture

VERSION = "intervention-v1"
STATUSES = ("PLANNED", "IN_PROGRESS", "IMPLEMENTED", "PAUSED", "CANCELLED")
PRIORITIES = ("Not yet agreed", "High", "Medium", "Low")


def validate_intervention(record, capture):
    payload = verify_capture(capture)
    result = dict(record)
    if result.get("version") != VERSION:
        raise ValueError("Unsupported intervention version")
    result["action_id"] = str(UUID(str(result["action_id"])))
    if str(result.get("google_place_id")) != str(capture["google_place_id"]) or str(result.get("capture_id")) != str(capture["id"]):
        raise ValueError("Intervention evidence belongs to another business or capture")
    if result.get("proposition_key") not in {p["proposition_key"] for p in payload["catalogue"]}:
        raise ValueError("An existing proposition is required")
    for key in ("finding", "hypothesis", "owner", "effort", "created_by", "revision_note"):
        if not isinstance(result.get(key), str) or not result[key].strip():
            raise ValueError(f"{key.replace('_', ' ').capitalize()} is required")
        result[key] = result[key].strip()
    if result.get("status") not in STATUSES or result.get("priority") not in PRIORITIES:
        raise ValueError("Unsupported intervention status or priority")
    ids = result.get("affected_evidence_ids")
    available = {o["evidence_id"] for o in payload["matrix"]["observations"]}
    if not isinstance(ids, list) or not ids or len(set(ids)) != len(ids) or not set(ids) <= available:
        raise ValueError("Select distinct evidence IDs from the exact preserved capture")
    snapshot = result.get("finding_snapshot") or {}
    if snapshot.get("capture_id") != str(capture["id"]) or snapshot.get("capture_sha256") != capture["payload_sha256"] or snapshot.get("google_place_id") != str(capture["google_place_id"]):
        raise ValueError("Finding snapshot must identify the preserved capture and hash")
    if not any(r.get("proposition_key") == result["proposition_key"] for r in snapshot.get("rows", [])):
        raise ValueError("Finding snapshot must include the intervention proposition")
    dates = {}
    for key in ("planned_date", "implemented_date"):
        value = result.get(key)
        dates[key] = date.fromisoformat(value) if value else None
        result[key] = dates[key].isoformat() if dates[key] else None
    completed = result.get("completion_evidence")
    if not isinstance(completed, list):
        raise ValueError("Completion evidence must be a list of public URLs")
    for link in completed:
        parsed = urlsplit(link)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Completion evidence requires public URLs")
    if dates["implemented_date"] and dates["implemented_date"] > date.today():
        raise ValueError("Implementation date cannot be in the future")
    if result["status"] == "IMPLEMENTED" and (not dates["implemented_date"] or not completed):
        raise ValueError("Implemented actions require an actual date and completion evidence")
    if bool(dates["implemented_date"]) != bool(completed):
        raise ValueError("Implementation date and completion evidence must be supplied together")
    if result.get("baseline_series_id") and not result.get("baseline_run_id"):
        raise ValueError("Baseline series requires its exact baseline run")
    for key in ("baseline_run_id", "baseline_series_id", "approved_revision_id", "bundle_id"):
        if result.get(key):
            result[key] = str(UUID(str(result[key])))
        else:
            result[key] = None
    result.setdefault("approved_action_id", None)
    if bool(result.get("approved_action_id")) != bool(result.get("approved_revision_id")):
        raise ValueError("Approved action ID and its report revision must be linked together")
    families = result.get("focused_families")
    if not isinstance(families, list) or any(not isinstance(f, str) or not f.strip() for f in families) or len(set(families)) != len(families):
        raise ValueError("Focused families must be distinct explicit labels")
    return result


def new_action_id():
    return str(uuid4())
