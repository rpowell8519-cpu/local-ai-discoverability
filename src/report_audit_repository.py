from __future__ import annotations

import json
import uuid
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.database import get_engine
from src.report_audit_workflow import WORKFLOW_SCHEMA_VERSION
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

_INSERT = text(
    """
    insert into report_audit_revisions (
        id, schema_version, target_google_place_id, target_business_name,
        revision, supersedes_revision_id, revision_reason, known_for,
        desired_searches, owner_competitors, benchmark_run_id,
        website_evidence_state, review_evidence_state, reviewer_decisions,
        reviewer_decisions_complete, created_by
    ) values (
        :id, :schema_version, :target_google_place_id, :target_business_name,
        :revision, :supersedes_revision_id, :revision_reason, :known_for,
        cast(:desired_searches as jsonb), cast(:owner_competitors as jsonb),
        :benchmark_run_id, :website_evidence_state, :review_evidence_state,
        cast(:reviewer_decisions as jsonb), :reviewer_decisions_complete, :created_by
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


def save_owner_brief_revision(
    *,
    target_google_place_id: str,
    target_business_name: str,
    known_for: str,
    desired_searches: str,
    owner_competitors: str = "",
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

    database = engine or get_engine()
    with database.begin() as connection:
        latest = connection.execute(
            _LATEST_FOR_UPDATE,
            {"target_google_place_id": target_google_place_id},
        ).mappings().first()
        previous: Mapping[str, Any] = latest or {}
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
            "created_by": created_by,
        }
        row = connection.execute(_INSERT, parameters).mappings().one()
    return dict(row)
