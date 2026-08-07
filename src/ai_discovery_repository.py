from __future__ import annotations

import json
import uuid
from typing import Any

import pandas as pd
from sqlalchemy import text

from src.database import get_engine


def create_discovery_run(
    *,
    target_business_name: str,
    target_google_place_id: str | None,
    target_resolution_status: str,
    target_dataset_match_name: str | None,
    primary_group: str,
    category_label: str,
    location_context: str,
    website: str,
    description: str,
    propositions: list[str],
    providers: list[str],
    models: dict[str, str],
    prompt_count: int,
    repeat_count: int,
) -> dict[str, str]:
    run_id = str(
        uuid.uuid4()
    )

    target_id = (
        str(
            target_google_place_id
        )
        if target_google_place_id
        else (
            "discovery:"
            + run_id
        )
    )

    engine = get_engine()

    query = text(
        """
        insert into ai_visibility_runs (
            id,
            target_google_place_id,
            target_business_name,
            primary_group,
            location_context,
            benchmark_mode,
            providers,
            models,
            prompt_count,
            repeat_count,
            status,
            entry_mode,
            target_website,
            target_description,
            target_propositions,
            target_category_label,
            target_resolution_status,
            target_dataset_match_name
        )
        values (
            :id,
            :target_google_place_id,
            :target_business_name,
            :primary_group,
            :location_context,
            'model_memory',
            cast(:providers as jsonb),
            cast(:models as jsonb),
            :prompt_count,
            :repeat_count,
            'running',
            'ai_discovery_scan',
            :target_website,
            :target_description,
            cast(:target_propositions as jsonb),
            :target_category_label,
            :target_resolution_status,
            :target_dataset_match_name
        )
        """
    )

    with engine.begin() as connection:
        connection.execute(
            query,
            {
                "id":
                    run_id,
                "target_google_place_id":
                    target_id,
                "target_business_name":
                    target_business_name,
                "primary_group":
                    primary_group,
                "location_context":
                    location_context,
                "providers":
                    json.dumps(
                        providers
                    ),
                "models":
                    json.dumps(
                        models
                    ),
                "prompt_count":
                    int(
                        prompt_count
                    ),
                "repeat_count":
                    int(
                        max(
                            1,
                            repeat_count,
                        )
                    ),
                "target_website":
                    website or None,
                "target_description":
                    description or None,
                "target_propositions":
                    json.dumps(
                        propositions
                    ),
                "target_category_label":
                    category_label,
                "target_resolution_status":
                    target_resolution_status,
                "target_dataset_match_name":
                    (
                        target_dataset_match_name
                        or None
                    ),
            },
        )

    return {
        "run_id":
            run_id,
        "target_google_place_id":
            target_id,
    }


def list_discovery_runs(
    limit: int = 25,
) -> pd.DataFrame:
    engine = get_engine()

    query = text(
        """
        select
            id,
            target_google_place_id,
            target_business_name,
            target_category_label,
            location_context,
            status,
            repeat_count,
            prompt_count,
            providers,
            started_at,
            completed_at
        from ai_visibility_runs
        where entry_mode = 'ai_discovery_scan'
        order by started_at desc
        limit :limit
        """
    )

    with engine.connect() as connection:
        rows = connection.execute(
            query,
            {
                "limit":
                    int(
                        max(
                            1,
                            limit,
                        )
                    ),
            },
        ).mappings().all()

    return pd.DataFrame(rows)


def get_discovery_run(
    run_id: str,
) -> dict[str, Any]:
    engine = get_engine()

    query = text(
        """
        select *
        from ai_visibility_runs
        where
            id = :run_id
            and entry_mode = 'ai_discovery_scan'
        limit 1
        """
    )

    with engine.connect() as connection:
        row = connection.execute(
            query,
            {
                "run_id":
                    run_id,
            },
        ).mappings().first()

    return dict(row) if row else {}


def load_diagnostic_readiness(
    google_place_ids: list[str],
) -> pd.DataFrame:
    columns = [
        "google_place_id",
        "latest_website_audit",
        "website_score",
        "reviews_stored",
    ]

    if not google_place_ids:
        return pd.DataFrame(
            columns=columns
        )

    engine = get_engine()

    query = text(
        """
        with latest_audits as (
            select distinct on (
                google_place_id
            )
                google_place_id,
                completed_at
                    as latest_website_audit,
                website_completeness_score
                    as website_score
            from website_audit_runs
            where google_place_id = any(
                :google_place_ids
            )
            order by
                google_place_id,
                completed_at desc nulls last,
                started_at desc
        ),
        review_counts as (
            select
                google_place_id,
                count(*)::integer
                    as reviews_stored
            from business_reviews
            where google_place_id = any(
                :google_place_ids
            )
            group by google_place_id
        )
        select
            ids.google_place_id,
            la.latest_website_audit,
            la.website_score,
            coalesce(
                rc.reviews_stored,
                0
            ) as reviews_stored
        from unnest(
            cast(
                :google_place_ids
                as text[]
            )
        ) as ids(
            google_place_id
        )
        left join latest_audits la
          on la.google_place_id =
             ids.google_place_id
        left join review_counts rc
          on rc.google_place_id =
             ids.google_place_id
        """
    )

    with engine.connect() as connection:
        rows = connection.execute(
            query,
            {
                "google_place_ids":
                    google_place_ids,
            },
        ).mappings().all()

    return pd.DataFrame(
        rows,
        columns=columns,
    )
