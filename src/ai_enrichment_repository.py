from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

import pandas as pd
from sqlalchemy import text

from src.database import get_engine


def _normalise_name(
    value: Any,
) -> str:
    text_value = unicodedata.normalize(
        "NFKD",
        str(value or ""),
    )
    text_value = "".join(
        character
        for character in text_value
        if not unicodedata.combining(
            character
        )
    )
    text_value = text_value.lower()
    text_value = text_value.replace(
        "&",
        " and ",
    )
    text_value = re.sub(
        r"[^a-z0-9]+",
        " ",
        text_value,
    )
    return re.sub(
        r"\s+",
        " ",
        text_value,
    ).strip()


def load_entity_aliases() -> pd.DataFrame:
    engine = get_engine()

    query = text(
        """
        select
            alias_name,
            alias_normalized,
            google_place_id,
            canonical_business_name,
            alias_type,
            source_note,
            source_url
        from business_entity_aliases
        order by
            alias_type,
            alias_name
        """
    )

    with engine.connect() as connection:
        rows = connection.execute(
            query
        ).mappings().all()

    return pd.DataFrame(rows)


def upsert_enrichment_candidates(
    *,
    run_id: str,
    unresolved_market: pd.DataFrame,
) -> int:
    if unresolved_market.empty:
        return 0

    engine = get_engine()

    query = text(
        """
        insert into ai_competitor_enrichment_queue (
            candidate_key,
            raw_business_name,
            first_seen_run_id,
            last_seen_run_id,
            recommendation_count,
            provider_count,
            providers,
            best_position,
            status,
            last_seen_at
        )
        values (
            :candidate_key,
            :raw_business_name,
            :run_id,
            :run_id,
            :recommendation_count,
            :provider_count,
            cast(:providers as jsonb),
            :best_position,
            'needs_lookup',
            now()
        )
        on conflict (candidate_key)
        do update set
            raw_business_name =
                excluded.raw_business_name,
            last_seen_run_id =
                excluded.last_seen_run_id,
            recommendation_count =
                greatest(
                    ai_competitor_enrichment_queue.recommendation_count,
                    excluded.recommendation_count
                ),
            provider_count =
                greatest(
                    ai_competitor_enrichment_queue.provider_count,
                    excluded.provider_count
                ),
            providers =
                excluded.providers,
            best_position = case
                when
                    ai_competitor_enrichment_queue.best_position
                    is null
                then excluded.best_position
                when excluded.best_position is null
                then ai_competitor_enrichment_queue.best_position
                else least(
                    ai_competitor_enrichment_queue.best_position,
                    excluded.best_position
                )
            end,
            last_seen_at = now()
        """
    )

    payloads = []

    for row in unresolved_market.to_dict(
        "records"
    ):
        raw_name = str(
            row.get(
                "business_name"
            )
            or row.get(
                "raw_business_name"
            )
            or ""
        ).strip()

        if not raw_name:
            continue

        provider_names = []

        for provider in [
            "OpenAI",
            "Claude",
            "Gemini",
        ]:
            count = int(
                row.get(
                    f"{provider}_recommendations",
                    0,
                )
                or 0
            )

            if count > 0:
                provider_names.append(
                    provider
                )

        best_position = row.get(
            "average_position"
        )

        try:
            best_position = int(
                round(
                    float(
                        best_position
                    )
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            best_position = None

        payloads.append(
            {
                "candidate_key":
                    _normalise_name(
                        raw_name
                    ),
                "raw_business_name":
                    raw_name,
                "run_id":
                    run_id,
                "recommendation_count":
                    int(
                        row.get(
                            "recommendations",
                            0,
                        )
                        or 0
                    ),
                "provider_count":
                    int(
                        row.get(
                            "providers",
                            len(
                                provider_names
                            ),
                        )
                        or 0
                    ),
                "providers":
                    json.dumps(
                        provider_names
                    ),
                "best_position":
                    best_position,
            }
        )

    if not payloads:
        return 0

    with engine.begin() as connection:
        connection.execute(
            query,
            payloads,
        )

    return len(payloads)


def get_enrichment_queue() -> pd.DataFrame:
    engine = get_engine()

    query = text(
        """
        select
            id,
            raw_business_name,
            recommendation_count,
            provider_count,
            providers,
            best_position,
            status,
            resolved_google_place_id,
            notes,
            first_seen_at,
            last_seen_at
        from ai_competitor_enrichment_queue
        order by
            case status
                when 'needs_lookup' then 1
                when 'resolved_existing' then 2
                when 'imported' then 3
                else 4
            end,
            recommendation_count desc,
            raw_business_name
        """
    )

    with engine.connect() as connection:
        rows = connection.execute(
            query
        ).mappings().all()

    return pd.DataFrame(rows)
