"""Reviewer-confirmed identity for the business a report is about.

AI answers often use a shorter brand name than the Google Maps listing, for example
"WRAP" for "WRAP- Coworking, Meeting Rooms & Offices". The directory only matches
variants of the full listing name, so those answers stay unresolved and the target is
credited with nothing. Unknown names are never upgraded to verified entities
automatically, so this module finds the look-alikes and leaves the decision to a
reviewer. Decisions are stored in the report revision, not in a new table.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from difflib import SequenceMatcher
from typing import Any

import pandas as pd

from src.ai_recommendation_intelligence import normalise_name

# A hyphen, en/em dash, bar or colon with a space on at least one side, so that
# hyphenated names such as "Coca-Cola" are never split.
_SEPARATOR = re.compile(r"\s+[-–—|:]\s*|[-–—|:]\s+")
_GENERIC_WORDS = frozenset({
    "the", "and", "of", "brighton", "hove", "sussex", "uk", "ltd", "limited",
    "cafe", "bar", "pub", "inn", "restaurant", "salon", "hotel", "shop", "studio",
    "club", "centre", "center", "office", "offices", "coworking", "workspace",
    "services", "group", "company", "co",
})
_MIN_CORE_LENGTH = 4
_SIMILARITY_THRESHOLD = 0.85


class UndecidedTargetNamesError(ValueError):
    """Raised when look-alike names have not been confirmed or rejected."""

    def __init__(self, names: list[dict[str, Any]]):
        self.names = names
        listed = "; ".join(
            f"“{item['name']}” ({int(item.get('recommendations') or 0)} answer(s))"
            for item in names
        )
        super().__init__(
            "The AI answers name businesses that may be this one: "
            + listed
            + ". Confirm or reject each in the report review step before generating, "
            "otherwise the business could be reported as absent from answers where it appeared."
        )


def brand_core_variants(business_name: str) -> list[str]:
    """Return the shorter brand names a long listing name may be known by."""

    full = normalise_name(business_name)
    variants: list[str] = []
    segments = [
        segment for segment in _SEPARATOR.split(str(business_name or "")) if segment.strip()
    ]
    if len(segments) > 1:
        core = normalise_name(segments[0])
        if _usable_core(core) and core != full:
            variants.append(core)
    return [
        item
        for item in dict.fromkeys(
            [*variants, *(v[4:] for v in variants if v.startswith("the "))]
        )
        if _usable_core(item)
    ]


def _usable_core(core: str) -> bool:
    if len(core) < _MIN_CORE_LENGTH:
        return False
    return any(word not in _GENERIC_WORDS for word in core.split())


def _contains_words(haystack: str, needle: str) -> bool:
    return f" {needle} " in f" {haystack} "


def _similarity_reason(candidate: str, references: Iterable[str]) -> str | None:
    for reference in references:
        if candidate == reference:
            return "Matches the business's shorter name"
        if len(reference) >= _MIN_CORE_LENGTH and _contains_words(candidate, reference):
            return "Contains the business's name"
        if len(candidate) >= _MIN_CORE_LENGTH and _contains_words(reference, candidate):
            return "Is part of the business's listing name"
        if SequenceMatcher(None, candidate, reference).ratio() >= _SIMILARITY_THRESHOLD:
            return "Closely resembles the business's name"
    return None


def find_possible_target_names(
    target_name: str, unresolved: Iterable[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """List unresolved AI names that may refer to the target business."""

    full = normalise_name(target_name)
    references = [*brand_core_variants(target_name), full]
    found = []
    for item in unresolved:
        raw = str(item.get("business_name") or "").strip()
        candidate = normalise_name(raw)
        if not candidate or candidate == full:
            continue
        reason = _similarity_reason(candidate, references)
        if reason:
            found.append(
                {
                    "name": raw,
                    "recommendations": int(item.get("recommendations") or 0),
                    "reason": reason,
                }
            )
    return sorted(found, key=lambda entry: (-entry["recommendations"], entry["name"]))


def undecided_target_names(
    target_name: str,
    unresolved: Iterable[Mapping[str, Any]],
    confirmed: Iterable[str],
    rejected: Iterable[str],
) -> list[dict[str, Any]]:
    decided = {str(name) for name in [*confirmed, *rejected]}
    return [
        item
        for item in find_possible_target_names(target_name, unresolved)
        if item["name"] not in decided
    ]


def assert_target_names_decided(
    target_name: str,
    unresolved: Iterable[Mapping[str, Any]],
    confirmed: Iterable[str],
    rejected: Iterable[str],
) -> None:
    undecided = undecided_target_names(target_name, unresolved, confirmed, rejected)
    if undecided:
        raise UndecidedTargetNamesError(undecided)


def target_name_adjudications(
    *, target_google_place_id: str, target_business_name: str, confirmed: Iterable[str]
) -> dict[str, dict[str, Any]]:
    """Slot adjudications crediting the confirmed raw names to the target."""

    return {
        str(name): {
            "google_place_id": str(target_google_place_id),
            "business_name": str(target_business_name),
            "resolution_method": "reviewer_confirmed_target_name",
        }
        for name in confirmed
        if str(name).strip()
    }


def confirmed_alias_frame(
    *, target_google_place_id: str, target_business_name: str, confirmed: Iterable[str]
) -> pd.DataFrame:
    """Alias rows, shaped like business_entity_aliases, for reviewer-confirmed names."""

    return pd.DataFrame(
        [
            {
                "alias_name": str(name),
                "google_place_id": str(target_google_place_id),
                "canonical_business_name": str(target_business_name),
                "alias_type": "reviewer_confirmed",
                "source_note": "Confirmed by the report reviewer as this business.",
                "source_url": None,
            }
            for name in confirmed
            if str(name).strip()
        ],
        columns=[
            "alias_name", "google_place_id", "canonical_business_name",
            "alias_type", "source_note", "source_url",
        ],
    )
