from __future__ import annotations

import json
import math
import re
from typing import Any

import pandas as pd


GENERIC_PROFILE = {
    "key": "generic",
    "label": "Generic local business",
    "detect_terms": [],
    "candidate_terms": [],
    "excluded_terms": [],
    "traits": {},
    "default_distance_miles": 5.0,
    "weights": {
        "type_fit": 0.35,
        "proximity": 0.25,
        "prominence": 0.15,
        "customer_journey": 0.10,
        "attributes": 0.10,
        "business_format": 0.05,
    },
}


VERTICAL_PROFILES = {
    "hair_salon": {
        "key": "hair_salon",
        "label": "Hair salon",
        "detect_terms": [
            "hairdresser",
            "hair salon",
            "hair stylist",
            "hair extension technician",
            "colourist",
            "colorist",
        ],
        "candidate_terms": [
            "hairdresser",
            "hair salon",
            "hair stylist",
            "hair extension technician",
            "colourist",
            "colorist",
            "barber shop",
        ],
        "excluded_terms": [
            "nail salon",
            "massage spa",
        ],
        "traits": {
            "Balayage": ["balayage"],
            "Blonde": ["blonde", "blonding"],
            "Hair colour": [
                "hair colour",
                "hair color",
                "colourist",
                "colorist",
                "colouring",
                "coloring",
            ],
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
        },
        "default_distance_miles": 5.0,
        "weights": {
            "type_fit": 0.35,
            "proximity": 0.25,
            "prominence": 0.15,
            "customer_journey": 0.10,
            "attributes": 0.10,
            "business_format": 0.05,
        },
    },
    "coffee_shop": {
        "key": "coffee_shop",
        "label": "Coffee shop / café",
        "detect_terms": [
            "coffee shop",
            "cafe",
            "café",
        ],
        "candidate_terms": [
            "coffee shop",
            "cafe",
            "café",
            "brunch restaurant",
            "breakfast restaurant",
            "bakery",
        ],
        "excluded_terms": [
            "internet cafe",
        ],
        "traits": {
            "Speciality coffee": [
                "speciality coffee",
                "specialty coffee",
                "single origin",
                "pour over",
                "filter coffee",
                "coffee roaster",
            ],
            "Brunch": [
                "brunch",
                "breakfast",
            ],
            "Pastries": [
                "pastry",
                "pastries",
                "croissant",
                "bakery",
            ],
            "Vegan options": [
                "vegan",
                "plant based",
                "plant-based",
            ],
            "Wi-Fi / laptop friendly": [
                "wifi",
                "wi-fi",
                "laptop",
                "coworking",
                "co-working",
            ],
            "Outdoor seating": [
                "outdoor seating",
                "terrace",
                "garden",
            ],
            "Dog friendly": [
                "dog friendly",
                "dog-friendly",
                "dogs allowed",
            ],
            "Takeaway": [
                "takeaway",
                "take out",
                "takeout",
            ],
        },
        "default_distance_miles": 3.0,
        "weights": {
            "type_fit": 0.35,
            "proximity": 0.25,
            "prominence": 0.15,
            "customer_journey": 0.08,
            "attributes": 0.12,
            "business_format": 0.05,
        },
    },
    "bar_pub": {
        "key": "bar_pub",
        "label": "Bar / pub",
        "detect_terms": [
            "bar",
            "pub",
            "cocktail bar",
            "wine bar",
        ],
        "candidate_terms": [
            "bar",
            "pub",
            "cocktail bar",
            "wine bar",
            "sports bar",
            "night club",
            "live music venue",
        ],
        "excluded_terms": [
            "beauty bar",
            "nail bar",
        ],
        "traits": {
            "Cocktails": [
                "cocktail",
                "mixology",
            ],
            "Craft beer": [
                "craft beer",
                "real ale",
                "taproom",
                "brewery",
            ],
            "Wine": [
                "wine bar",
                "wine list",
                "natural wine",
            ],
            "Live music": [
                "live music",
                "live band",
                "gig",
            ],
            "DJs / dancing": [
                "dj",
                "djs",
                "dance floor",
                "dancing",
            ],
            "Late opening": [
                "late night",
                "open late",
                "nightlife",
            ],
            "Food": [
                "food served",
                "restaurant",
                "small plates",
                "bar food",
            ],
            "Outdoor seating": [
                "outdoor seating",
                "beer garden",
                "terrace",
                "rooftop",
            ],
            "Sports viewing": [
                "sports bar",
                "live sports",
                "football",
                "big screen",
            ],
            "Reservations": [
                "reservations",
                "booking",
                "book a table",
            ],
        },
        "default_distance_miles": 4.0,
        "weights": {
            "type_fit": 0.35,
            "proximity": 0.20,
            "prominence": 0.15,
            "customer_journey": 0.10,
            "attributes": 0.15,
            "business_format": 0.05,
        },
    },
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


def business_text(record: dict[str, Any]) -> str:
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
        str(record.get(field) or "").lower()
        for field in fields
    )


def get_profile_for_business(
    record: dict[str, Any],
) -> dict[str, Any]:
    text = business_text(record)

    for profile in VERTICAL_PROFILES.values():
        if any(
            term in text
            for term in profile["detect_terms"]
        ):
            return profile

    return GENERIC_PROFILE


def get_profile_by_key(
    profile_key: str,
) -> dict[str, Any]:
    if profile_key == "generic":
        return GENERIC_PROFILE

    return VERTICAL_PROFILES.get(
        profile_key,
        GENERIC_PROFILE,
    )


def available_profiles() -> list[dict[str, str]]:
    profiles = [
        {
            "key": GENERIC_PROFILE["key"],
            "label": GENERIC_PROFILE["label"],
        }
    ]
    profiles.extend(
        {
            "key": profile["key"],
            "label": profile["label"],
        }
        for profile in VERTICAL_PROFILES.values()
    )
    return profiles


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


def safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
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


def combined_business_text(
    record: dict[str, Any],
) -> str:
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


def extract_profile_traits(
    record: dict[str, Any],
    profile: dict[str, Any],
) -> set[str]:
    combined = combined_business_text(record)

    return {
        label
        for label, phrases in profile.get(
            "traits",
            {},
        ).items()
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

    if "coffee" in all_types or "cafe" in all_types:
        return "Café"

    if "pub" in primary:
        return "Pub"

    if "bar" in primary:
        return "Bar"

    return "Local business"


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


def _presence(
    record: dict[str, Any],
    field: str,
) -> bool:
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
    candidate_reviews = safe_float(candidate.get("reviews"))

    target_rating = safe_float(target.get("rating"))
    candidate_rating = safe_float(candidate.get("rating"))

    target_photos = safe_float(target.get("photos_count"))
    candidate_photos = safe_float(candidate.get("photos_count"))

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
    return (
        1.0
        if broad_business_format(target)
        == broad_business_format(candidate)
        else 0.25
    )


def _type_text(record: dict[str, Any]) -> str:
    return " ".join(
        as_text(record.get(field))
        for field in ["category", "type", "subtypes"]
    )


def candidate_allowed(
    candidate: dict[str, Any],
    target: dict[str, Any],
    profile: dict[str, Any],
    candidate_scope: str,
) -> bool:
    status = as_text(candidate.get("business_status"))

    if status and status != "operational":
        return False

    candidate_text = _type_text(candidate)
    target_primary = as_text(
        target.get("category") or target.get("type")
    )
    candidate_primary = as_text(
        candidate.get("category") or candidate.get("type")
    )

    if candidate_scope == "Same primary type":
        return (
            bool(target_primary)
            and target_primary == candidate_primary
        )

    if candidate_scope == "All businesses":
        return True

    excluded_terms = profile.get("excluded_terms", [])

    if any(
        term in candidate_text
        for term in excluded_terms
    ):
        return False

    candidate_terms = profile.get("candidate_terms", [])

    if candidate_terms:
        return any(
            term in candidate_text
            for term in candidate_terms
        )

    return (
        target_primary == candidate_primary
        if target_primary
        else True
    )


def score_competitor(
    target: dict[str, Any],
    candidate: dict[str, Any],
    profile: dict[str, Any],
    max_distance_miles: float,
) -> dict[str, Any] | None:
    distance = haversine_miles(
        target.get("latitude"),
        target.get("longitude"),
        candidate.get("latitude"),
        candidate.get("longitude"),
    )

    if distance is None or distance > max_distance_miles:
        return None

    target_traits = extract_profile_traits(target, profile)
    candidate_traits = extract_profile_traits(
        candidate,
        profile,
    )

    target_subtypes = split_listish(target.get("subtypes"))
    candidate_subtypes = split_listish(
        candidate.get("subtypes")
    )

    target_primary = as_text(
        target.get("category") or target.get("type")
    )
    candidate_primary = as_text(
        candidate.get("category") or candidate.get("type")
    )

    same_category = (
        bool(target_primary)
        and target_primary == candidate_primary
    )

    trait_similarity = jaccard_similarity(
        target_traits,
        candidate_traits,
    )
    subtype_similarity = jaccard_similarity(
        target_subtypes,
        candidate_subtypes,
    )

    type_fit_score = (
        trait_similarity * 0.45
        + subtype_similarity * 0.35
        + (1.0 if same_category else 0.0) * 0.20
    )

    if profile["key"] == "generic":
        type_fit_score = (
            subtype_similarity * 0.60
            + (1.0 if same_category else 0.0) * 0.40
        )

    proximity_score = max(
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
        "Type and trait fit": type_fit_score,
        "Proximity": proximity_score,
        "Prominence fit": prominence_score,
        "Customer journey": journey_score,
        "Google attributes": attribute_score,
        "Business format": format_score,
    }

    weights = profile.get(
        "weights",
        GENERIC_PROFILE["weights"],
    )

    weighted_total = (
        type_fit_score * weights["type_fit"]
        + proximity_score * weights["proximity"]
        + prominence_score * weights["prominence"]
        + journey_score * weights["customer_journey"]
        + attribute_score * weights["attributes"]
        + format_score * weights["business_format"]
    ) * 100

    shared_traits = sorted(
        target_traits & candidate_traits
    )

    reasons: list[str] = []

    if same_category:
        reasons.append("same primary type")

    if shared_traits:
        reasons.append(
            "shared traits: "
            + ", ".join(shared_traits[:4])
        )

    reasons.append(f"{distance:.1f} miles away")

    if prominence_score >= 0.70:
        reasons.append("similar Google prominence")

    if journey_score >= 0.75:
        reasons.append(
            "similar booking/customer journey"
        )

    if format_score == 1.0:
        reasons.append("same business format")

    return {
        "score": round(weighted_total, 1),
        "distance_miles": round(distance, 2),
        "shared_traits": shared_traits,
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
    profile_override: dict[str, Any] | None = None,
    max_distance_miles: float | None = None,
    candidate_scope: str = "Profile-relevant types",
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    pd.DataFrame,
]:
    target_rows = businesses[
        businesses["place_id"] == target_place_id
    ]

    if target_rows.empty:
        raise ValueError(
            "The selected target business was not found."
        )

    target = target_rows.iloc[0].to_dict()
    profile = (
        profile_override
        or get_profile_for_business(target)
    )

    distance_limit = (
        max_distance_miles
        if max_distance_miles is not None
        else profile["default_distance_miles"]
    )

    output: list[dict[str, Any]] = []

    for _, row in businesses.iterrows():
        candidate = row.to_dict()

        if candidate.get("place_id") == target_place_id:
            continue

        if not candidate_allowed(
            candidate=candidate,
            target=target,
            profile=profile,
            candidate_scope=candidate_scope,
        ):
            continue

        result = score_competitor(
            target=target,
            candidate=candidate,
            profile=profile,
            max_distance_miles=distance_limit,
        )

        if result is None:
            continue

        output.append(
            {
                "place_id": candidate.get("place_id"),
                "Business": candidate.get("name"),
                "Score": result["score"],
                "Distance (miles)": result["distance_miles"],
                "Format": result["candidate_format"],
                "Category": (
                    candidate.get("category")
                    or candidate.get("type")
                ),
                "Subtypes": candidate.get("subtypes"),
                "Rating": safe_float(
                    candidate.get("rating")
                ),
                "Reviews": int(
                    safe_float(candidate.get("reviews"))
                ),
                "Shared traits": ", ".join(
                    result["shared_traits"]
                ),
                "Why matched": "; ".join(
                    result["reasons"]
                ),
                "Components": result["components"],
                "Website": (
                    candidate.get("website")
                    or candidate.get("site")
                ),
                "Google Maps": (
                    candidate.get("location_link")
                    or candidate.get("google_maps_url")
                ),
            }
        )

    ranked = pd.DataFrame(output)

    if ranked.empty:
        return target, profile, ranked

    ranked = ranked.sort_values(
        ["Score", "Reviews"],
        ascending=[False, False],
    ).reset_index(drop=True)

    ranked.insert(
        0,
        "Rank",
        range(1, len(ranked) + 1),
    )

    return target, profile, ranked
