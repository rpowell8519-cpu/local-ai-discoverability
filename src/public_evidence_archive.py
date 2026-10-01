"""Immutable source payloads and human evidence decisions, independent of live collectors."""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from datetime import date, datetime, timezone
from decimal import Decimal
from urllib.parse import urlsplit
from uuid import UUID

from src.public_evidence_repository import matrix_from_bundle

CAPTURE_VERSION = "public-evidence-capture-v1"
DECISIONS = ("UNCERTAIN", "NO_SUPPORT", "EXPLICIT_SUPPORT", "IMPLICIT_SUPPORT", "CONTRADICTS")
ORIGINS = ("unknown", "owner_claim", "customer_report", "independent_third_party", "syndicated_claim")
AFFIRMATIVE = {"EXPLICIT_SUPPORT", "IMPLICIT_SUPPORT"}


def json_value(value):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date, UUID)):
        return value.isoformat() if hasattr(value, "isoformat") else str(value)
    if isinstance(value, Mapping):
        return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(v) for v in value]
    raise ValueError(f"Unsupported source value type: {type(value).__name__}")


def canonical_json(payload):
    return json.dumps(json_value(payload), sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def payload_hash(payload):
    return hashlib.sha256(canonical_json(payload).encode()).hexdigest()


def build_capture(bundle, catalogue, aliases):
    pid = str(bundle["business"].get("google_place_id") or "")
    if not pid or not bundle["business"].get("business_name"):
        raise ValueError("A canonical business identity is required")
    for row in [*(bundle.get("reviews") or []), *(bundle.get("platform_links") or []),
                *([bundle["listing"]] if bundle.get("listing") else []),
                *([bundle["audit"]] if bundle.get("audit") else [])]:
        if str(row.get("google_place_id") or "") != pid:
            raise ValueError("A source record belongs to a different or unresolved business")
    if bundle.get("pages") and not bundle.get("audit"):
        raise ValueError("Saved pages require their audit record")
    for page in bundle.get("pages") or []:
        if not page.get("id") or str(page.get("audit_run_id")) != str(bundle["audit"].get("id")):
            raise ValueError("A page does not belong to the captured audit")
    if not any(bundle.get(k) for k in ("listing", "pages", "reviews", "checks")):
        raise ValueError("There is no saved primary evidence to archive")
    sources = json_value(bundle)
    payload = {"version": CAPTURE_VERSION, "google_place_id": pid, "source_bundle": sources,
               "catalogue": json_value(catalogue), "aliases": json_value(aliases),
               "matrix": json_value(matrix_from_bundle(sources, catalogue, aliases)),
               "scope": "Copy of saved database evidence, not a fresh public-source collection"}
    body = canonical_json(payload)
    return {"google_place_id": pid, "capture_version": CAPTURE_VERSION, "canonical_payload": body,
            "payload": payload, "payload_sha256": hashlib.sha256(body.encode()).hexdigest()}


def _json_tree(value):
    """Compare JSON values after numeric decoding, while keeping booleans distinct."""
    if value is None:
        return ("null",)
    if isinstance(value, bool):
        return ("boolean", value)
    if isinstance(value, (int, float)):
        return ("number", Decimal(str(value)))
    if isinstance(value, str):
        return ("string", value)
    if isinstance(value, dict):
        return ("object", tuple((k, _json_tree(v)) for k, v in sorted(value.items())))
    if isinstance(value, list):
        return ("array", tuple(_json_tree(v) for v in value))
    raise ValueError("Unsupported JSON payload value")


def verify_capture(capture):
    payload = capture.get("payload") or {}
    if payload.get("version") != CAPTURE_VERSION or capture.get("capture_version") != CAPTURE_VERSION:
        raise ValueError("Unsupported capture version")
    if str(payload.get("google_place_id")) != str(capture.get("google_place_id")):
        raise ValueError("Capture identity mismatch")
    body = capture.get("canonical_payload")
    if body is not None:
        if not isinstance(body, str) or _json_tree(json.loads(body)) != _json_tree(payload):
            raise ValueError("Capture content hash mismatch")
        checksum = hashlib.sha256(body.encode()).hexdigest()
    else:
        checksum = payload_hash(payload)
    if checksum != capture.get("payload_sha256"):
        raise ValueError("Capture content hash mismatch")
    return payload


def validate_decision(capture, *, evidence_id, decision, origin, reviewer, note, identity_confirmed):
    payload = verify_capture(capture)
    evidence = next((o for o in payload["matrix"]["observations"] if o["evidence_id"] == evidence_id), None)
    if not evidence or evidence["kind"] != "proposition_candidate":
        raise ValueError("Review decisions must reference a proposition excerpt in this exact capture")
    if decision not in DECISIONS or origin not in ORIGINS:
        raise ValueError("Unsupported evidence decision or origin")
    if not str(reviewer or "").strip() or not str(note or "").strip():
        raise ValueError("Reviewer and explanation are required")
    if decision in AFFIRMATIVE | {"CONTRADICTS"} and (identity_confirmed is not True or origin == "unknown"):
        raise ValueError("Support/contradiction needs confirmed identity and an explained evidence origin")
    return {"evidence_id": evidence_id, "decision": decision, "origin": origin,
            "reviewer": str(reviewer).strip(), "note": str(note).strip(), "identity_confirmed": identity_confirmed is True}


def summarize_reviewed_evidence(capture, decisions):
    payload = verify_capture(capture)
    evidence = {o["evidence_id"]: o for o in payload["matrix"]["observations"] if o["kind"] == "proposition_candidate"}
    latest = {}
    for d in decisions:
        if str(d.get("capture_id")) != str(capture.get("id")):
            raise ValueError("Decision from another capture")
        validate_decision(capture, **{k: d[k] for k in ("evidence_id", "decision", "origin", "reviewer", "note", "identity_confirmed")})
        eid = d["evidence_id"]
        if eid not in latest or d["revision"] > latest[eid]["revision"]:
            latest[eid] = d
        elif d["revision"] == latest[eid]["revision"] and d != latest[eid]:
            raise ValueError("Conflicting decision revision")
    rows = []
    for prop in payload["catalogue"]:
        observations = [o for o in evidence.values() if o["field"] == prop["proposition_key"]]
        if not observations:
            continue
        approved = [o for o in observations if o["evidence_id"] in latest and latest[o["evidence_id"]]["decision"] in AFFIRMATIVE]
        reviewed = [o for o in observations if o["evidence_id"] in latest]
        definitive = [o for o in reviewed if latest[o["evidence_id"]]["decision"] != "UNCERTAIN"]
        contradicts = [o for o in observations if o["evidence_id"] in latest and latest[o["evidence_id"]]["decision"] == "CONTRADICTS"]
        eligible = [o for o in approved if latest[o["evidence_id"]]["origin"] != "syndicated_claim"]
        rows.append({"proposition_key": prop["proposition_key"], "proposition": prop["label"],
            "candidate_excerpts": len(observations), "reviewed_excerpts": len(reviewed),
            "unreviewed_excerpts": len(observations) - len(reviewed),
            "uncertain_excerpts": len(reviewed) - len(definitive),
            "reviewed_support_count": len(approved), "reviewed_contradiction_count": len(contradicts),
            "reviewed_source_breadth": len({o["source_class"] for o in eligible}) if definitive else None,
            "customer_source_breadth": len({o["source_class"] for o in eligible if latest[o["evidence_id"]]["origin"] == "customer_report"}) if definitive else None,
            "third_party_source_breadth": len({o["source_class"] for o in eligible if latest[o["evidence_id"]]["origin"] == "independent_third_party"}) if definitive else None,
            "supporting_evidence_ids": [o["evidence_id"] for o in approved],
            "contradicting_evidence_ids": [o["evidence_id"] for o in contradicts],
            "coverage": "complete_candidate_review" if len(definitive) == len(observations) else "partial_candidate_review"})
    return rows


def collection_attempt(*, google_place_id, source_class, source_url, status, observed_at,
                       sample_size, scope, note, adapter_version, capture_id=None):
    if status not in {"COLLECTED", "CHECKED_EMPTY", "FAILED", "UNAVAILABLE"}:
        raise ValueError("Only actual completed collection outcomes can be recorded")
    when = datetime.fromisoformat(observed_at.replace("Z", "+00:00")) if isinstance(observed_at, str) else observed_at
    if not isinstance(when, datetime) or when.tzinfo is None or when > datetime.now(timezone.utc):
        raise ValueError("A non-future timezone-aware attempt timestamp is required")
    parsed = urlsplit(str(source_url or ""))
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("A named public source URL is required")
    if any(not str(v or "").strip() for v in (google_place_id, source_class, scope, note, adapter_version)):
        raise ValueError("Business, source class, checked scope, explanation and adapter are required")
    if isinstance(sample_size, bool) or (sample_size is not None and not isinstance(sample_size, int)):
        raise ValueError("Sample size must be an integer or unknown")
    if (status == "COLLECTED" and (sample_size is None or sample_size <= 0)) or (status == "CHECKED_EMPTY" and sample_size != 0) or (status in {"FAILED", "UNAVAILABLE"} and sample_size is not None):
        raise ValueError("Sample size must agree with collection status")
    return {"google_place_id": google_place_id, "source_class": source_class, "source_url": source_url,
            "status": status, "observed_at": when.isoformat(), "sample_size": sample_size,
            "scope": scope.strip(), "note": note.strip(), "adapter_version": adapter_version,
            "capture_id": capture_id}
