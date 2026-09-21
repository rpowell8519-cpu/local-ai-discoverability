from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.ai_recommendation_intelligence import (
    build_business_share_table,
    build_recommendation_records,
)
from src.database import get_engine
from src.report_identity import confirmed_alias_frame


def load_report_candidates(
    *,
    run_id: str,
    target_google_place_id: str,
    engine: Engine | None = None,
    confirmed_target_names: Iterable[str] = (),
    confirmed_names: Mapping[str, Iterable[str]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Return measured verified candidates and unresolved names for human review.

    confirmed_target_names are raw AI names a reviewer has confirmed as the target
    business. They are credited to it as reviewer-confirmed aliases.
    """

    database = engine or get_engine()
    with database.connect() as connection:
        run = connection.execute(
            text("select primary_group from ai_visibility_runs where id = cast(:id as uuid)"),
            {"id": run_id},
        ).mappings().first()
        if not run:
            raise ValueError("The attached AI benchmark no longer exists")
        results = pd.DataFrame(
            connection.execute(
                text(
                    """
                    select r.*, q.prompt_order, q.base_prompt_order, q.repeat_index,
                           q.prompt_category, q.prompt_source, q.prompt_text
                    from ai_visibility_results r
                    join ai_visibility_queries q on q.id = r.query_id
                    where r.run_id = cast(:id as uuid)
                      and r.status = 'completed'
                      and coalesce(r.response_complete, true)
                    order by q.base_prompt_order, q.repeat_index, r.provider
                    """
                ),
                {"id": run_id},
            ).mappings().all()
        )
        business_rows = [dict(item) for item in connection.execute(
            text(
                """
                select bf.google_place_id, bf.business_name, bf.primary_group, bf.business_format,
                       rol.raw_data->>'city' as city,
                       coalesce(rol.raw_data->>'address', rol.raw_data->>'full_address') as address,
                       coalesce(rol.raw_data->>'latitude', rol.raw_data->>'lat') as latitude,
                       coalesce(rol.raw_data->>'longitude', rol.raw_data->>'lng') as longitude
                from business_features bf
                left join lateral (
                    select raw_data from raw_outscraper_locations
                    where google_place_id = bf.google_place_id
                    order by created_at desc, id desc limit 1
                ) rol on true
                """
            )
        ).mappings().all()]
        businesses = pd.DataFrame(
            business_rows
        )
        aliases = pd.DataFrame(
            connection.execute(
                text(
                    """
                    select alias_name, google_place_id, canonical_business_name,
                           alias_type, source_note, source_url
                    from business_entity_aliases
                    """
                )
            ).mappings().all()
        )
    if results.empty:
        return {"target": [], "verified": [], "unresolved": []}
    credited: dict[str, list[str]] = {
        str(pid): [str(name) for name in names if str(name).strip()]
        for pid, names in dict(confirmed_names or {}).items()
    }
    if confirmed_target_names:
        credited.setdefault(str(target_google_place_id), []).extend(str(n) for n in confirmed_target_names if str(n).strip())
    for pid, names in credited.items():
        row = next((r for r in business_rows if str(r["google_place_id"]) == pid), None)
        if row is not None and names:
            aliases = pd.concat(
                [aliases, confirmed_alias_frame(
                    target_google_place_id=pid, target_business_name=row["business_name"], confirmed=names)],
                ignore_index=True,
            )
    records = build_recommendation_records(
        results=results,
        businesses=businesses,
        aliases=aliases,
        target_google_place_id=target_google_place_id,
        commercial_competitor_ids=set(),
        primary_group=str(run.get("primary_group") or ""),
    )
    if records.empty:
        return {"target": [], "verified": [], "unresolved": []}
    target_records = records[
        records["google_place_id"].notna()
        & records["google_place_id"].astype(str).eq(str(target_google_place_id))
    ]
    target = (
        build_business_share_table(target_records).to_dict("records")
        if not target_records.empty
        else []
    )
    verified_records = records[
        records["google_place_id"].notna()
        & records["google_place_id"].astype(str).ne(str(target_google_place_id))
    ]
    verified = (
        build_business_share_table(verified_records).to_dict("records")
        if not verified_records.empty
        else []
    )
    verified = sorted(
        verified,
        key=lambda item: (-int(item.get("recommendations") or 0), str(item.get("business_name") or "")),
    )
    details = {str(item["google_place_id"]): item for item in business_rows}
    verified = [
        {**item, **{key: details.get(str(item.get("google_place_id")), {}).get(key)
                    for key in ("city", "address", "latitude", "longitude", "primary_group", "business_format")}}
        for item in verified
    ]
    unresolved_counts = (
        records[records["google_place_id"].isna()]
        .groupby("raw_business_name", dropna=False)
        .size()
        .sort_values(ascending=False)
    )
    unresolved = [
        {"business_name": str(name), "recommendations": int(count)}
        for name, count in unresolved_counts.items()
        if str(name).strip()
    ]
    return {"target": target, "verified": verified, "unresolved": unresolved}
