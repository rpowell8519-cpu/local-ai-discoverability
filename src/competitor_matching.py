from __future__ import annotations

import json
import math
from typing import Any

import pandas as pd

from src.taxonomy import FORMAT_RELATIONSHIPS, GROUP_LABELS, GROUP_RELATIONSHIPS


DEFAULT_WEIGHTS = {
    "group_format": 0.20,
    "traits": 0.20,
    "about_attributes": 0.25,
    "proximity": 0.15,
    "prominence": 0.10,
    "customer_journey": 0.10,
}

VERTICAL_WEIGHTS = {
    "coffee_cafes": {
        **DEFAULT_WEIGHTS,
        "proximity": 0.20,
        "customer_journey": 0.05,
    },
    "hair_services": {
        **DEFAULT_WEIGHTS,
        "traits": 0.30,
        "about_attributes": 0.15,
    },
}

ATTRIBUTE_PREFIX_WEIGHTS = {
    "offerings.": 1.50,
    "highlights.": 1.50,
    "service_options.": 1.20,
    "dining_options.": 1.20,
    "planning.": 1.10,
    "atmosphere.": 1.00,
    "crowd.": 0.80,
    "pets.": 0.80,
    "amenities.": 0.60,
    "accessibility.": 0.40,
    "parking.": 0.30,
    "payments.": 0.10,
    "other.": 0.20,
}


def _missing(value: Any) -> bool:
    return value is None or (
        isinstance(value, float) and math.isnan(value)
    )


def parse_jsonish(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if _missing(value):
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return default
    return default


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return default if _missing(value) else float(value)
    except (TypeError, ValueError):
        return default


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return bool(value)


def normalise_record(record: dict[str, Any]) -> dict[str, Any]:
    output = dict(record)
    output["traits"] = parse_jsonish(output.get("traits"), [])
    output["secondary_groups"] = parse_jsonish(
        output.get("secondary_groups"), []
    )
    output["about_features"] = parse_jsonish(
        output.get("about_features"), {}
    )
    output["classification_reasons"] = parse_jsonish(
        output.get("classification_reasons"), []
    )
    return output


def group_score(target_group: str, candidate_group: str) -> float:
    if target_group == candidate_group:
        return 1.0
    return GROUP_RELATIONSHIPS.get(target_group, {}).get(
        candidate_group, 0.0
    )


def format_score(
    target_format: str,
    candidate_format: str,
    target_group: str,
    candidate_group: str,
) -> float:
    if target_format == candidate_format:
        return 1.0

    direct = FORMAT_RELATIONSHIPS.get(target_format, {}).get(
        candidate_format
    )
    if direct is not None:
        return direct

    reverse = FORMAT_RELATIONSHIPS.get(candidate_format, {}).get(
        target_format
    )
    if reverse is not None:
        return reverse

    if target_group == candidate_group:
        return 0.65

    return group_score(target_group, candidate_group) * 0.50


def combined_group_format(
    target: dict[str, Any],
    candidate: dict[str, Any],
) -> float:
    tg = str(target.get("primary_group") or "other")
    cg = str(candidate.get("primary_group") or "other")
    gs = group_score(tg, cg)
    fs = format_score(
        str(target.get("business_format") or ""),
        str(candidate.get("business_format") or ""),
        tg,
        cg,
    )
    return gs * 0.60 + fs * 0.40


def jaccard(first: set[str], second: set[str]) -> float:
    if not first or not second:
        return 0.0
    return len(first & second) / len(first | second)


def compare_traits(
    target: dict[str, Any],
    candidate: dict[str, Any],
) -> tuple[float, list[str], list[str], list[str]]:
    target_traits = {str(item) for item in target.get("traits", [])}
    candidate_traits = {
        str(item) for item in candidate.get("traits", [])
    }

    return (
        jaccard(target_traits, candidate_traits),
        sorted(target_traits & candidate_traits),
        sorted(target_traits - candidate_traits),
        sorted(candidate_traits - target_traits),
    )


def attribute_weight(path: str) -> float:
    for prefix, weight in ATTRIBUTE_PREFIX_WEIGHTS.items():
        if path.startswith(prefix):
            return weight
    return 0.50


def readable_path(path: str) -> str:
    return " → ".join(
        section.replace("_", " ").title()
        for section in path.split(".")
    )


def compare_about(
    target: dict[str, Any],
    candidate: dict[str, Any],
) -> tuple[float, list[str], list[str]]:
    target_about = {
        str(key): as_bool(value)
        for key, value in target.get("about_features", {}).items()
    }
    candidate_about = {
        str(key): as_bool(value)
        for key, value in candidate.get("about_features", {}).items()
    }

    paths = sorted(set(target_about) & set(candidate_about))
    if not paths:
        return 0.0, [], []

    earned = 0.0
    possible = 0.0
    shared_true: list[str] = []
    conflicts: list[str] = []

    for path in paths:
        weight = attribute_weight(path)
        possible += weight
        tv = target_about[path]
        cv = candidate_about[path]

        if tv is True and cv is True:
            earned += weight
            shared_true.append(readable_path(path))
        elif tv != cv:
            conflicts.append(readable_path(path))
        else:
            earned += weight * 0.10

    return earned / possible, shared_true, conflicts


def haversine_miles(
    lat1: Any,
    lon1: Any,
    lat2: Any,
    lon2: Any,
) -> float | None:
    try:
        lat1, lon1, lat2, lon2 = map(
            float, [lat1, lon1, lat2, lon2]
        )
    except (TypeError, ValueError):
        return None

    radius = 3958.8
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)

    a = (
        math.sin(dp / 2) ** 2
        + math.cos(p1)
        * math.cos(p2)
        * math.sin(dl / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(a))


def prominence(
    target: dict[str, Any],
    candidate: dict[str, Any],
) -> float:
    tr = safe_float(target.get("reviews"))
    cr = safe_float(candidate.get("reviews"))
    t_rating = safe_float(target.get("rating"))
    c_rating = safe_float(candidate.get("rating"))
    tp = safe_float(target.get("photos_count"))
    cp = safe_float(candidate.get("photos_count"))

    review_similarity = max(
        0.0,
        1.0 - abs(math.log1p(tr) - math.log1p(cr)) / 3.0,
    )
    rating_similarity = max(
        0.0, 1.0 - abs(t_rating - c_rating) / 1.5
    )
    photo_similarity = max(
        0.0,
        1.0 - abs(math.log1p(tp) - math.log1p(cp)) / 3.0,
    )

    return (
        review_similarity * 0.50
        + rating_similarity * 0.35
        + photo_similarity * 0.15
    )


def has_any(record: dict[str, Any], fields: list[str]) -> bool:
    return any(
        bool(str(record.get(field) or "").strip())
        for field in fields
    )


def journey(
    target: dict[str, Any],
    candidate: dict[str, Any],
) -> float:
    scores = [
        1.0
        if has_any(target, ["website", "site"])
        == has_any(candidate, ["website", "site"])
        else 0.0,
        1.0
        if has_any(
            target,
            ["booking_appointment_link", "reservation_links"],
        )
        == has_any(
            candidate,
            ["booking_appointment_link", "reservation_links"],
        )
        else 0.0,
    ]

    target_res = target.get("about_features", {}).get(
        "planning.accepts_reservations"
    )
    candidate_res = candidate.get("about_features", {}).get(
        "planning.accepts_reservations"
    )

    if target_res is not None and candidate_res is not None:
        scores.append(
            1.0
            if as_bool(target_res) == as_bool(candidate_res)
            else 0.0
        )

    return sum(scores) / len(scores)


def candidate_allowed(
    target: dict[str, Any],
    candidate: dict[str, Any],
    scope: str,
) -> bool:
    tg = str(target.get("primary_group") or "other")
    cg = str(candidate.get("primary_group") or "other")
    gs = group_score(tg, cg)
    fs = format_score(
        str(target.get("business_format") or ""),
        str(candidate.get("business_format") or ""),
        tg,
        cg,
    )

    if scope == "Direct formats only":
        return tg == cg and fs >= 0.75
    if scope == "Direct and adjacent formats":
        return tg == cg or gs >= 0.50
    if scope == "Broad market alternatives":
        return tg == cg or gs >= 0.20
    return tg == cg


def score_competitor(
    target: dict[str, Any],
    candidate: dict[str, Any],
    max_distance_miles: float,
) -> dict[str, Any] | None:
    distance = haversine_miles(
        target.get("latitude"),
        target.get("longitude"),
        candidate.get("latitude"),
        candidate.get("longitude"),
    )

    if distance is not None and distance > max_distance_miles:
        return None

    group_format = combined_group_format(target, candidate)
    trait_result = compare_traits(target, candidate)
    traits_score, shared_traits, target_only, candidate_only = (
        trait_result
    )
    about_score, shared_about, conflicts = compare_about(
        target, candidate
    )
    proximity = (
        max(0.0, 1.0 - distance / max_distance_miles)
        if distance is not None
        else 0.0
    )
    prominence_score = prominence(target, candidate)
    journey_score = journey(target, candidate)

    target_group = str(target.get("primary_group") or "other")
    weights = VERTICAL_WEIGHTS.get(
        target_group, DEFAULT_WEIGHTS
    )

    components = {
        "Group and format": group_format,
        "Traits": traits_score,
        "About attributes": about_score,
        "Proximity": proximity,
        "Prominence": prominence_score,
        "Customer journey": journey_score,
    }

    total = (
        group_format * weights["group_format"]
        + traits_score * weights["traits"]
        + about_score * weights["about_attributes"]
        + proximity * weights["proximity"]
        + prominence_score * weights["prominence"]
        + journey_score * weights["customer_journey"]
    ) * 100

    reasons = [
        "same canonical group"
        if target.get("primary_group")
        == candidate.get("primary_group")
        else "related canonical group"
    ]

    if (
        target.get("business_format")
        == candidate.get("business_format")
    ):
        reasons.append("same business format")

    if shared_traits:
        reasons.append(
            "shared traits: " + ", ".join(shared_traits[:5])
        )

    if shared_about:
        reasons.append(
            "shared attributes: " + ", ".join(shared_about[:5])
        )

    if distance is not None:
        reasons.append(f"{distance:.1f} miles away")

    return {
        "score": round(total, 1),
        "distance": round(distance, 2)
        if distance is not None
        else None,
        "components": {
            key: round(value * 100, 1)
            for key, value in components.items()
        },
        "shared_traits": shared_traits,
        "target_only_traits": target_only,
        "candidate_only_traits": candidate_only,
        "shared_about": shared_about,
        "conflicts": conflicts,
        "reasons": reasons,
    }


def rank_competitors(
    businesses: pd.DataFrame,
    target_place_id: str,
    max_distance_miles: float = 5.0,
    candidate_scope: str = "Direct and adjacent formats",
) -> tuple[dict[str, Any], pd.DataFrame]:
    records = [
        normalise_record(record)
        for record in businesses.to_dict("records")
    ]

    target = next(
        (
            record
            for record in records
            if str(record.get("google_place_id"))
            == str(target_place_id)
        ),
        None,
    )

    if target is None:
        raise ValueError("Target business not found.")

    output = []

    for candidate in records:
        if str(candidate.get("google_place_id")) == str(
            target_place_id
        ):
            continue

        if not candidate_allowed(
            target, candidate, candidate_scope
        ):
            continue

        result = score_competitor(
            target, candidate, max_distance_miles
        )
        if result is None:
            continue

        output.append(
            {
                "google_place_id": candidate.get(
                    "google_place_id"
                ),
                "Business": candidate.get("business_name"),
                "Score": result["score"],
                "Distance (miles)": result["distance"],
                "Canonical group": GROUP_LABELS.get(
                    str(candidate.get("primary_group")),
                    candidate.get("primary_group"),
                ),
                "Format": candidate.get("business_format"),
                "Traits": ", ".join(
                    candidate.get("traits", [])
                ),
                "Rating": safe_float(candidate.get("rating")),
                "Reviews": int(
                    safe_float(candidate.get("reviews"))
                ),
                "Why matched": "; ".join(result["reasons"]),
                "Components": result["components"],
                "Shared traits": result["shared_traits"],
                "Target-only traits": result[
                    "target_only_traits"
                ],
                "Candidate-only traits": result[
                    "candidate_only_traits"
                ],
                "Shared attributes": result["shared_about"],
                "Different attributes": result["conflicts"],
                "Website": candidate.get("website")
                or candidate.get("site"),
                "Google Maps": candidate.get("location_link")
                or candidate.get("google_maps_url"),
            }
        )

    ranked = pd.DataFrame(output)
    if ranked.empty:
        return target, ranked

    ranked = ranked.sort_values(
        ["Score", "Reviews"],
        ascending=[False, False],
    ).reset_index(drop=True)
    ranked.insert(0, "Rank", range(1, len(ranked) + 1))
    return target, ranked
