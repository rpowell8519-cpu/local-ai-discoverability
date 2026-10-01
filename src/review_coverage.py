"""Review collection coverage; a linked profile is not a completed review check."""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any
from urllib.parse import urlsplit

import pandas as pd

from src.review_ingestion import SOURCE, SOURCE_LABELS, SOURCE_TRIPADVISOR, SOURCE_YELP

PLATFORM_SOURCES = {"google": SOURCE, "yelp": SOURCE_YELP, "tripadvisor": SOURCE_TRIPADVISOR}
COVERAGE_VERSION = 1


def has_legacy_presence_action(recommendations) -> bool:
    """Old sample-as-absence actions must be reviewed again before a new report is issued."""
    return any(str(item.get("id") or "").startswith("reviews:platform-") for item in recommendations or [])


def empty_text_check(*, source_url: str, checked_at: str, note: str) -> dict[str, Any]:
    """An operator checked a named source and found no usable text, not no profile/reviews."""
    parsed = urlsplit(source_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("A public profile URL is required for a completed check")
    checked = date.fromisoformat(checked_at)
    if checked > date.today():
        raise ValueError("The check date cannot be in the future")
    if not note.strip():
        raise ValueError("Record what was checked and why no usable review text was found")
    return {"status": "checked", "found_count": 0, "source_url": source_url,
            "checked_at": checked.isoformat(), "note": note.strip(), "method": "operator_text_check"}


def build_review_coverage(
    *, business_names: Mapping[str, str], reviews: pd.DataFrame,
    platform_links: pd.DataFrame | None = None,
    checks: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Count saved text per source and preserve explicit zero checks. Unknown never becomes zero."""
    links = {}
    if platform_links is not None and not platform_links.empty:
        for row in platform_links.to_dict("records"):
            source = PLATFORM_SOURCES.get(str(row.get("platform")))
            if source:
                links[(str(row["google_place_id"]), source)] = str(row.get("external_url") or "")
    rows = []
    for pid, name in business_names.items():
        for source, label in SOURCE_LABELS.items():
            sample = pd.DataFrame()
            if not reviews.empty and "source" in reviews.columns:
                sample = reviews[(reviews["google_place_id"].astype(str) == str(pid)) & (reviews["source"] == source)]
                sample = sample[sample["review_text"].fillna("").astype(str).str.strip().ne("")]
                if "review_id" in sample.columns:
                    sample = sample.drop_duplicates("review_id")
            count = len(sample)
            check = dict((checks or {}).get(str(pid), {}).get(source) or {})
            valid_check = None
            if check.get("status") == "checked" and check.get("found_count") == 0:
                try:
                    valid_check = empty_text_check(source_url=str(check.get("source_url") or ""),
                                                  checked_at=str(check.get("checked_at") or ""),
                                                  note=str(check.get("note") or ""))
                except ValueError:
                    pass  # incomplete historical decisions cannot prove a completed check
            linked_url = links.get((str(pid), source))
            if valid_check and linked_url and linked_url != valid_check["source_url"]:
                valid_check = None  # a check of a replaced profile cannot establish this profile's coverage
            url = linked_url or (valid_check or {}).get("source_url")
            status = "checked" if count or valid_check else "not_checked"
            rows.append({
                "version": COVERAGE_VERSION, "google_place_id": str(pid), "business_name": name,
                "source": source, "platform": label, "profile_status": "linked" if url else "unknown",
                "source_url": url, "status": status, "sampled_review_count": count,
                "found_count": count if count else (0 if valid_check else None),
                "method": "saved_text_sample" if count else ((valid_check or {}).get("method")),
                "checked_at": None if count else (valid_check or {}).get("checked_at"),
                "note": "Saved review text; not the platform's published total." if count else (
                    (valid_check or {}).get("note") or "No completed review-text check recorded."
                ),
            })
    return rows
