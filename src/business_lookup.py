"""Find a business in the database, or say clearly that it is not there.

A report can only be run for a business with a verified Google Place ID, so the first thing
the operator needs is a straight answer to "is it in the database?". Matching is on the
business name, then its town or address, and a pasted Place ID matches exactly. Near misses
are suggested separately and are never treated as a match.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from difflib import SequenceMatcher
from typing import Any

from src.ai_recommendation_intelligence import normalise_name
from src.report_identity import display_name

_PLACE_ID = re.compile(r"[A-Za-z0-9_-]{20,}")


def looks_like_place_id(value: str) -> bool:
    value = str(value or "").strip()
    return bool(_PLACE_ID.fullmatch(value)) and " " not in value


def _haystack(record: Mapping[str, Any]) -> str:
    return " ".join(
        normalise_name(record.get(key)) for key in ("business_name", "city", "address") if record.get(key) is not None
    )


def search_businesses(
    records: Iterable[Mapping[str, Any]], query: str, *, limit: int = 25
) -> list[Mapping[str, Any]]:
    """Businesses matching the query, best first. Empty when there is no match."""

    records = list(records)
    text = str(query or "").strip()
    if not text:
        return []
    if looks_like_place_id(text):
        return [r for r in records if str(r.get("google_place_id")) == text]
    normalised = normalise_name(text)
    tokens = normalised.split()
    if not tokens:
        return []
    scored = []
    for record in records:
        name = normalise_name(record.get("business_name"))
        if normalised == name:
            score = 100
        elif name.startswith(normalised):
            score = 90
        elif normalised in name:
            score = 80
        elif all(token in _haystack(record) for token in tokens):
            score = 70  # every word appears in the name, town or address
        else:
            continue
        scored.append((-score, len(name), name, record))
    scored.sort(key=lambda item: item[:3])
    return [item[3] for item in scored[:limit]]


def near_misses(
    records: Iterable[Mapping[str, Any]], query: str, *, limit: int = 5, cutoff: float = 0.72
) -> list[Mapping[str, Any]]:
    """Businesses whose names resemble the query without matching it, for a "did you mean"."""

    normalised = normalise_name(query)
    if not normalised or looks_like_place_id(query):
        return []
    matched = {id(r) for r in search_businesses(records, query)}
    scored = []
    for record in records:
        if id(record) in matched:
            continue
        names = {normalise_name(record.get("business_name")), normalise_name(display_name(str(record.get("business_name") or "")))}
        best = max((SequenceMatcher(None, normalised, name).ratio() for name in names if name), default=0.0)
        if best >= cutoff:
            scored.append((-best, str(record.get("business_name")), record))
    scored.sort(key=lambda item: item[:2])
    return [item[2] for item in scored[:limit]]
