"""Bounded research reads in one repeatable-read transaction; no collectors or writers."""
from __future__ import annotations

from collections import defaultdict
from uuid import UUID

import pandas as pd
from sqlalchemy import text

from src.database import get_engine
from src.focused_monitoring import summarise_wave
from src.research_evidence import build_dataset, choose_asof, dated
from src.review_profile_metrics import google_profile_observation


def _rows(connection, sql, params=None):
    return [dict(r) for r in connection.execute(text(sql), params or {}).mappings().all()]


def list_research_runs(*, engine=None, limit=100):
    if not 1 <= limit <= 500:
        raise ValueError("Run list limit must be between 1 and 500")
    with (engine or get_engine()).connect() as connection:
        return _rows(connection, """
            select id,target_google_place_id,target_business_name,primary_group,location_context,
                   benchmark_mode,providers,models,status,started_at,completed_at,prompt_count,repeat_count
            from public.ai_visibility_runs r
            where not exists (select 1 from public.ai_measurement_waves w
                              where w.run_id=r.id and w.panel_kind='free_check')
            order by started_at desc,id desc limit :limit
        """, {"limit": limit})


def load_research_dataset(run_ids, *, max_age_days=90, engine=None):
    ids = [str(UUID(str(value))) for value in run_ids]
    if not ids or len(ids) > 10 or len(set(ids)) != len(ids):
        raise ValueError("Select one to ten distinct saved runs")
    params = {"ids": ids}
    with (engine or get_engine()).connect() as connection:
        connection.execute(text("set transaction isolation level repeatable read, read only"))
        ready = {r["name"]: r["available"] for r in _rows(connection, """
            select name,to_regclass('public.' || name) is not null as available
            from unnest(cast(:names as text[])) name
        """, {"names": ["ai_measurement_waves", "review_profile_metrics", "public_evidence_captures", "public_evidence_decisions"]})}
        runs = _rows(connection, "select * from public.ai_visibility_runs where id=any(cast(:ids as uuid[]))", params)
        if len(runs) != len(ids):
            raise ValueError("A selected run no longer exists")
        waves = _rows(connection, "select * from public.ai_measurement_waves where run_id=any(cast(:ids as uuid[]))", params) if ready["ai_measurement_waves"] else []
        queries = _rows(connection, "select * from public.ai_visibility_queries where run_id=any(cast(:ids as uuid[]))", params)
        results = _rows(connection, "select * from public.ai_visibility_results where run_id=any(cast(:ids as uuid[]))", params)
        businesses = _rows(connection, "select google_place_id,business_name,primary_group,business_format from public.business_features")
        aliases = _rows(connection, "select alias_name,alias_normalized,google_place_id,canonical_business_name,alias_type,source_note,source_url from public.business_entity_aliases")
        # Only the predefined cohort gets evidence reads, never a cohort chosen from winners.
        pids = sorted({str(r["target_google_place_id"]) for r in runs} |
                      {str(pid) for w in waves for pid in w["configuration"].get("settings", {}).get("comparator_ids", [])})
        cohort = {"pids": pids}
        raw_profiles = _rows(connection, """
            select id,google_place_id,created_at,raw_data from public.raw_outscraper_locations
            where google_place_id=any(cast(:pids as text[])) order by created_at,id
        """, cohort)
        profiles = _rows(connection, "select * from public.review_profile_metrics where google_place_id=any(cast(:pids as text[]))", cohort) if ready["review_profile_metrics"] else []
        capture_meta = _rows(connection, "select id,google_place_id,archived_at from public.public_evidence_captures where google_place_id=any(cast(:pids as text[]))", cohort) if ready["public_evidence_captures"] else []
        selected = set()
        for run in runs:
            for pid in pids:
                cap = choose_asof([c for c in capture_meta if str(c["google_place_id"]) == pid], "archived_at", dated(run["started_at"]))
                if cap:
                    selected.add(str(cap["id"]))
        captures, decisions = [], []
        if selected:
            caps = {"ids": sorted(selected)}
            captures = _rows(connection, "select * from public.public_evidence_captures where id=any(cast(:ids as uuid[]))", caps)
            if ready["public_evidence_decisions"]:
                decisions = _rows(connection, "select * from public.public_evidence_decisions where capture_id=any(cast(:ids as uuid[]))", caps)
    profile_errors = []
    for raw in raw_profiles:
        try:
            profiles.append(google_profile_observation(raw))
        except ValueError as exc:
            profile_errors.append({"source_record_id": str(raw["id"]), "reason": str(exc)})
    wave_lookup = {str(w["run_id"]): w for w in waves}
    q_by_run, r_by_run = defaultdict(list), defaultdict(list)
    for q in queries: q_by_run[str(q["run_id"])].append(q)
    for r in results: r_by_run[str(r["run_id"])].append(r)
    summaries = [summarise_wave(run=r, wave=wave_lookup.get(str(r["id"])), queries=q_by_run[str(r["id"])],
        results=r_by_run[str(r["id"])], businesses=businesses, aliases=pd.DataFrame(aliases)) for r in runs]
    dataset = build_dataset(summaries, profiles=profiles, captures=captures, decisions=decisions, max_age_days=max_age_days)
    dataset.update(source_profile_errors=profile_errors,
        available_capture_dates=[{**c, "id": str(c["id"]), "archived_at": str(c["archived_at"])} for c in capture_meta],
        selected_run_ids=ids, measurement_provenance=summaries)
    return dataset
