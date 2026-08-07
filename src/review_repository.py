from __future__ import annotations

import json
import uuid
from typing import Any

import pandas as pd
from sqlalchemy import text

from src.database import get_engine


def get_review_counts() -> pd.DataFrame:
    engine = get_engine()

    query = text(
        """
        select
            google_place_id,
            max(business_name) as business_name,
            count(*) as review_count,
            avg(review_rating)::numeric(5, 2)
                as sample_rating,
            max(review_datetime_utc)
                as latest_review,
            min(review_datetime_utc)
                as earliest_review
        from business_reviews
        group by google_place_id
        order by business_name
        """
    )

    with engine.connect() as connection:
        rows = connection.execute(
            query
        ).mappings().all()

    return pd.DataFrame(rows)


def get_reviews(
    google_place_ids: list[str],
) -> pd.DataFrame:
    if not google_place_ids:
        return pd.DataFrame()

    engine = get_engine()

    query = text(
        """
        select
            google_place_id,
            business_name,
            review_id,
            review_text,
            review_rating,
            review_timestamp,
            review_datetime_utc,
            review_likes,
            author_title,
            author_reviews_count,
            owner_answer,
            review_link
        from business_reviews
        where google_place_id = any(
            :google_place_ids
        )
        order by
            google_place_id,
            review_datetime_utc desc nulls last,
            imported_at desc
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

    return pd.DataFrame(rows)


def save_theme_analysis(
    *,
    google_place_id: str,
    business_name: str,
    profile_key: str,
    reviews_analysed: int,
    themes: pd.DataFrame,
) -> str:
    engine = get_engine()
    run_id = str(uuid.uuid4())

    run_query = text(
        """
        insert into review_analysis_runs (
            id,
            google_place_id,
            business_name,
            profile_key,
            analysis_method,
            reviews_analysed
        )
        values (
            :id,
            :google_place_id,
            :business_name,
            :profile_key,
            'rules_v1',
            :reviews_analysed
        )
        """
    )

    theme_query = text(
        """
        insert into review_themes (
            analysis_run_id,
            google_place_id,
            theme_key,
            theme_label,
            theme_category,
            mention_count,
            mention_pct,
            positive_count,
            neutral_count,
            negative_count,
            positive_examples,
            negative_examples
        )
        values (
            :analysis_run_id,
            :google_place_id,
            :theme_key,
            :theme_label,
            :theme_category,
            :mention_count,
            :mention_pct,
            :positive_count,
            :neutral_count,
            :negative_count,
            cast(:positive_examples as jsonb),
            cast(:negative_examples as jsonb)
        )
        """
    )

    payloads = []

    for row in themes.to_dict("records"):
        payloads.append(
            {
                "analysis_run_id": run_id,
                "google_place_id": google_place_id,
                "theme_key": row["theme_key"],
                "theme_label": row["theme_label"],
                "theme_category": row["category"],
                "mention_count": int(
                    row["mention_count"]
                ),
                "mention_pct": float(
                    row["mention_pct"]
                ),
                "positive_count": int(
                    row["positive_count"]
                ),
                "neutral_count": int(
                    row["neutral_count"]
                ),
                "negative_count": int(
                    row["negative_count"]
                ),
                "positive_examples": json.dumps(
                    row["positive_examples"]
                ),
                "negative_examples": json.dumps(
                    row["negative_examples"]
                ),
            }
        )

    with engine.begin() as connection:
        connection.execute(
            run_query,
            {
                "id": run_id,
                "google_place_id":
                    google_place_id,
                "business_name":
                    business_name,
                "profile_key":
                    profile_key,
                "reviews_analysed":
                    int(reviews_analysed),
            },
        )

        if payloads:
            connection.execute(
                theme_query,
                payloads,
            )

    return run_id
