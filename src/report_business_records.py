"""The current canonical business layer, as the report generator and the report runner read it.

One query, so the page and `src/report_runner.py` see the same businesses, websites, cities and
Google totals. It reads the latest raw Outscraper row per Place ID (`created_at desc, id desc`).
Read-only.
"""

from __future__ import annotations

from typing import Any

BUSINESS_RECORDS_SQL = """
        select
            google_place_id,
            business_name,
            raw_category,
            raw_type,
            primary_group,
            business_format,
            rol.raw_data->>'city' as city,
            coalesce(rol.raw_data->>'address', rol.raw_data->>'full_address') as address,
            coalesce(rol.raw_data->>'latitude', rol.raw_data->>'lat') as latitude,
            coalesce(rol.raw_data->>'longitude', rol.raw_data->>'lng') as longitude,
            coalesce(
                nullif(rol.raw_data->>'website', ''),
                nullif(rol.raw_data->>'site', '')
            ) as source_website_url,
            nullif(rol.raw_data->>'rating', '') as google_rating,
            nullif(rol.raw_data->>'reviews', '') as google_reviews
        from business_features bf
        left join lateral (
            select raw_data
            from raw_outscraper_locations
            where google_place_id = bf.google_place_id
            order by created_at desc, id desc
            limit 1
        ) rol on true
        where
            google_place_id is not null
            and business_name is not null
        order by lower(business_name), google_place_id
        """


def load_business_records(engine: Any = None) -> list[dict[str, Any]]:
    """Every current business, one dict per Place ID, ordered by name."""

    from sqlalchemy import text

    from src.database import get_engine

    with (engine or get_engine()).connect() as connection:
        return [dict(row) for row in connection.execute(text(BUSINESS_RECORDS_SQL)).mappings().all()]
