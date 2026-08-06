from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy import text

from src.database import get_engine


STATUS_LABELS = {
    "direct": "Direct competitor",
    "indirect": "Indirect competitor",
    "possible": "Possible competitor",
    "not_relevant": "Not relevant",
}

LABEL_TO_STATUS = {
    label: status
    for status, label in STATUS_LABELS.items()
}


def load_reviews_for_target(
    target_google_place_id: str,
) -> pd.DataFrame:
    engine = get_engine()

    query = text(
        """
        select
            target_google_place_id,
            candidate_google_place_id,
            relationship_status,
            reviewer_notes,
            reviewed_by,
            reviewed_at
        from competitor_relationship_reviews
        where target_google_place_id = :target_google_place_id
        order by reviewed_at desc
        """
    )

    with engine.connect() as connection:
        rows = connection.execute(
            query,
            {
                "target_google_place_id":
                    target_google_place_id,
            },
        ).mappings().all()

    return pd.DataFrame(rows)


def get_review_for_pair(
    target_google_place_id: str,
    candidate_google_place_id: str,
) -> dict[str, Any]:
    engine = get_engine()

    query = text(
        """
        select
            relationship_status,
            reviewer_notes,
            reviewed_by,
            reviewed_at
        from competitor_relationship_reviews
        where
            target_google_place_id =
                :target_google_place_id
            and candidate_google_place_id =
                :candidate_google_place_id
        """
    )

    with engine.connect() as connection:
        row = connection.execute(
            query,
            {
                "target_google_place_id":
                    target_google_place_id,
                "candidate_google_place_id":
                    candidate_google_place_id,
            },
        ).mappings().first()

    return dict(row) if row else {}


def save_review(
    target_google_place_id: str,
    candidate_google_place_id: str,
    relationship_status: str,
    reviewer_notes: str = "",
    reviewed_by: str = "",
) -> None:
    if relationship_status not in STATUS_LABELS:
        raise ValueError(
            "Unsupported relationship status."
        )

    if (
        target_google_place_id
        == candidate_google_place_id
    ):
        raise ValueError(
            "A business cannot be its own competitor."
        )

    engine = get_engine()

    query = text(
        """
        insert into competitor_relationship_reviews (
            target_google_place_id,
            candidate_google_place_id,
            relationship_status,
            reviewer_notes,
            reviewed_by,
            reviewed_at,
            updated_at
        )
        values (
            :target_google_place_id,
            :candidate_google_place_id,
            :relationship_status,
            :reviewer_notes,
            :reviewed_by,
            now(),
            now()
        )
        on conflict (
            target_google_place_id,
            candidate_google_place_id
        )
        do update set
            relationship_status =
                excluded.relationship_status,
            reviewer_notes =
                excluded.reviewer_notes,
            reviewed_by =
                excluded.reviewed_by,
            reviewed_at = now(),
            updated_at = now()
        """
    )

    with engine.begin() as connection:
        connection.execute(
            query,
            {
                "target_google_place_id":
                    target_google_place_id,
                "candidate_google_place_id":
                    candidate_google_place_id,
                "relationship_status":
                    relationship_status,
                "reviewer_notes":
                    reviewer_notes.strip(),
                "reviewed_by":
                    reviewed_by.strip(),
            },
        )


def delete_review(
    target_google_place_id: str,
    candidate_google_place_id: str,
) -> None:
    engine = get_engine()

    query = text(
        """
        delete from competitor_relationship_reviews
        where
            target_google_place_id =
                :target_google_place_id
            and candidate_google_place_id =
                :candidate_google_place_id
        """
    )

    with engine.begin() as connection:
        connection.execute(
            query,
            {
                "target_google_place_id":
                    target_google_place_id,
                "candidate_google_place_id":
                    candidate_google_place_id,
            },
        )
