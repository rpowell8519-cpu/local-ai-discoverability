"""Load saved answers whose citations were recorded, for the cited sources page. Reads only."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from sqlalchemy import bindparam, text

from src.database import get_engine

LISTING_MATCHES_PATH = Path(__file__).with_name("citation_listing_matches.csv")

RESULTS_SQL = """
    select res.id as result_id, res.run_id, res.created_at as answered_at, res.provider, q.prompt_text as question,
           res.status, res.raw_response, res.report_metadata,
           coalesce(m.place_id, r.target_google_place_id) as place_id, r.target_business_name as run_business,
           bf.business_name as listed_business, bf.primary_group as listed_type, r.primary_group as run_type,
           r.location_context as location, {panel_kind} as panel_kind,
           r.target_website as run_website, site.website as listing_website
    from public.ai_visibility_results res
    join public.ai_visibility_runs r on r.id = res.run_id
    join public.ai_visibility_queries q on q.id = res.query_id
    {waves_join}
    left join unnest(cast(:match_runs as text[]), cast(:match_places as text[])) as m(run_id, place_id)
        on m.run_id = r.id::text
    left join public.business_features bf on bf.google_place_id = coalesce(m.place_id, r.target_google_place_id)
    left join lateral (
        select coalesce(nullif(rol.raw_data->>'website', ''), nullif(rol.raw_data->>'site', '')) as website
        from public.raw_outscraper_locations rol
        where rol.google_place_id = coalesce(m.place_id, r.target_google_place_id)
        order by rol.created_at desc, rol.id desc
        limit 1
    ) site on true
    where res.report_metadata->>'citation_status' = 'measured'
"""


def load_listing_matches(path: Path | str = LISTING_MATCHES_PATH) -> dict[str, str]:
    """Run ID -> Google Place ID for tests someone has since matched to their listing by hand."""
    with open(path, encoding="utf-8", newline="") as handle:
        rows = csv.DictReader(line for line in handle if line.strip() and not line.lstrip().startswith("#"))
        return {row["run_id"].strip(): row["place_id"].strip() for row in rows
                if row.get("run_id", "").strip() and row.get("place_id", "").strip()}


def load_cited_results(*, engine=None) -> list[dict[str, Any]]:
    """Every saved answer whose citations were recorded, with its business, type, area and kind of test.

    A business is identified by its Google Place ID, so the same business under two spellings is one
    business. A test whose business was never matched to a listing keeps the name it was run under,
    unless citation_listing_matches.csv links it to one.
    """
    matches = load_listing_matches()
    with (engine or get_engine()).connect() as connection:
        has_waves = connection.execute(text("select to_regclass('public.ai_measurement_waves') is not null")).scalar_one()
        sql = RESULTS_SQL.format(
            panel_kind="coalesce(w.panel_kind, 'core')" if has_waves else "'core'",
            waves_join="left join public.ai_measurement_waves w on w.run_id = r.id" if has_waves else "")
        query = text(sql).bindparams(bindparam("match_runs"), bindparam("match_places"))
        rows = [dict(row) for row in connection.execute(
            query, {"match_runs": list(matches), "match_places": list(matches.values())}).mappings()]
    for row in rows:
        listed = bool(row["listed_business"])
        row["business"] = row["listed_business"] if listed else f"{row['run_business']} (listing not confirmed)"
        row["business_type"] = row["listed_type"] if listed else row["run_type"]
        row["own_websites"] = [row["run_website"], row["listing_website"]]
    return rows
