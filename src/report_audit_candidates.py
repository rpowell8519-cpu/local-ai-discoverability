from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.ai_recommendation_intelligence import (
    build_business_share_table,
    build_recommendation_records,
)
from src.database import get_engine


def load_report_candidates(
    *, run_id: str, target_google_place_id: str, engine: Engine | None = None
) -> dict[str, list[dict[str, Any]]]:
    """Return measured verified candidates and unresolved names for human review."""

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
        businesses = pd.DataFrame(
            connection.execute(
                text(
                    "select google_place_id, business_name, primary_group, business_format from business_features"
                )
            ).mappings().all()
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
        return {"verified": [], "unresolved": []}
    records = build_recommendation_records(
        results=results,
        businesses=businesses,
        aliases=aliases,
        target_google_place_id=target_google_place_id,
        commercial_competitor_ids=set(),
        primary_group=str(run.get("primary_group") or ""),
    )
    if records.empty:
        return {"verified": [], "unresolved": []}
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
    return {"verified": verified, "unresolved": unresolved}
