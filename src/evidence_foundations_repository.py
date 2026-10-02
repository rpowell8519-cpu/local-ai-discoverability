"""Optional additive stores; legacy runs and raw evidence are never backfilled implicitly."""
from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import text

from src.database import get_engine
from src.proposition_catalog import starter_catalogue
from src.review_profile_metrics import google_profile_observation, review_sample_metrics

FOUNDATION_TABLES = ("proposition_catalog", "proposition_aliases", "review_profile_metrics", "ai_measurement_waves")


def list_foundation_businesses(*, engine=None) -> list[dict[str, Any]]:
    with (engine or get_engine()).connect() as connection:
        rows = connection.execute(text("""
            select google_place_id, business_name, primary_group from public.business_features
            where business_name is not null order by lower(business_name), google_place_id
        """)).mappings().all()
    return [dict(row) for row in rows]


def list_business_runs(place_id: str, *, engine=None) -> list[dict[str, Any]]:
    with (engine or get_engine()).connect() as connection:
        rows = connection.execute(text("""
            select id, target_google_place_id, target_business_name, target_propositions,
                   benchmark_mode, models, providers, status, started_at, completed_at,
                   primary_group, location_context, prompt_count, repeat_count
            from public.ai_visibility_runs where target_google_place_id=:place_id
            order by started_at desc, id desc
        """), {"place_id": place_id}).mappings().all()
    return [dict(row) for row in rows]


def foundation_status(*, engine=None) -> dict[str, bool]:
    with (engine or get_engine()).connect() as connection:
        rows = connection.execute(text("""
            select name, to_regclass('public.' || name) is not null as available
            from unnest(cast(:names as text[])) as name
        """), {"names": list(FOUNDATION_TABLES)}).mappings().all()
    return {row["name"]: bool(row["available"]) for row in rows}


def load_catalogue(*, engine=None):
    engine = engine or get_engine()
    status = foundation_status(engine=engine)
    if not status.get("proposition_catalog") or not status.get("proposition_aliases"):
        return (*starter_catalogue(), "local starter vocabulary; migration pending")
    with engine.connect() as connection:
        catalogue = connection.execute(text("select * from public.proposition_catalog order by label")).mappings().all()
        aliases = connection.execute(text("select * from public.proposition_aliases order by alias_key")).mappings().all()
    return list(catalogue), list(aliases), "stored catalogue"


def record_measurement_wave(connection, *, run_id: str, target_id: str, panel: dict[str, Any]) -> bool:
    """Called in the run transaction. The absent optional table keeps legacy execution usable."""
    ready = connection.execute(text("select to_regclass('public.ai_measurement_waves') is not null")).scalar_one()
    if not ready:
        return False
    # Serialize simultaneous starts of the same target/config so they share a series.
    connection.execute(text("select pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
                       {"scope": target_id + ":" + panel["configuration_sha256"]})
    series = connection.execute(text("""
        select w.series_id from public.ai_measurement_waves w
        join public.ai_visibility_runs r on r.id = w.run_id
        where r.target_google_place_id = :target_id and w.configuration_sha256 = :checksum
        order by w.created_at desc, w.run_id desc limit 1
    """), {"target_id": target_id, "checksum": panel["configuration_sha256"]}).scalar_one_or_none()
    connection.execute(text("""
        insert into public.ai_measurement_waves
            (run_id, series_id, panel_id, panel_kind, configuration_sha256, configuration)
        values (:run_id, :series_id, :panel_id, :panel_kind, :checksum, cast(:configuration as jsonb))
    """), {"run_id": run_id, "series_id": str(series or uuid.uuid4()), "panel_id": panel["panel_id"],
           "panel_kind": panel["panel_kind"], "checksum": panel["configuration_sha256"],
           "configuration": json.dumps(panel["configuration"], ensure_ascii=False, allow_nan=False)})
    return True


def load_measurement_wave(run_id: str, *, engine=None) -> dict[str, Any] | None:
    engine = engine or get_engine()
    if not foundation_status(engine=engine).get("ai_measurement_waves"):
        return None
    with engine.connect() as connection:
        row = connection.execute(text("select * from public.ai_measurement_waves where run_id=:run_id"),
                                 {"run_id": run_id}).mappings().first()
    return dict(row) if row else None


def load_profile_evidence(place_id: str, *, engine=None) -> dict[str, Any]:
    from src.review_repository import get_reviews
    engine = engine or get_engine()
    with engine.connect() as connection:
        # These are source captures, not refreshed current profile metrics.
        raw_rows = connection.execute(text("""
            select id, google_place_id, created_at, raw_data
            from public.raw_outscraper_locations where google_place_id=:place_id
            order by created_at desc, id desc
        """), {"place_id": place_id}).mappings().all()
        stored = []
        if foundation_status(engine=engine).get("review_profile_metrics"):
            stored = connection.execute(text("""
                select * from public.review_profile_metrics where google_place_id=:place_id
                order by observed_at desc, id desc
            """), {"place_id": place_id}).mappings().all()
    observations, errors = [], []
    for raw in raw_rows:
        try:
            observations.append(google_profile_observation(dict(raw)))
        except ValueError as exc:
            errors.append({"source_record_id": str(raw["id"]), "reason": str(exc)})
    return {"profile_observations": observations, "stored_profile_history": [dict(row) for row in stored],
            "samples": review_sample_metrics(get_reviews([place_id])), "unusable_observations": errors}


def save_google_profile_observation(raw_row: dict[str, Any], *, engine=None) -> None:
    """Explicit operator/collector write only. No historical backfill is triggered by reading."""
    observation = google_profile_observation(raw_row)
    with (engine or get_engine()).begin() as connection:
        connection.execute(text("""
            insert into public.review_profile_metrics
                (google_place_id, platform, rating, published_review_count, observed_at,
                 source_record_id, source_url, adapter_version, evidence_sha256)
            values (:google_place_id, :platform, :rating, :published_review_count, :observed_at,
                    :source_record_id, :source_url, :adapter_version, :evidence_sha256)
            on conflict (google_place_id, platform, source_record_id, adapter_version) do nothing
        """), observation)


def load_confirmed_question_map(run_id: str, place_id: str, *, engine=None) -> dict[str, str]:
    with (engine or get_engine()).connect() as connection:
        row = connection.execute(text("""
            select reviewer_decisions from public.report_audit_revisions
            where benchmark_run_id=:run_id and target_google_place_id=:place_id
              and reviewer_decisions_complete
            order by revision desc, created_at desc, id desc limit 1
        """), {"run_id": run_id, "place_id": place_id}).mappings().first()
    return dict((row["reviewer_decisions"] or {}).get("question_priority_map") or {}) if row else {}
