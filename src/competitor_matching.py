from __future__ import annotations

import json
import math
import re
from typing import Any

import pandas as pd


SERVICE_KEYWORDS = {
    "General hairdressing": [
        "hairdresser",
        "hair salon",
        "hair stylist",
        "hair studio",
    ],
    "Hair colour": [
        "hair colour",
        "hair color",
        "colourist",
        "colorist",
        "colouring",
        "coloring",
    ],
    "Balayage": ["balayage"],
    "Blonde": ["blonde", "blonding"],
    "Highlights": ["highlights", "foils"],
    "Colour correction": [
        "colour correction",
        "color correction",
    ],
    "Creative colour": [
        "creative colour",
        "creative color",
        "vivid colour",
        "vivid color",
    ],
    "Hair extensions": [
        "hair extension",
        "extensions",
    ],
    "Bridal hair": [
        "bridal",
        "wedding hair",
    ],
    "Men's hair": [
        "men's hair",
        "mens hair",
        "male grooming",
    ],
    "Children's hair": [
        "good for kids",
        "good for children",
        "children's hair",
        "childrens hair",
        "kids haircut",
    ],
    "Curly hair": [
        "curly",
        "curl specialist",
        "curls",
    ],
    "Afro-textured hair": [
        "afro",
        "textured hair",
        "coily",
    ],
    "Hair systems": [
        "hair system",
        "hair replacement",
        "toupee",
    ],
    "Barbering": [
        "barber shop",
        "barbershop",
        "barbering",
    ],
    "Beauty services": [
        "beauty salon",
        "beautician",
    ],
}


def _is_missing(value: Any) -> bool:
    if value is None:
        return True

    if isinstance(value, float):
        return math.isnan(value)

    return False


def as_text(value: Any) -> str:
    if _is_missing(value):
        return ""

    return str(value).strip().lower()


def parse_jsonish(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value

    if _is_missing(value):
        return None

    if isinstance(value, str):
        cleaned = value.strip()

        if not cleaned:
            return None

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return value

    return value


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if _is_missing(value):
            return default

        return float(value)
    except (TypeError, ValueError):
        return default


def normalise_phrase(value: Any) -> str:
    text = as_text(value)
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9\s'-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def split_listish(value: Any) -> set[str]:
    parsed = parse_jsonish(value)

    if isinstance(parsed, list):
        values = parsed
    elif isinstance(parsed, dict):
        values = list(parsed.keys())
    elif isinstance(parsed, str):
        values = re.split(r"[,;|]", parsed)
    else:
        values = []

    return {
        normalise_phrase(item)
        for item in values
        if normalise_phrase(item)
    }


def flatten_true_attribute_keys(
    value: Any,
    prefix: str = "",
) -> set[str]:
    parsed = parse_jsonish(value)
    output: set[str] = set()

    if not isinstance(parsed, dict):
        return output

    for key, nested_value in parsed.items():
        combined_key = normalise_phrase(
            f"{prefix} {key}".strip()
        )

        if isinstance(nested_value, dict):
            output |= flatten_true_attribute_keys(
                nested_value,
                combined_key,
            )
        elif nested_value is True:
            output.add(combined_key)
        elif (
            isinstance(nested_value, str)
            and nested_value.lower() in {"true", "yes"}
        ):
            output.add(combined_key)

    return output


def combined_business_text(record: dict[str, Any]) -> str:
    fields = [
        "category",
        "type",
        "subtypes",
        "description",
        "reviews_tags",
        "about",
        "located_in",
        "range",
        "prices",
    ]

    return " ".join(
        as_text(record.get(field))
        for field in fields
    )


def extract_service_terms(
    record: dict[str, Any],
) -> set[str]:
    combined = combined_business_text(record)

    return {
        label
        for label, phrases in SERVICE_KEYWORDS.items()
        if any(phrase in combined for phrase in phrases)
    }


def broad_business_format(
    record: dict[str, Any],
) -> str:
    primary = " ".join(
        as_text(record.get(field))
        for field in ["category", "type"]
    )
    all_types = " ".join(
        as_text(record.get(field))
        for field in ["category", "type", "subtypes"]
    )

    if "barber shop" in primary or primary.strip() == "barber":
        return "Barber"

    if (
        "hair extension" in primary
        and "hairdresser" not in primary
        and "hair salon" not in primary
    ):
        return "Specialist"

    if (
        "beauty salon" in primary
        and "hairdresser" not in all_types
        and "hair salon" not in all_types
        and "hair extension" not in all_types
    ):
        return "Beauty"

    return "Salon"


def is_eligible_hair_business(
    record: dict[str, Any],
) -> bool:
    status = as_text(record.get("business_status"))

    if status and status != "operational":
        return False

    business_types = " ".join(
        as_text(record.get(field))
        for field in ["category", "type", "subtypes"]
    )

    positive_terms = [
        "hairdresser",
        "hair salon",
        "hair stylist",
        "hair extension",
        "colourist",
        "colorist",
        "barber shop",
        "barbershop",
    ]

    return any(
        term in business_types
        for term in positive_terms
    )


def jaccard_similarity(
    first: set[str],
    second: set[str],
) -> float:
    if not first or not second:
        return 0.0

    return len(first & second) / len(first | second)


def haversine_miles(
    latitude_1: Any,
    longitude_1: Any,
    latitude_2: Any,
    longitude_2: Any,
) -> float | None:
    try:
        lat_1 = float(latitude_1)
        lon_1 = float(longitude_1)
        lat_2 = float(latitude_2)
        lon_2 = float(longitude_2)
    except (TypeError, ValueError):
        return None

    earth_radius_miles = 3958.8

    phi_1 = math.radians(lat_1)
    phi_2 = math.radians(lat_2)
    delta_phi = math.radians(lat_2 - lat_1)
    delta_lambda = math.radians(lon_2 - lon_1)

    value = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi_1)
        * math.cos(phi_2)
        * math.sin(delta_lambda / 2) ** 2
    )

    return (
        2
        * earth_radius_miles
        * math.asin(math.sqrt(value))
    )


def _presence(record: dict[str, Any], field: str) -> bool:
    return bool(as_text(record.get(field)))


def _has_booking(record: dict[str, Any]) -> bool:
    return any(
        _presence(record, field)
        for field in [
            "booking_appointment_link",
            "reservation_links",
        ]
    )


def _uses_appointments(
    record: dict[str, Any],
) -> bool:
    attributes = flatten_true_attribute_keys(
        record.get("about")
    )

    return any(
        "appointment" in attribute
        for attribute in attributes
    )


def _prominence_similarity(
    target: dict[str, Any],
    candidate: dict[str, Any],
) -> float:
    target_reviews = safe_float(target.get("reviews"))
    candidate_reviews = safe_float(
        candidate.get("reviews")
    )

    target_rating = safe_float(target.get("rating"))
    candidate_rating = safe_float(
        candidate.get("rating")
    )

    target_photos = safe_float(
        target.get("photos_count")
    )
    candidate_photos = safe_float(
        candidate.get("photos_count")
    )

    review_similarity = max(
        0.0,
        1.0
        - abs(
            math.log1p(target_reviews)
            - math.log1p(candidate_reviews)
        )
        / 3.0,
    )

    rating_similarity = max(
        0.0,
        1.0
        - abs(target_rating - candidate_rating)
        / 1.5,
    )

    photo_similarity = max(
        0.0,
        1.0
        - abs(
            math.log1p(target_photos)
            - math.log1p(candidate_photos)
        )
        / 3.0,
    )

    return (
        review_similarity * 0.50
        + rating_similarity * 0.35
        + photo_similarity * 0.15
    )


def _journey_similarity(
    target: dict[str, Any],
    candidate: dict[str, Any],
) -> float:
    website_match = (
        _presence(target, "website")
        == _presence(candidate, "website")
    )
    booking_match = (
        _has_booking(target)
        == _has_booking(candidate)
    )
    appointment_match = (
        _uses_appointments(target)
        == _uses_appointments(candidate)
    )

    return (
        (1.0 if website_match else 0.0) * 0.35
        + (1.0 if booking_match else 0.0) * 0.40
        + (1.0 if appointment_match else 0.0) * 0.25
    )


def _format_similarity(
    target: dict[str, Any],
    candidate: dict[str, Any],
) -> float:
    target_format = broad_business_format(target)
    candidate_format = broad_business_format(candidate)

    if target_format == candidate_format:
        return 1.0

    pair_scores = {
        frozenset({"Salon", "Specialist"}): 0.75,
        frozenset({"Salon", "Beauty"}): 0.40,
        frozenset({"Salon", "Barber"}): 0.20,
        frozenset({"Specialist", "Beauty"}): 0.35,
        frozenset({"Specialist", "Barber"}): 0.15,
        frozenset({"Beauty", "Barber"}): 0.10,
    }

    return pair_scores.get(
        frozenset({target_format, candidate_format}),
        0.25,
    )


def score_competitor(
    target: dict[str, Any],
    candidate: dict[str, Any],
    max_distance_miles: float = 5.0,
) -> dict[str, Any] | None:
    distance = haversine_miles(
        target.get("latitude"),
        target.get("longitude"),
        candidate.get("latitude"),
        candidate.get("longitude"),
    )

    if distance is None or distance > max_distance_miles:
        return None

    target_services = extract_service_terms(target)
    candidate_services = extract_service_terms(candidate)

    target_subtypes = split_listish(
        target.get("subtypes")
    )
    candidate_subtypes = split_listish(
        candidate.get("subtypes")
    )

    same_category = (
        bool(as_text(target.get("category")))
        and as_text(target.get("category"))
        == as_text(candidate.get("category"))
    )

    service_score = (
        jaccard_similarity(
            target_services,
            candidate_services,
        )
        * 0.45
        + jaccard_similarity(
            target_subtypes,
            candidate_subtypes,
        )
        * 0.35
        + (1.0 if same_category else 0.0) * 0.20
    )

    distance_score = max(
        0.0,
        1.0 - distance / max_distance_miles,
    )

    prominence_score = _prominence_similarity(
        target,
        candidate,
    )

    journey_score = _journey_similarity(
        target,
        candidate,
    )

    target_attributes = flatten_true_attribute_keys(
        target.get("about")
    )
    candidate_attributes = flatten_true_attribute_keys(
        candidate.get("about")
    )

    attribute_score = jaccard_similarity(
        target_attributes,
        candidate_attributes,
    )

    format_score = _format_similarity(
        target,
        candidate,
    )

    components = {
        "Service fit": service_score,
        "Proximity": distance_score,
        "Prominence fit": prominence_score,
        "Customer journey": journey_score,
        "Google attributes": attribute_score,
        "Business format": format_score,
    }

    total_score = (
        service_score * 0.35
        + distance_score * 0.25
        + prominence_score * 0.15
        + journey_score * 0.10
        + attribute_score * 0.10
        + format_score * 0.05
    ) * 100

    shared_services = sorted(
        target_services & candidate_services
    )

    reasons: list[str] = []

    if same_category:
        reasons.append("same primary category")

    if shared_services:
        reasons.append(
            "shared services: "
            + ", ".join(shared_services[:4])
        )

    reasons.append(f"{distance:.1f} miles away")

    if prominence_score >= 0.70:
        reasons.append(
            "similar Google prominence"
        )

    if journey_score >= 0.75:
        reasons.append(
            "similar booking/customer journey"
        )

    if format_score == 1.0:
        reasons.append(
            "same business format"
        )

    return {
        "score": round(total_score, 1),
        "distance_miles": round(distance, 2),
        "shared_services": shared_services,
        "reasons": reasons,
        "components": {
            key: round(value * 100, 1)
            for key, value in components.items()
        },
        "candidate_format": broad_business_format(
            candidate
        ),
    }


def rank_competitors(
    businesses: pd.DataFrame,
    target_place_id: str,
    max_distance_miles: float = 5.0,
    include_barbers: bool = False,
) -> tuple[dict[str, Any], pd.DataFrame]:
    target_rows = businesses[
        businesses["place_id"] == target_place_id
    ]

    if target_rows.empty:
        raise ValueError(
            "The selected target business was not found."
        )

    target = target_rows.iloc[0].to_dict()
    output: list[dict[str, Any]] = []

    for _, row in businesses.iterrows():
        candidate = row.to_dict()

        if (
            candidate.get("place_id")
            == target_place_id
        ):
            continue

        if not is_eligible_hair_business(candidate):
            continue

        candidate_format = broad_business_format(
            candidate
        )

        if (
            not include_barbers
            and candidate_format == "Barber"
        ):
            continue

        result = score_competitor(
            target=target,
            candidate=candidate,
            max_distance_miles=max_distance_miles,
        )

        if result is None:
            continue

        output.append(
            {
                "place_id": candidate.get("place_id"),
                "Business": candidate.get("name"),
                "Score": result["score"],
                "Distance (miles)": (
                    result["distance_miles"]
                ),
                "Format": result["candidate_format"],
                "Category": candidate.get("category")
                or candidate.get("type"),
                "Subtypes": candidate.get("subtypes"),
                "Rating": safe_float(
                    candidate.get("rating")
                ),
                "Reviews": int(
                    safe_float(candidate.get("reviews"))
                ),
                "Shared services": ", ".join(
                    result["shared_services"]
                ),
                "Why matched": "; ".join(
                    result["reasons"]
                ),
                "Components": result["components"],
                "Website": candidate.get("website"),
                "Google Maps": candidate.get(
                    "location_link"
                ),
            }
        )

    ranked = pd.DataFrame(output)

    if ranked.empty:
        return target, ranked

    ranked = ranked.sort_values(
        ["Score", "Reviews"],
        ascending=[False, False],
    ).reset_index(drop=True)

    ranked.insert(
        0,
        "Rank",
        range(1, len(ranked) + 1),
    )

    return target, ranked
