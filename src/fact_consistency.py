"""Compare contextual observations, without choosing a source as canonical truth."""
from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Mapping

from src.proposition_catalog import label_key
from src.site_checks import normalise_postcode, normalise_uk_phone

VERSION = "fact-comparison-v1"


def _clock(value: str) -> str | None:
    match = re.fullmatch(r"\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*", value, re.I)
    if not match:
        return None
    hour, minute, suffix = int(match[1]), int(match[2] or 0), (match[3] or "").lower()
    if minute > 59 or (suffix and not 1 <= hour <= 12) or (not suffix and hour > 23):
        return None
    if suffix:
        hour = hour % 12 + (12 if suffix == "pm" else 0)
    return f"{hour:02}:{minute:02}"


def normalize_fact(field: str, value: Any, *, aliases: Mapping[str, str] | None = None) -> Any:
    """Only normalize known equivalences. Unsupported/ambiguous values stay unknown."""
    if value is None or value == "":
        return None
    if field == "phone":
        return normalise_uk_phone(str(value))
    if field == "postcode":
        return normalise_postcode(str(value))
    if field == "service_name":
        key = label_key(str(value))
        return (aliases or {}).get(key, key)
    if field == "price":
        # Service, currency and fixed/from qualifiers are part of the fact, not decorations.
        if not isinstance(value, dict) or not value.get("service"):
            return None
        match = re.fullmatch(r"\s*(from\s+)?([£$€])\s*(\d+(?:\.\d{1,2})?)\s*", str(value.get("amount", "")), re.I)
        if not match:
            return None
        return (label_key(value["service"]), match[2], str(Decimal(match[3]).normalize()), bool(match[1]))
    if field == "hours":
        if not isinstance(value, dict) or not value.get("timezone") or not value.get("day"):
            return None
        # Exceptions and overnight interpretation must be explicit; no guessing from prose.
        start, end = _clock(str(value.get("opens", ""))), _clock(str(value.get("closes", "")))
        if not start or not end or end <= start:
            return None
        return (label_key(value["day"]), value["timezone"], start, end, value.get("exception_date"))
    if field in {"business_name", "address", "category"}:
        return label_key(str(value))
    return None


def compare_fact(field: str, reference: list[Any], observed: list[Any], *, collection_status: str,
                 complete: bool, applicable: bool = True, aliases=None) -> dict[str, str]:
    def result(state, reason):
        return {"state": state, "reason": reason, "comparison_version": VERSION}
    if not applicable:
        return result("NOT_APPLICABLE", "This field does not apply to this source.")
    if collection_status not in {"COLLECTED", "CHECKED_EMPTY"}:
        return result("UNKNOWN", "No completed source observation is available.")
    if not reference:
        return result("UNKNOWN", "The comparison reference is unknown; no source is assumed true.")
    left = [normalize_fact(field, v, aliases=aliases) for v in reference]
    right = [normalize_fact(field, v, aliases=aliases) for v in observed]
    if any(v is None for v in left + right):
        return result("UNKNOWN", "At least one value could not be normalized safely.")
    if not observed:
        return result("MISSING" if complete else "UNKNOWN", "No value found within the checked scope." if complete else "Partial capture cannot establish a missing value.")
    # Sets with several alternatives are not resolved by taking the first intersection.
    if len(set(left)) != 1 or len(set(right)) != 1:
        return result("UNKNOWN", "Multiple values require operator review.")
    if left[0] == right[0]:
        return result("MATCH" if reference == observed else "SEMANTIC_MATCH", "Same contextual value.")
    if field == "price" and left[0][:3] == right[0][:3]:
        return result("UNKNOWN", "Fixed and 'from' prices are not equivalent or necessarily conflicting.")
    if field in {"price", "hours"} and left[0][:2] != right[0][:2]:
        return result("UNKNOWN", "Values describe different services, currencies, days or timezones.")
    if field == "hours" and left[0][-1] != right[0][-1]:
        return result("UNKNOWN", "Opening-hour exceptions differ.")
    if not complete:
        return result("UNKNOWN", "A partial capture may omit the matching reference value.")
    return result("CONFLICT", "Different values within comparable scope; neither source is selected as truth.")
