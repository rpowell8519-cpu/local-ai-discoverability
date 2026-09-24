from __future__ import annotations

import json
import uuid
from typing import Any, Mapping
from urllib.parse import urlparse

from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.database import get_engine
from src.report_audit_workflow import WORKFLOW_SCHEMA_VERSION
from src.report_competitors import MAX_COMPARISON_BUSINESSES
from src.report_generator_readiness import normalise_owner_brief, owner_brief_missing_fields


_LATEST = text(
    """
    select * from report_audit_revisions
    where target_google_place_id = :target_google_place_id
    order by revision desc
    limit 1
    """
)

_LATEST_FOR_UPDATE = text(str(_LATEST) + " for update")

_HISTORY = text(
    """
    select * from report_audit_revisions
    where target_google_place_id = :target_google_place_id
    order by revision desc
    """
)

_BY_REVISION = text(
    """
    select * from report_audit_revisions
    where target_google_place_id = :target_google_place_id and revision = :revision
    """
)

_INSERT = text(
    """
    insert into report_audit_revisions (
        id, schema_version, target_google_place_id, target_business_name,
        revision, supersedes_revision_id, revision_reason, known_for,
        desired_searches, owner_competitors, benchmark_run_id,
        website_evidence_state, review_evidence_state, reviewer_decisions,
        reviewer_decisions_complete, owner_context, manual_website_url, created_by
    ) values (
        :id, :schema_version, :target_google_place_id, :target_business_name,
        :revision, :supersedes_revision_id, :revision_reason, :known_for,
        cast(:desired_searches as jsonb), cast(:owner_competitors as jsonb),
        :benchmark_run_id, :website_evidence_state, :review_evidence_state,
        cast(:reviewer_decisions as jsonb), :reviewer_decisions_complete,
        cast(:owner_context as jsonb), :manual_website_url, :created_by
    ) returning *
    """
)


def get_latest_report_audit(
    target_google_place_id: str, *, engine: Engine | None = None
) -> dict[str, Any] | None:
    database = engine or get_engine()
    with database.connect() as connection:
        row = connection.execute(
            _LATEST, {"target_google_place_id": target_google_place_id}
        ).mappings().first()
    return dict(row) if row else None


def list_report_audit_revisions(
    target_google_place_id: str, *, engine: Engine | None = None
) -> list[dict[str, Any]]:
    """Every saved revision for this business, most recent first.

    Revisions are never edited or deleted, so a business that has been through this twice for two
    different purposes (say, two different customer-intent audits) has all of both still here, even
    though only the most recent is "current". Used to offer switching back to an earlier one.
    """

    database = engine or get_engine()
    with database.connect() as connection:
        rows = connection.execute(
            _HISTORY, {"target_google_place_id": target_google_place_id}
        ).mappings().all()
    return [dict(row) for row in rows]


def restore_report_audit_revision(
    target_google_place_id: str,
    revision: int,
    *,
    created_by: str = "streamlit_report_generator",
    engine: Engine | None = None,
) -> dict[str, Any]:
    """Make an earlier revision current again, as a new revision that copies it exactly.

    Every field, including the saved reviewer decisions, comes from the chosen revision untouched;
    nothing is merged with whatever is current now. This is an ordinary append like every other
    save here, so the revision being switched away from is not lost and can be returned to the
    same way later.
    """

    database = engine or get_engine()
    with database.begin() as connection:
        latest = connection.execute(
            _LATEST_FOR_UPDATE, {"target_google_place_id": target_google_place_id}
        ).mappings().first()
        chosen = connection.execute(
            _BY_REVISION, {"target_google_place_id": target_google_place_id, "revision": revision}
        ).mappings().first()
        if chosen is None:
            raise ValueError(f"Revision {revision} was not found for this business.")
        parameters = {
            "id": str(uuid.uuid4()),
            "schema_version": WORKFLOW_SCHEMA_VERSION,
            "target_google_place_id": target_google_place_id,
            "target_business_name": chosen["target_business_name"],
            "revision": int(latest["revision"]) + 1 if latest else 1,
            "supersedes_revision_id": str(latest["id"]) if latest else None,
            "revision_reason": f"Restored from revision {chosen['revision']}",
            "known_for": chosen["known_for"],
            "desired_searches": json.dumps(list(chosen["desired_searches"] or [])),
            "owner_competitors": json.dumps(list(chosen["owner_competitors"] or [])),
            "benchmark_run_id": chosen["benchmark_run_id"],
            "website_evidence_state": chosen["website_evidence_state"],
            "review_evidence_state": chosen["review_evidence_state"],
            "reviewer_decisions": json.dumps(dict(chosen["reviewer_decisions"] or {})),
            "reviewer_decisions_complete": bool(chosen["reviewer_decisions_complete"]),
            "owner_context": json.dumps(dict(chosen.get("owner_context") or {})),
            "manual_website_url": chosen.get("manual_website_url"),
            "created_by": created_by,
        }
        row = connection.execute(_INSERT, parameters).mappings().one()
    return dict(row)


def save_owner_competitors_revision(
    *,
    target_google_place_id: str,
    owner_competitors: list[str],
    created_by: str = "streamlit_report_generator",
    engine: Engine | None = None,
) -> dict[str, Any]:
    """Add or change the owner's named competitors, without disturbing anything already reviewed.

    A client naming one more competitor after the review is under way is a normal request, not a
    reason to redo it: unlike save_owner_brief_revision, this keeps the attached benchmark and every
    existing reviewer decision (name matches, approved recommendations, evidence waivers) exactly as
    they were. Only reviewer_decisions_complete is cleared, since the new name still needs its own
    decision before the review can be completed again.
    """

    names = list(dict.fromkeys(str(item).strip() for item in owner_competitors if str(item).strip()))
    database = engine or get_engine()
    with database.begin() as connection:
        latest = connection.execute(
            _LATEST_FOR_UPDATE, {"target_google_place_id": target_google_place_id}
        ).mappings().first()
        if not latest:
            raise ValueError("Submit the report owner brief before naming competitors.")
        parameters = {
            "id": str(uuid.uuid4()),
            "schema_version": WORKFLOW_SCHEMA_VERSION,
            "target_google_place_id": target_google_place_id,
            "target_business_name": latest["target_business_name"],
            "revision": int(latest["revision"]) + 1,
            "supersedes_revision_id": str(latest["id"]),
            "revision_reason": "Owner competitors updated",
            "known_for": latest["known_for"],
            "desired_searches": json.dumps(list(latest["desired_searches"] or [])),
            "owner_competitors": json.dumps(names),
            "benchmark_run_id": latest["benchmark_run_id"],
            "website_evidence_state": latest["website_evidence_state"],
            "review_evidence_state": latest["review_evidence_state"],
            "reviewer_decisions": json.dumps(dict(latest["reviewer_decisions"] or {})),
            "reviewer_decisions_complete": False,
            "owner_context": json.dumps(dict(latest.get("owner_context") or {})),
            "manual_website_url": latest.get("manual_website_url"),
            "created_by": created_by,
        }
        row = connection.execute(_INSERT, parameters).mappings().one()
    return dict(row)


def save_owner_brief_revision(
    *,
    target_google_place_id: str,
    target_business_name: str,
    known_for: str,
    desired_searches: str,
    owner_competitors: str = "",
    priority_services: str = "",
    service_areas: str = "",
    ideal_customers: str = "",
    exclusions: str = "",
    additional_context: str = "",
    manual_website_url: str = "",
    workflow_origin: str = "",
    created_by: str = "streamlit_report_generator",
    engine: Engine | None = None,
) -> dict[str, Any]:
    """Append an immutable brief revision and invalidate dependent review facts."""

    brief = normalise_owner_brief(
        known_for=known_for,
        desired_searches=desired_searches,
        owner_competitors=owner_competitors,
    )
    missing = owner_brief_missing_fields(brief)
    if missing:
        raise ValueError("Please complete: " + "; ".join(missing))
    if not str(target_google_place_id or "").strip():
        raise ValueError("A canonical Google Place ID is required")
    if not str(target_business_name or "").strip():
        raise ValueError("The business name is required")
    website_url = str(manual_website_url or "").strip()
    if website_url:
        parsed = urlparse(website_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("The website address must begin with http:// or https://")
    owner_context = {
        "priority_services": [line.strip(" \t-•") for line in priority_services.splitlines() if line.strip(" \t-•")],
        "service_areas": [line.strip(" \t-•") for line in service_areas.splitlines() if line.strip(" \t-•")],
        "ideal_customers": " ".join(str(ideal_customers or "").split()),
        "exclusions": [line.strip(" \t-•") for line in exclusions.splitlines() if line.strip(" \t-•")],
        "additional_context": " ".join(str(additional_context or "").split()),
    }
    if str(workflow_origin or "").strip():
        owner_context["workflow_origin"] = str(workflow_origin).strip()

    database = engine or get_engine()
    with database.begin() as connection:
        latest = connection.execute(
            _LATEST_FOR_UPDATE,
            {"target_google_place_id": target_google_place_id},
        ).mappings().first()
        previous: Mapping[str, Any] = latest or {}
        previous_context = dict(previous.get("owner_context") or {})
        preserved_origin = str(
            workflow_origin or previous_context.get("workflow_origin") or ""
        ).strip()
        if preserved_origin:
            owner_context["workflow_origin"] = preserved_origin
        parameters = {
            "id": str(uuid.uuid4()),
            "schema_version": WORKFLOW_SCHEMA_VERSION,
            "target_google_place_id": target_google_place_id,
            "target_business_name": target_business_name.strip(),
            "revision": int(previous.get("revision") or 0) + 1,
            "supersedes_revision_id": str(previous["id"]) if latest else None,
            "revision_reason": "Owner brief submitted" if not latest else "Owner brief updated",
            "known_for": brief["known_for"],
            "desired_searches": json.dumps(brief["desired_searches"]),
            "owner_competitors": json.dumps(brief["owner_competitors"]),
            "benchmark_run_id": None,
            "website_evidence_state": previous.get("website_evidence_state", "not_checked"),
            "review_evidence_state": previous.get("review_evidence_state", "not_checked"),
            "reviewer_decisions": "{}",
            "reviewer_decisions_complete": False,
            "owner_context": json.dumps(owner_context),
            "manual_website_url": website_url or None,
            "created_by": created_by,
        }
        row = connection.execute(_INSERT, parameters).mappings().one()
    return dict(row)


def attach_benchmark_revision(
    *,
    target_google_place_id: str,
    benchmark_run_id: str,
    created_by: str = "streamlit_ai_visibility",
    engine: Engine | None = None,
) -> dict[str, Any]:
    """Attach a completed benchmark to the latest brief as a new revision."""

    database = engine or get_engine()
    with database.begin() as connection:
        latest = connection.execute(
            _LATEST_FOR_UPDATE,
            {"target_google_place_id": target_google_place_id},
        ).mappings().first()
        if not latest:
            raise ValueError("Submit the report owner brief before attaching a benchmark")
        parameters = {
            "id": str(uuid.uuid4()),
            "schema_version": WORKFLOW_SCHEMA_VERSION,
            "target_google_place_id": target_google_place_id,
            "target_business_name": latest["target_business_name"],
            "revision": int(latest["revision"]) + 1,
            "supersedes_revision_id": str(latest["id"]),
            "revision_reason": "Completed benchmark attached",
            "known_for": latest["known_for"],
            "desired_searches": json.dumps(list(latest["desired_searches"])),
            "owner_competitors": json.dumps(list(latest["owner_competitors"])),
            "benchmark_run_id": benchmark_run_id,
            "website_evidence_state": latest["website_evidence_state"],
            "review_evidence_state": latest["review_evidence_state"],
            "reviewer_decisions": "{}",
            "reviewer_decisions_complete": False,
            "owner_context": json.dumps(dict(latest.get("owner_context") or {})),
            "manual_website_url": latest.get("manual_website_url"),
            "created_by": created_by,
        }
        row = connection.execute(_INSERT, parameters).mappings().one()
    return dict(row)


def save_reviewer_decisions_revision(
    *,
    target_google_place_id: str,
    reviewer_decisions: Mapping[str, Any],
    complete: bool,
    created_by: str = "streamlit_report_reviewer",
    engine: Engine | None = None,
) -> dict[str, Any]:
    """Append the selected comparison set and accessible report narrative."""

    database = engine or get_engine()
    with database.begin() as connection:
        latest = connection.execute(
            _LATEST_FOR_UPDATE,
            {"target_google_place_id": target_google_place_id},
        ).mappings().first()
        if not latest or not latest.get("benchmark_run_id"):
            raise ValueError("A completed benchmark must be attached before report review")
        cohort = list(reviewer_decisions.get("cohort_place_ids") or [])
        if len(cohort) > MAX_COMPARISON_BUSINESSES or len(set(cohort)) != len(cohort):
            raise ValueError(f"Select up to {MAX_COMPARISON_BUSINESSES} distinct verified comparison businesses")
        parameters = {
            "id": str(uuid.uuid4()),
            "schema_version": WORKFLOW_SCHEMA_VERSION,
            "target_google_place_id": target_google_place_id,
            "target_business_name": latest["target_business_name"],
            "revision": int(latest["revision"]) + 1,
            "supersedes_revision_id": str(latest["id"]),
            "revision_reason": "Report review completed" if complete else "Report review draft saved",
            "known_for": latest["known_for"],
            "desired_searches": json.dumps(list(latest["desired_searches"])),
            "owner_competitors": json.dumps(list(latest["owner_competitors"])),
            "benchmark_run_id": str(latest["benchmark_run_id"]),
            "website_evidence_state": latest["website_evidence_state"],
            "review_evidence_state": latest["review_evidence_state"],
            "reviewer_decisions": json.dumps(dict(reviewer_decisions)),
            "reviewer_decisions_complete": bool(complete),
            "owner_context": json.dumps(dict(latest.get("owner_context") or {})),
            "manual_website_url": latest.get("manual_website_url"),
            "created_by": created_by,
        }
        row = connection.execute(_INSERT, parameters).mappings().one()
    return dict(row)


def save_evidence_states_revision(
    *,
    target_google_place_id: str,
    website_evidence_state: str,
    review_evidence_state: str,
    created_by: str = "streamlit_report_generator",
    engine: Engine | None = None,
) -> dict[str, Any]:
    """Record checked/unavailable evidence without treating absence as a score."""

    allowed = {"available", "unavailable", "not_checked"}
    if website_evidence_state not in allowed or review_evidence_state not in allowed:
        raise ValueError("Unsupported evidence state")
    database = engine or get_engine()
    with database.begin() as connection:
        latest = connection.execute(
            _LATEST_FOR_UPDATE,
            {"target_google_place_id": target_google_place_id},
        ).mappings().first()
        if not latest:
            raise ValueError("Submit the report owner brief before recording evidence")
        parameters = {
            "id": str(uuid.uuid4()),
            "schema_version": WORKFLOW_SCHEMA_VERSION,
            "target_google_place_id": target_google_place_id,
            "target_business_name": latest["target_business_name"],
            "revision": int(latest["revision"]) + 1,
            "supersedes_revision_id": str(latest["id"]),
            "revision_reason": "Evidence availability reviewed",
            "known_for": latest["known_for"],
            "desired_searches": json.dumps(list(latest["desired_searches"])),
            "owner_competitors": json.dumps(list(latest["owner_competitors"])),
            "benchmark_run_id": latest.get("benchmark_run_id"),
            "website_evidence_state": website_evidence_state,
            "review_evidence_state": review_evidence_state,
            "reviewer_decisions": "{}",
            "reviewer_decisions_complete": False,
            "owner_context": json.dumps(dict(latest.get("owner_context") or {})),
            "manual_website_url": latest.get("manual_website_url"),
            "created_by": created_by,
        }
        row = connection.execute(_INSERT, parameters).mappings().one()
    return dict(row)
