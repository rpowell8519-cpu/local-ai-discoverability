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
_MIN_LEADING_WORD = 3
_MIN_WEBSITE_LABEL = 6
# A page on one of these is not the business's own address, so its first label names the platform.
_SHARED_HOSTS = frozenset({
    "facebook.com", "instagram.com", "linktr.ee", "google.com", "business.site", "wixsite.com",
    "squarespace.com", "wordpress.com", "yell.com", "checkatrade.com", "bark.com", "linkedin.com",
    "x.com", "twitter.com", "tiktok.com", "youtube.com",
})
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


def _shares_most_words(candidate: str, reference: str) -> bool:
    """Two or more meaningful words in common, making up most of the candidate.

    Catches "Plus X Innovation Hub" beside "Plus X Innovation Brighton", where neither name contains
    the other. It only flags; a reviewer decides, and a missed match costs more than an extra flag.
    """

    wanted = [word for word in candidate.split() if word not in _GENERIC_WORDS]
    shared = [word for word in wanted if word in set(reference.split())]
    return len(shared) >= 2 and len(shared) / max(len(wanted), 1) >= 0.6


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
        if _shares_most_words(candidate, reference):
            return "Shares most of its words with the business's name"
    return None


def _leading_word(name: str) -> str:
    """The first word of a normalised name, ignoring a leading "the"; empty when it says nothing."""

    words = [word for word in name.split() if word != "the"]
    if not words or len(words[0]) < _MIN_LEADING_WORD or words[0] in _GENERIC_WORDS:
        return ""
    return words[0]


def _website_label(url: str) -> str:
    """"udrcleaning" for "https://www.udrcleaning.co.uk/"; empty for a page on a shared platform."""

    host = re.sub(r"^[a-z]+://", "", str(url or "").strip().lower()).split("/")[0].split("?")[0].split(":")[0]
    host = host.removeprefix("www.")
    if not host or any(host == shared or host.endswith("." + shared) for shared in _SHARED_HOSTS):
        return ""
    label = re.sub(r"[^a-z0-9]", "", host.split(".")[0])
    return label if len(label) >= _MIN_WEBSITE_LABEL else ""


def _client_reason(candidate: str, full: str, website_labels: Iterable[str]) -> str | None:
    """Extra look-alike tests used only for the business the report is about.

    "UDR Cleaning" beside the listing "UDR Properties" (website udrcleaning.co.uk) shares one short
    word, so the general tests pass it by and the client is reported as absent. These only add a
    question for the reviewer; wrongly reporting a client as absent costs far more than one extra.
    """

    squashed = candidate.replace(" ", "")
    for label in website_labels:
        if squashed == label or (len(squashed) >= _MIN_WEBSITE_LABEL and (squashed in label or label in squashed)):
            return "Matches the business's website address"
    lead = _leading_word(full)
    if lead and lead == _leading_word(candidate):
        return "Starts with the same word as the business's name"
    return None


def find_possible_target_names(
    target_name: str, unresolved: Iterable[Mapping[str, Any]], *,
    client: bool = False, websites: Iterable[str] = (),
) -> list[dict[str, Any]]:
    """List unresolved AI names that may refer to the target business.

    `client` switches on the wider tests for the business the report is about; `websites` are its
    own website addresses.
    """

    full = normalise_name(target_name)
    references = [*brand_core_variants(target_name), full]
    labels = [label for label in dict.fromkeys(_website_label(url) for url in websites) if label] if client else []
    found = []
    for item in unresolved:
        raw = str(item.get("business_name") or "").strip()
        candidate = normalise_name(raw)
        if not candidate or candidate == full:
            continue
        reason = _similarity_reason(candidate, references) or (_client_reason(candidate, full, labels) if client else None)
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
    *,
    websites: Iterable[str] = (),
) -> list[dict[str, Any]]:
    decided = {str(name) for name in [*confirmed, *rejected]}
    return [
        item
        for item in find_possible_target_names(target_name, unresolved, client=True, websites=websites)
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


def display_name(business_name: str) -> str:
    """The name to use in a headline: the brand before any descriptor, else the full name."""

    segments = [segment.strip() for segment in _SEPARATOR.split(str(business_name or "")) if segment.strip()]
    if len(segments) > 1 and _usable_core(normalise_name(segments[0])):
        return segments[0]
    return str(business_name or "").strip()
