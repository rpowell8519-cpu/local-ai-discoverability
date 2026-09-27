from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy import text

from src.database import get_engine


SUPPORTED_PLATFORMS = ("yelp", "tripadvisor", "checkatrade")

PLATFORM_LABELS = {
    "yelp": "Yelp",
    "tripadvisor": "TripAdvisor",
    "checkatrade": "Checkatrade",
}


def load_platform_links(google_place_ids: list[str]) -> pd.DataFrame:
    """All saved platform links for the given businesses.

    One row per (google_place_id, platform) that has been confirmed. Callers
    that need "does this business have a Yelp link yet" should filter this
    frame rather than assuming every business has every platform.
    """

    if not google_place_ids:
        return pd.DataFrame(
            columns=[
                "google_place_id",
                "platform",
                "external_url",
                "added_by",
                "added_at",
            ]
        )

    engine = get_engine()

    query = text(
        """
        select
            google_place_id,
            platform,
            external_url,
            added_by,
            added_at
        from business_platform_links
        where google_place_id = any(:google_place_ids)
        order by google_place_id, platform
        """
    )

    with engine.connect() as connection:
        rows = connection.execute(
            query,
            {"google_place_ids": google_place_ids},
        ).mappings().all()

    return pd.DataFrame(rows)


def save_platform_link(
    *,
    google_place_id: str,
    platform: str,
    external_url: str,
    added_by: str = "",
) -> None:
    """Save (or replace) the confirmed URL for one business on one platform.

    This is a manually-confirmed link, not an automatic match: the caller
    (a reviewer, in the Review Insights page) has found the business on that
    platform themselves and pasted its page URL in. Nothing here guesses.
    """

    if platform not in SUPPORTED_PLATFORMS:
        raise ValueError(f"Unsupported platform: {platform}")

    external_url = external_url.strip()

    if not external_url.lower().startswith(("http://", "https://")):
        raise ValueError("Please paste the full page URL, including https://")

    engine = get_engine()

    query = text(
        """
        insert into business_platform_links (
            google_place_id,
            platform,
            external_url,
            added_by,
            added_at,
            updated_at
        )
        values (
            :google_place_id,
            :platform,
            :external_url,
            :added_by,
            now(),
            now()
        )
        on conflict (google_place_id, platform)
        do update set
            external_url = excluded.external_url,
            added_by = excluded.added_by,
            updated_at = now()
        """
    )

    with engine.begin() as connection:
        connection.execute(
            query,
            {
                "google_place_id": google_place_id,
                "platform": platform,
                "external_url": external_url,
                "added_by": added_by.strip(),
            },
        )


def delete_platform_link(google_place_id: str, platform: str) -> None:
    engine = get_engine()

    query = text(
        """
        delete from business_platform_links
        where google_place_id = :google_place_id
            and platform = :platform
        """
    )

    with engine.begin() as connection:
        connection.execute(
            query,
            {"google_place_id": google_place_id, "platform": platform},
        )
