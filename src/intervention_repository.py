"""Explicit append-only action revisions. Optional storage never changes existing reports."""
from __future__ import annotations

from sqlalchemy import text

from src.database import get_engine
from src.interventions import validate_intervention
from src.public_evidence_archive import canonical_json
from src.public_evidence_archive_repository import load_capture

TABLE = "positioning_interventions"


def intervention_storage_ready(*, engine=None):
    with (engine or get_engine()).connect() as connection:
        return bool(connection.execute(text("select to_regclass('public.positioning_interventions') is not null")).scalar_one())


def list_interventions(place_id, *, engine=None):
    engine = engine or get_engine()
    if not intervention_storage_ready(engine=engine):
        return []
    with engine.connect() as connection:
        rows = connection.execute(text("""
            select distinct on (action_id) * from public.positioning_interventions
            where google_place_id=:pid order by action_id,revision desc
        """), {"pid": place_id}).mappings().all()
    return [dict(r) for r in rows]


def list_intervention_history(action_id, *, engine=None):
    with (engine or get_engine()).connect() as connection:
        rows = connection.execute(text("select * from public.positioning_interventions where action_id=:id order by revision"),
                                  {"id": action_id}).mappings().all()
    return [dict(r) for r in rows]


def save_intervention(record, *, expected_revision=0, engine=None):
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int) or expected_revision < 0:
        raise ValueError("Expected revision must be a nonnegative integer")
    engine = engine or get_engine()
    if not intervention_storage_ready(engine=engine):
        raise ValueError("The separately approved intervention migration must be applied before saving")
    capture = load_capture(str(record["capture_id"]), engine=engine)
    record = validate_intervention(record, capture)
    with engine.begin() as connection:
        connection.execute(text("select pg_advisory_xact_lock(hashtextextended(:scope,0))"),
                           {"scope": "intervention:" + record["action_id"]})
        previous = connection.execute(text("""
            select id,revision from public.positioning_interventions where action_id=:id
            order by revision desc limit 1
        """), {"id": record["action_id"]}).mappings().first()
        revision = previous["revision"] if previous else 0
        if revision != expected_revision:
            raise ValueError("This action changed since it was loaded. Reload its latest revision before saving")
        return str(connection.execute(text("""
            insert into public.positioning_interventions
                (action_id,revision,supersedes_id,google_place_id,proposition_key,capture_id,
                 baseline_run_id,baseline_series_id,approved_revision_id,approved_action_id,bundle_id,record,created_by)
            values (:action_id,:revision,:supersedes_id,:google_place_id,:proposition_key,:capture_id,
                    :baseline_run_id,:baseline_series_id,:approved_revision_id,:approved_action_id,:bundle_id,
                    cast(:body as jsonb),:created_by) returning id
        """), {**record, "revision": revision + 1, "supersedes_id": str(previous["id"]) if previous else None,
               "body": canonical_json(record)}).scalar_one())
