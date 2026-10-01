"""Profile observations and collected text samples are different populations."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from src.review_ingestion import SOURCE, SOURCE_TRIPADVISOR, SOURCE_YELP

SOURCE_PLATFORMS = {SOURCE: "google", SOURCE_YELP: "yelp", SOURCE_TRIPADVISOR: "tripadvisor"}
ADAPTER_VERSION = "google-listing-profile-v1"


def _number(value: Any, *, count=False) -> int | float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (ValueError, TypeError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    if count:
        return int(number) if number.is_integer() else None
    return number if 1 <= number <= 5 else None


def google_profile_observation(raw_row: dict[str, Any]) -> dict[str, Any]:
    """Use a named raw listing capture; never substitute text counts or import time."""
    raw = dict(raw_row.get("raw_data") or {})
    observed = raw_row.get("created_at")
    if isinstance(observed, str):
        observed = datetime.fromisoformat(observed.replace("Z", "+00:00"))
    if not isinstance(observed, datetime) or observed.tzinfo is None:
        raise ValueError("A dated source capture with a timezone is required")
    if observed > datetime.now(timezone.utc):
        raise ValueError("A source capture cannot be in the future")
    if not raw_row.get("id") or not raw_row.get("google_place_id"):
        raise ValueError("A source record ID and canonical Place ID are required")
    return {"google_place_id": str(raw_row["google_place_id"]), "platform": "google",
            "rating": _number(raw.get("rating")), "published_review_count": _number(raw.get("reviews"), count=True),
            "observed_at": observed.isoformat(), "source_record_id": str(raw_row["id"]),
            "source_url": raw.get("location_link") or raw.get("google_maps_url"),
            "adapter_version": ADAPTER_VERSION,
            "evidence_sha256": hashlib.sha256(json.dumps(raw, sort_keys=True, ensure_ascii=False,
                                                        separators=(",", ":")).encode()).hexdigest(),
            "latest_published_review_at": None, "recent_review_velocity": None}


def review_sample_metrics(reviews: pd.DataFrame) -> list[dict[str, Any]]:
    """Count distinct nonblank texts by business and platform; dates describe only this sample."""
    if reviews.empty:
        return []
    frame = reviews.copy()
    if "source" not in frame:
        frame["source"] = SOURCE  # legacy saved review records default to Google
    frame["source"] = frame["source"].fillna("unknown").replace("", "unknown")
    frame = frame[frame["review_text"].fillna("").astype(str).str.strip().ne("")]
    frame = frame.drop_duplicates(["google_place_id", "source", "review_id"])
    rows = []
    for (pid, source), group in frame.groupby(["google_place_id", "source"]):
        dates = pd.to_datetime(group.get("review_datetime_utc", pd.Series(dtype="object")), utc=True, errors="coerce").dropna()
        rows.append({"google_place_id": str(pid), "platform": SOURCE_PLATFORMS.get(source, source),
                     "sampled_review_count": len(group),
                     "sample_window_start": dates.min().isoformat() if len(dates) else None,
                     "sample_window_end": dates.max().isoformat() if len(dates) else None,
                     "latest_known_in_sample": dates.max().isoformat() if len(dates) else None,
                     "dated_sample_size": len(dates), "coverage": "text_sample_only",
                     "source": source})
    return rows
