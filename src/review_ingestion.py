from __future__ import annotations

import html
import io
import json
import math
import re
import uuid
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from sqlalchemy import text

from src.database import get_engine


REQUIRED_COLUMNS = {
    "name",
    "place_id",
    "review_id",
    "review_text",
    "review_rating",
}

SOURCE = "outscraper_google_reviews"


def _missing(value: Any) -> bool:
    if value is None:
        return True

    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _clean_text(value: Any) -> str | None:
    if _missing(value):
        return None

    text_value = html.unescape(str(value))
    text_value = re.sub(
        r"<br\s*/?>",
        "\n",
        text_value,
        flags=re.IGNORECASE,
    )
    text_value = re.sub(
        r"<[^>]+>",
        " ",
        text_value,
    )
    text_value = re.sub(
        r"[ \t]+",
        " ",
        text_value,
    )
    text_value = re.sub(
        r"\n{3,}",
        "\n\n",
        text_value,
    )

    cleaned = text_value.strip()
    return cleaned or None


def _int_or_none(value: Any) -> int | None:
    if _missing(value):
        return None

    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _timestamp_to_iso(
    value: Any,
) -> str | None:
    timestamp_value = _int_or_none(value)

    if timestamp_value is None:
        return None

    try:
        return datetime.fromtimestamp(
            timestamp_value,
            tz=timezone.utc,
        ).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def read_outscraper_reviews(
    uploaded_file: Any,
) -> pd.DataFrame:
    file_name = str(
        getattr(uploaded_file, "name", "")
        or ""
    ).lower()

    if file_name.endswith(".xlsx"):
        frame = pd.read_excel(
            uploaded_file,
            engine="openpyxl",
        )
    elif file_name.endswith(".csv"):
        frame = pd.read_csv(uploaded_file)
    else:
        raise ValueError(
            "Please upload an Outscraper .xlsx or .csv file."
        )

    missing_columns = REQUIRED_COLUMNS - set(
        frame.columns
    )

    if missing_columns:
        raise ValueError(
            "The file is missing required Outscraper columns: "
            + ", ".join(sorted(missing_columns))
        )

    return frame


def normalise_review_frame(
    frame: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []

    for record in frame.to_dict("records"):
        place_id = _clean_text(
            record.get("place_id")
        )
        review_id = _clean_text(
            record.get("review_id")
        )
        business_name = _clean_text(
            record.get("name")
        )
        review_text = _clean_text(
            record.get("review_text")
        )
        review_rating = _int_or_none(
            record.get("review_rating")
        )

        valid = bool(
            place_id
            and review_id
            and business_name
            and review_text
            and review_rating is not None
        )

        output = {
            "google_place_id": place_id,
            "business_name": business_name,
            "review_id": review_id,
            "review_text": review_text,
            "review_rating": review_rating,
            "review_timestamp": _int_or_none(
                record.get("review_timestamp")
            ),
            "review_datetime_utc": _timestamp_to_iso(
                record.get("review_timestamp")
            ),
            "review_likes": _int_or_none(
                record.get("review_likes")
            ),
            "author_title": _clean_text(
                record.get("author_title")
            ),
            "author_id": _clean_text(
                record.get("author_id")
            ),
            "author_reviews_count": _int_or_none(
                record.get("author_reviews_count")
            ),
            "author_photos_count": _int_or_none(
                record.get("author_photos_count")
            ),
            "owner_answer": _clean_text(
                record.get("owner_answer")
            ),
            "owner_answer_timestamp": _int_or_none(
                record.get("owner_answer_timestamp")
            ),
            "owner_answer_datetime_utc": _timestamp_to_iso(
                record.get("owner_answer_timestamp")
            ),
            "review_link": _clean_text(
                record.get("review_link")
            ),
            "location_link": _clean_text(
                record.get("location_link")
            ),
            "raw_data": json.dumps(
                {
                    str(key): (
                        None
                        if _missing(value)
                        else value
                    )
                    for key, value in record.items()
                },
                default=str,
            ),
            "valid": valid,
        }

        rows.append(output)

    normalised = pd.DataFrame(rows)

    valid_frame = normalised[
        normalised["valid"]
    ].copy()

    invalid_frame = normalised[
        ~normalised["valid"]
    ].copy()

    valid_frame = valid_frame.drop_duplicates(
        subset=[
            "google_place_id",
            "review_id",
        ],
        keep="last",
    )

    return valid_frame, invalid_frame


def _create_import_batch(
    source_file_name: str,
    total_rows: int,
    valid_rows: int,
    business_count: int,
) -> str:
    engine = get_engine()
    batch_id = str(uuid.uuid4())

    query = text(
        """
        insert into review_import_batches (
            id,
            source_file_name,
            source,
            total_rows,
            valid_rows,
            business_count,
            status
        )
        values (
            :id,
            :source_file_name,
            :source,
            :total_rows,
            :valid_rows,
            :business_count,
            'running'
        )
        """
    )

    with engine.begin() as connection:
        connection.execute(
            query,
            {
                "id": batch_id,
                "source_file_name": source_file_name,
                "source": SOURCE,
                "total_rows": int(total_rows),
                "valid_rows": int(valid_rows),
                "business_count": int(business_count),
            },
        )

    return batch_id


def _finish_import_batch(
    batch_id: str,
    *,
    status: str,
    imported_rows: int,
    error_message: str | None = None,
) -> None:
    engine = get_engine()

    query = text(
        """
        update review_import_batches
        set
            status = :status,
            imported_rows = :imported_rows,
            error_message = :error_message,
            completed_at = now()
        where id = :id
        """
    )

    with engine.begin() as connection:
        connection.execute(
            query,
            {
                "id": batch_id,
                "status": status,
                "imported_rows": int(imported_rows),
                "error_message": error_message,
            },
        )


def import_reviews(
    frame: pd.DataFrame,
    *,
    source_file_name: str,
) -> dict[str, Any]:
    valid_frame, invalid_frame = (
        normalise_review_frame(frame)
    )

    business_count = (
        valid_frame["google_place_id"].nunique()
        if not valid_frame.empty
        else 0
    )

    batch_id = _create_import_batch(
        source_file_name=source_file_name,
        total_rows=len(frame),
        valid_rows=len(valid_frame),
        business_count=business_count,
    )

    if valid_frame.empty:
        _finish_import_batch(
            batch_id,
            status="completed",
            imported_rows=0,
        )

        return {
            "batch_id": batch_id,
            "processed_rows": 0,
            "invalid_rows": len(invalid_frame),
            "business_count": 0,
        }

    query = text(
        """
        insert into business_reviews (
            google_place_id,
            business_name,
            review_id,
            review_text,
            review_rating,
            review_timestamp,
            review_datetime_utc,
            review_likes,
            author_title,
            author_id,
            author_reviews_count,
            author_photos_count,
            owner_answer,
            owner_answer_timestamp,
            owner_answer_datetime_utc,
            review_link,
            location_link,
            source,
            source_file_name,
            import_batch_id,
            raw_data,
            updated_at
        )
        values (
            :google_place_id,
            :business_name,
            :review_id,
            :review_text,
            :review_rating,
            :review_timestamp,
            cast(:review_datetime_utc as timestamptz),
            :review_likes,
            :author_title,
            :author_id,
            :author_reviews_count,
            :author_photos_count,
            :owner_answer,
            :owner_answer_timestamp,
            cast(:owner_answer_datetime_utc as timestamptz),
            :review_link,
            :location_link,
            :source,
            :source_file_name,
            :import_batch_id,
            cast(:raw_data as jsonb),
            now()
        )
        on conflict (
            google_place_id,
            review_id
        )
        do update set
            business_name = excluded.business_name,
            review_text = excluded.review_text,
            review_rating = excluded.review_rating,
            review_timestamp = excluded.review_timestamp,
            review_datetime_utc = excluded.review_datetime_utc,
            review_likes = excluded.review_likes,
            author_title = excluded.author_title,
            author_id = excluded.author_id,
            author_reviews_count = excluded.author_reviews_count,
            author_photos_count = excluded.author_photos_count,
            owner_answer = excluded.owner_answer,
            owner_answer_timestamp = excluded.owner_answer_timestamp,
            owner_answer_datetime_utc = excluded.owner_answer_datetime_utc,
            review_link = excluded.review_link,
            location_link = excluded.location_link,
            source_file_name = excluded.source_file_name,
            import_batch_id = excluded.import_batch_id,
            raw_data = excluded.raw_data,
            updated_at = now()
        """
    )

    payloads = []

    for record in valid_frame.to_dict("records"):
        payload = {
            key: record.get(key)
            for key in [
                "google_place_id",
                "business_name",
                "review_id",
                "review_text",
                "review_rating",
                "review_timestamp",
                "review_datetime_utc",
                "review_likes",
                "author_title",
                "author_id",
                "author_reviews_count",
                "author_photos_count",
                "owner_answer",
                "owner_answer_timestamp",
                "owner_answer_datetime_utc",
                "review_link",
                "location_link",
                "raw_data",
            ]
        }
        payload.update(
            {
                "source": SOURCE,
                "source_file_name": source_file_name,
                "import_batch_id": batch_id,
            }
        )
        payloads.append(payload)

    engine = get_engine()

    try:
        with engine.begin() as connection:
            connection.execute(
                query,
                payloads,
            )

        _finish_import_batch(
            batch_id,
            status="completed",
            imported_rows=len(payloads),
        )

    except Exception as exc:
        _finish_import_batch(
            batch_id,
            status="failed",
            imported_rows=0,
            error_message=str(exc),
        )
        raise

    return {
        "batch_id": batch_id,
        "processed_rows": len(payloads),
        "invalid_rows": len(invalid_frame),
        "business_count": business_count,
    }
