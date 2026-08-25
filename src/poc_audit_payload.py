from __future__ import annotations

import hashlib
import json
import math
import uuid
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any


SCHEMA_VERSION = "poc_audit_v1"


# Deliberate data-minimisation boundary. These are the only source
# review fields that may enter an immutable POC payload. Reviewer names,
# profile identifiers, contribution counts, avatars and the raw
# Outscraper object are not used by the deterministic review analysis or
# client report and must not be copied merely because they are available.
REVIEW_EVIDENCE_FIELDS = (
    "id",
    "review_id",
    "google_place_id",
    "business_name",
    "review_text",
    "review_rating",
    "review_timestamp",
    "review_datetime_utc",
    "review_link",
    "source",
    "source_file_name",
    "import_batch_id",
    "imported_at",
    "updated_at",
)


class PayloadValidationError(ValueError):
    """Raised when an audit payload is not safe to freeze."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def _json_value(value: Any) -> Any:
    if value is None or isinstance(
        value,
        (str, int, bool),
    ):
        return value

    if isinstance(value, float):
        return None if math.isnan(value) else value

    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, (date, datetime)):
        return value.isoformat()

    if isinstance(value, uuid.UUID):
        return str(value)

    if isinstance(value, Mapping):
        return {
            str(key): _json_value(item)
            for key, item in value.items()
        }

    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return [_json_value(item) for item in value]

    if hasattr(value, "item"):
        try:
            return _json_value(value.item())
        except (TypeError, ValueError):
            pass

    raise TypeError(
        "Unsupported canonical JSON value: "
        f"{type(value).__name__}"
    )


def canonical_json_bytes(value: Any) -> bytes:
    """Return the one canonical byte representation used for hashes."""

    return json.dumps(
        _json_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(str(value).encode("utf-8"))


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def freeze_ai_response(
    source: Mapping[str, Any],
    *,
    explicit_matches: list[dict[str, Any]] | None = None,
    indirect_matches: list[dict[str, Any]] | None = None,
    parser_reconciliation: Mapping[str, Any] | None = None,
    verification_notes: str | None = None,
    raw_response_inspected: bool = True,
) -> dict[str, Any]:
    """Freeze one complete provider response and its verification."""

    raw_response = str(source.get("raw_response") or "")

    record = {
        "response_id": str(source.get("id") or ""),
        "query_id": str(source.get("query_id") or ""),
        "provider": str(source.get("provider") or ""),
        "model": str(source.get("model") or ""),
        "base_prompt_order": int(
            source.get("base_prompt_order") or 0
        ),
        "prompt_category": (
            str(source.get("prompt_category") or "")
        ),
        "prompt_text": str(source.get("prompt_text") or ""),
        "repetition": int(source.get("repeat_index") or 0),
        "raw_response": raw_response,
        "raw_response_sha256": sha256_text(raw_response),
        "raw_response_inspected": bool(raw_response_inspected),
        "status": str(source.get("status") or ""),
        "response_complete": bool(source.get("response_complete")),
        "finish_reason": source.get("finish_reason"),
        "error_message": source.get("error_message"),
        "created_at": _json_value(source.get("created_at")),
        "explicit_matches": explicit_matches or [],
        "indirect_matches": indirect_matches or [],
        "parser_reconciliation": dict(
            parser_reconciliation or {}
        ),
        "verification_notes": verification_notes,
    }

    return _json_value(record)


def build_baseline_validation(
    responses: Sequence[Mapping[str, Any]],
    *,
    expected_responses: int,
    status: str,
    verification_method_version: str,
) -> dict[str, Any]:
    frozen = [_json_value(dict(item)) for item in responses]

    explicit_count = sum(
        any(
            bool(match.get("credible", True))
            for match in item.get("explicit_matches", [])
        )
        for item in frozen
    )
    indirect_count = sum(
        any(
            bool(match.get("credible", True))
            for match in item.get("indirect_matches", [])
        )
        for item in frozen
    )
    parser_error_count = sum(
        not bool(
            item.get("parser_reconciliation", {}).get(
                "target_correct",
                True,
            )
        )
        for item in frozen
    )
    unverifiable_count = sum(
        not bool(item.get("raw_response_inspected"))
        or not bool(item.get("response_complete"))
        or not str(item.get("raw_response") or "")
        for item in frozen
    )

    return {
        "status": str(status),
        "verification_method_version": str(
            verification_method_version
        ),
        "expected_responses": int(expected_responses),
        "inspected_responses": sum(
            bool(item.get("raw_response_inspected"))
            for item in frozen
        ),
        "complete_raw_responses": sum(
            bool(item.get("response_complete"))
            and bool(str(item.get("raw_response") or ""))
            for item in frozen
        ),
        "explicit_target_recommendations": explicit_count,
        "possible_indirect_target_recommendations": indirect_count,
        "target_parser_errors": parser_error_count,
        "unverifiable_responses": unverifiable_count,
        "response_audit_sha256": sha256_json(frozen),
        "responses": frozen,
    }


def freeze_review_set(
    *,
    google_place_id: str,
    business_name: str,
    records: Sequence[Mapping[str, Any]],
    status: str = "complete",
    exception: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Freeze the exact ordered review records used by analysis."""

    frozen_records = []

    for ordinal, source in enumerate(records, start=1):
        record = _json_value(
            {
                field: source.get(field)
                for field in REVIEW_EVIDENCE_FIELDS
            }
        )
        record["ordinal"] = ordinal
        # The current audit uses owner responses only as a presence
        # count. Preserve that exact analytical input without copying
        # response prose or timestamps that the report never uses.
        record["owner_response_present"] = bool(
            str(source.get("owner_answer") or "").strip()
        )
        frozen_records.append(record)

    review_ids = [
        str(record.get("review_id") or "")
        for record in frozen_records
    ]

    return {
        "google_place_id": str(google_place_id),
        "business_name": str(business_name),
        "status": str(status),
        "record_count": len(frozen_records),
        "ordered_review_ids": review_ids,
        "ordered_review_ids_sha256": sha256_json(review_ids),
        "records_sha256": sha256_json(frozen_records),
        "records": frozen_records,
        "exception": (
            _json_value(dict(exception))
            if exception is not None
            else None
        ),
    }


def _evidence_counts(payload: Mapping[str, Any]) -> dict[str, int]:
    baseline = payload.get("baseline_validation", {})
    market = payload.get("recommendation_market", {})
    website = payload.get("website_evidence", {})
    review = payload.get("review_evidence", {})

    website_audits = website.get("audits", [])
    review_sets = review.get("review_sets", [])

    return {
        "ai_raw_responses": len(baseline.get("responses", [])),
        "recommendation_slots": len(
            market.get("slot_evidence", [])
        ),
        "website_audits": len(website_audits),
        "website_pages": sum(
            len(item.get("pages", []))
            for item in website_audits
        ),
        "review_records": sum(
            len(item.get("records", []))
            for item in review_sets
        ),
    }


def build_poc_audit_payload(
    *,
    audit: Mapping[str, Any],
    revision: Mapping[str, Any],
    methodology: Mapping[str, Any],
    baseline_validation: Mapping[str, Any],
    source_traceability: Mapping[str, Any],
    recommendation_market: Mapping[str, Any],
    website_evidence: Mapping[str, Any],
    review_evidence: Mapping[str, Any],
    diagnostic: Mapping[str, Any],
    report: Mapping[str, Any],
) -> dict[str, Any]:
    """Build and validate one complete immutable report payload."""

    payload = _json_value(
        {
            "schema_version": SCHEMA_VERSION,
            "revision": dict(revision),
            "audit": dict(audit),
            "methodology": dict(methodology),
            "baseline_validation": dict(baseline_validation),
            "source_traceability": dict(source_traceability),
            "recommendation_market": dict(recommendation_market),
            "website_evidence": dict(website_evidence),
            "review_evidence": dict(review_evidence),
            "diagnostic": dict(diagnostic),
            "report": dict(report),
        }
    )

    payload["primary_evidence_counts"] = _evidence_counts(
        payload
    )

    validate_poc_audit_payload(payload)
    return payload


def validate_poc_audit_payload(
    payload: Mapping[str, Any],
) -> None:
    errors: list[str] = []

    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append("Unsupported or missing schema_version")

    audit = payload.get("audit", {})
    run_id = str(audit.get("baseline_run_id") or "")
    target_id = str(audit.get("target_google_place_id") or "")

    if not run_id:
        errors.append("audit.baseline_run_id is required")

    if not target_id or target_id.startswith("discovery:"):
        errors.append(
            "A canonical target Google Place ID is required"
        )

    revision = payload.get("revision", {})

    try:
        revision_number = int(revision.get("snapshot_revision"))
    except (TypeError, ValueError):
        revision_number = 0

    supersedes = revision.get("supersedes_snapshot_id")
    revision_reason = str(revision.get("revision_reason") or "").strip()

    if revision_number < 1:
        errors.append("snapshot_revision must be at least 1")

    if not revision_reason:
        errors.append("revision_reason is required")

    if revision_number == 1 and supersedes:
        errors.append(
            "Revision 1 cannot supersede another snapshot"
        )

    if revision_number > 1 and not supersedes:
        errors.append(
            "A revision above 1 must identify its superseded snapshot"
        )

    baseline = payload.get("baseline_validation", {})
    responses = baseline.get("responses", [])
    expected = int(baseline.get("expected_responses") or 0)

    if len(responses) != expected:
        errors.append(
            "Frozen AI response count does not match expected_responses"
        )

    response_ids = []

    for index, response in enumerate(responses, start=1):
        response_id = str(response.get("response_id") or "")
        response_ids.append(response_id)
        raw_text = response.get("raw_response")

        if not response_id:
            errors.append(f"AI response {index} has no response_id")

        if not isinstance(raw_text, str) or not raw_text:
            errors.append(
                f"AI response {response_id or index} has no raw text"
            )
        elif response.get("raw_response_sha256") != sha256_text(
            raw_text
        ):
            errors.append(
                f"AI response {response_id or index} hash mismatch"
            )

        for field in [
            "query_id",
            "provider",
            "model",
            "prompt_text",
            "base_prompt_order",
            "repetition",
            "parser_reconciliation",
        ]:
            if response.get(field) in (None, "", 0):
                errors.append(
                    f"AI response {response_id or index} "
                    f"is missing {field}"
                )

    if len(response_ids) != len(set(response_ids)):
        errors.append("AI response IDs are not unique")

    if baseline.get("response_audit_sha256") != sha256_json(
        responses
    ):
        errors.append("response_audit_sha256 mismatch")

    review_sets = payload.get("review_evidence", {}).get(
        "review_sets",
        [],
    )

    for review_set in review_sets:
        name = str(review_set.get("business_name") or "Unknown")
        records = review_set.get("records", [])
        review_ids = review_set.get("ordered_review_ids", [])

        actual_ids = [
            str(record.get("review_id") or "")
            for record in records
        ]

        if review_set.get("record_count") != len(records):
            errors.append(f"{name} review record_count mismatch")

        if review_ids != actual_ids:
            errors.append(f"{name} ordered review IDs mismatch")

        if len(review_ids) != len(set(review_ids)):
            errors.append(f"{name} review IDs are not unique")

        if review_set.get("ordered_review_ids_sha256") != (
            sha256_json(review_ids)
        ):
            errors.append(f"{name} ordered review-ID hash mismatch")

        if review_set.get("records_sha256") != sha256_json(records):
            errors.append(f"{name} frozen review-record hash mismatch")

        for index, record in enumerate(records, start=1):
            if record.get("ordinal") != index:
                errors.append(f"{name} review ordinal mismatch")
            if not str(record.get("review_id") or ""):
                errors.append(f"{name} review has no review_id")
            if "review_text" not in record:
                errors.append(f"{name} review text was not frozen")

        if (
            review_set.get("status") == "exception"
            and not review_set.get("exception")
        ):
            errors.append(f"{name} review exception is undocumented")

    counts = _evidence_counts(payload)

    if payload.get("primary_evidence_counts") != counts:
        errors.append("primary_evidence_counts mismatch")

    canonical_json_bytes(payload)

    if errors:
        raise PayloadValidationError(errors)


def payload_sha256(payload: Mapping[str, Any]) -> str:
    validate_poc_audit_payload(payload)
    return sha256_json(payload)
