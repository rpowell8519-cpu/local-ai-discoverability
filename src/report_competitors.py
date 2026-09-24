from __future__ import annotations

import math
import re
from difflib import SequenceMatcher
from typing import Any, Iterable, Mapping


# Walk-in businesses whose customers do not travel far: salons, cafes, pubs and
# their close peers. Everything else uses the wider default until decided otherwise.
# A nursery is chosen even more locally than a salon (daily drop-off), so it uses the
# same tight radius rather than the wide default meant for something like a workspace.
LOCAL_WALK_IN_GROUPS = frozenset({
    "bar", "bars", "cafe", "cafes", "food_drink", "hair_beauty",
    "hospitality_food_drink", "pub", "pubs", "restaurant", "restaurants",
    "salon", "salons", "childcare_nurseries",
})
WALK_IN_CATCHMENT_MILES = 3.0
DEFAULT_CATCHMENT_MILES = 15.0


def normalise_business_name(value: str) -> str:
    words = re.findall(r"[a-z0-9]+", str(value or "").casefold())
    noise = {"limited", "ltd", "plc", "the", "uk"}
    return " ".join(word for word in words if word not in noise)


def catchment_radius_miles(primary_group: str, business_format: str = "") -> float:
    group = normalise_business_name(primary_group).replace(" ", "_")
    format_name = normalise_business_name(business_format).replace(" ", "_")
    if group in LOCAL_WALK_IN_GROUPS or format_name in {"venue", "fixed_location"}:
        return WALK_IN_CATCHMENT_MILES
    return DEFAULT_CATCHMENT_MILES


def _coordinate(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def distance_miles(first: Mapping[str, Any], second: Mapping[str, Any]) -> float | None:
    lat1, lon1 = _coordinate(first.get("latitude")), _coordinate(first.get("longitude"))
    lat2, lon2 = _coordinate(second.get("latitude")), _coordinate(second.get("longitude"))
    if None in {lat1, lon1, lat2, lon2}:
        return None
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlambda = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 3958.8 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def classify_location(
    candidate: Mapping[str, Any], *, target: Mapping[str, Any],
    primary_group: str, business_format: str = "", service_areas: Iterable[str] = (),
    radius_miles: float | None = None,
) -> dict[str, Any]:
    radius = float(radius_miles or catchment_radius_miles(primary_group, business_format))
    distance = distance_miles(target, candidate)
    location_text = " ".join(
        str(candidate.get(key) or "") for key in ("city", "address")
    ).casefold()
    named_area = next(
        (str(area) for area in service_areas if str(area).strip() and str(area).casefold() in location_text),
        None,
    )
    if named_area:
        classification = "local"
        reason = f"Located in the stated service area: {named_area}."
    elif distance is None:
        classification = "unknown"
        reason = "Location could not be checked automatically."
    elif distance <= radius:
        classification = "local"
        reason = f"Approximately {distance:.0f} miles from the target, within the {radius:.0f}-mile catchment."
    elif distance <= radius * 1.5:
        classification = "wider_area"
        reason = f"Approximately {distance:.0f} miles away, just beyond the expected {radius:.0f}-mile catchment."
    else:
        classification = "outside"
        reason = f"Approximately {distance:.0f} miles away, outside the expected {radius:.0f}-mile catchment."
    return {
        "location_classification": classification,
        "location_reason": reason,
        "distance_miles": round(distance, 1) if distance is not None else None,
        "catchment_radius_miles": radius,
    }


def match_owner_competitors(
    owner_names: Iterable[str], businesses: Iterable[Mapping[str, Any]],
    recommendation_counts: Mapping[str, int] | None = None,
) -> list[dict[str, Any]]:
    candidates = [dict(item) for item in businesses]
    counts = recommendation_counts or {}
    matches: list[dict[str, Any]] = []
    for owner_name in owner_names:
        wanted = normalise_business_name(owner_name)
        scored = sorted(
            ((SequenceMatcher(None, wanted, normalise_business_name(item.get("business_name", ""))).ratio(), item)
             for item in candidates if normalise_business_name(item.get("business_name", ""))),
            key=lambda pair: pair[0], reverse=True,
        )
        score, match = scored[0] if scored else (0.0, {})
        matched_name = normalise_business_name(match.get("business_name", ""))
        exact = bool(wanted and wanted == matched_name)
        descriptive_suffix = bool(wanted and matched_name and all(word in matched_name.split() for word in wanted.split()))
        accepted = exact or descriptive_suffix or score >= 0.82
        place_id = str(match.get("google_place_id") or "") if accepted else ""
        recommendations = int(counts.get(place_id, 0)) if place_id else 0
        matches.append({
            "owner_name": str(owner_name),
            "google_place_id": place_id or None,
            "business_name": str(match.get("business_name") or owner_name) if accepted else str(owner_name),
            "match_status": "matched" if accepted else "needs_confirmation",
            "match_score": round(score, 3),
            "recommendations": recommendations,
            "visibility_status": (
                f"Recommended {recommendations} time{'s' if recommendations != 1 else ''}"
                if recommendations else "Not recommended in this benchmark"
            ) if accepted else "Identity needs confirmation",
        })
    return matches


def resolve_run_location(service_areas: Iterable[str], city: Any) -> str:
    """Where the AI providers should assume the customer is searching from.

    The owner's stated service areas take priority, then the business's own city. There is
    deliberately no default: a wrong location silently skews every result, so an empty
    answer means the run must not start.
    """

    areas = [str(area).strip() for area in service_areas if str(area).strip()]
    if areas:
        return ", ".join(areas)
    if city is None or (isinstance(city, float) and city != city):
        return ""
    return str(city).strip()


MAX_COMPARISON_BUSINESSES = 7  # the business itself plus up to seven others makes eight in all
OWNER_SHARE_OF_COMPARISONS = 4  # at most this many of the seven are chosen because the owner named them


def select_comparison_set(
    owner_named: Iterable[str],
    most_visible: Iterable[str],
    *,
    limit: int = MAX_COMPARISON_BUSINESSES,
    owner_share: int = OWNER_SHARE_OF_COMPARISONS,
) -> list[str]:
    """A default comparison set that mixes the businesses the owner named with the most visible ones.

    Owner-named businesses come first, up to owner_share, because the owner asked about them and a
    business the AI never recommended is still a useful comparison. The rest are the most visible
    businesses in the AI answers. If either group runs short the other fills the gap, and nothing
    appears twice. The reviewer can change the result.
    """

    owner = list(dict.fromkeys(str(item) for item in owner_named if str(item)))
    visible = list(dict.fromkeys(str(item) for item in most_visible if str(item)))
    chosen = owner[: max(0, min(owner_share, limit))]
    for item in visible:
        if len(chosen) >= limit:
            break
        if item not in chosen:
            chosen.append(item)
    for item in owner:
        if len(chosen) >= limit:
            break
        if item not in chosen:
            chosen.append(item)
    return chosen[:limit]
