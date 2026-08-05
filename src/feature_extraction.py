from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from typing import Any

from src.taxonomy import (
    GROUP_LABELS,
    GROUP_RULES,
    TRAIT_RULES,
    contains_phrase,
    normalise_label,
    split_subtypes,
)


def _is_missing(value: Any) -> bool:
    if value is None:
        return True

    if isinstance(value, float):
        return math.isnan(value)

    return False


def parse_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value

    if _is_missing(value):
        return {}

    if isinstance(value, str):
        cleaned = value.strip()

        if not cleaned:
            return {}

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            return {}

        return parsed if isinstance(parsed, dict) else {}

    return {}


def slug_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def flatten_about(
    value: Any,
    prefix: str = "",
) -> dict[str, bool]:
    parsed = (
        value
        if isinstance(value, dict)
        else parse_json_object(value)
    )

    output: dict[str, bool] = {}

    if not isinstance(parsed, dict):
        return output

    for key, nested_value in parsed.items():
        current_key = ".".join(
            item
            for item in [prefix, slug_key(key)]
            if item
        )

        if isinstance(nested_value, dict):
            output.update(
                flatten_about(
                    nested_value,
                    current_key,
                )
            )
        elif isinstance(nested_value, bool):
            output[current_key] = nested_value
        elif isinstance(nested_value, str):
            lowered = nested_value.strip().lower()

            if lowered in {"true", "false"}:
                output[current_key] = lowered == "true"

    return output


def combined_text(record: dict[str, Any]) -> str:
    fields = [
        "name",
        "category",
        "type",
        "subtypes",
        "description",
        "reviews_tags",
        "located_in",
        "range",
        "prices",
    ]

    return " ".join(
        str(record.get(field) or "")
        for field in fields
    ).lower()


def classify_groups(
    record: dict[str, Any],
) -> tuple[
    str,
    list[dict[str, Any]],
    float,
    list[str],
]:
    category = normalise_label(
        record.get("category")
    )
    business_type = normalise_label(
        record.get("type")
    )
    subtypes = split_subtypes(
        record.get("subtypes")
    )

    scores: dict[str, float] = defaultdict(float)
    reasons: dict[str, list[str]] = defaultdict(list)

    for group_key, rules in GROUP_RULES.items():
        if category in rules["category_values"]:
            scores[group_key] += 5.0
            reasons[group_key].append(
                f"Category: {record.get('category')}"
            )

        if business_type in rules["type_values"]:
            scores[group_key] += 7.0
            reasons[group_key].append(
                f"Type: {record.get('type')}"
            )

        matching_subtypes = [
            subtype
            for subtype in subtypes
            if subtype in rules["subtype_values"]
        ]

        if matching_subtypes:
            scores[group_key] += min(
                9.0,
                3.0 * len(matching_subtypes),
            )
            reasons[group_key].append(
                "Subtypes: "
                + ", ".join(matching_subtypes[:4])
            )

    about_features = flatten_about(
        record.get("about")
    )

    if (
        about_features.get(
            "highlights.live_music"
        )
        or about_features.get(
            "highlights.live_performances"
        )
        or about_features.get(
            "offerings.dancing"
        )
    ):
        scores["nightlife_entertainment"] += 2.0
        reasons["nightlife_entertainment"].append(
            "Entertainment attributes"
        )

    if not scores:
        return (
            "other",
            [],
            0.30,
            ["No configured taxonomy match"],
        )

    ordered = sorted(
        scores.items(),
        key=lambda item: (-item[1], item[0]),
    )

    primary_group, primary_score = ordered[0]

    secondary_groups = [
        {
            "group": group_key,
            "label": GROUP_LABELS[group_key],
            "evidence_score": score,
        }
        for group_key, score in ordered[1:]
        if score >= 3.0
        and score >= primary_score * 0.40
    ]

    second_score = (
        ordered[1][1]
        if len(ordered) > 1
        else 0.0
    )

    score_separation = max(
        0.0,
        primary_score - second_score,
    )

    confidence = min(
        0.98,
        0.50
        + min(primary_score, 18.0) * 0.02
        + min(score_separation, 10.0) * 0.012,
    )

    return (
        primary_group,
        secondary_groups,
        round(confidence, 4),
        reasons[primary_group],
    )


def determine_business_format(
    record: dict[str, Any],
    primary_group: str,
    about_features: dict[str, bool],
) -> str:
    business_type = normalise_label(
        record.get("type")
    )
    subtypes = set(
        split_subtypes(record.get("subtypes"))
    )

    labels = {
        business_type,
        *subtypes,
    }

    if primary_group == "bars_pubs":
        if "gastropub" in labels:
            return "Gastropub"
        if "sports bar" in labels:
            return "Sports bar"
        if "cocktail bar" in labels:
            return "Cocktail bar"
        if "wine bar" in labels:
            return "Wine bar"
        if "gay bar" in labels:
            return "Gay bar"
        if "lounge bar" in labels:
            return "Lounge bar"
        if (
            "taproom" in labels
            or "brewpub" in labels
            or "brewery" in labels
        ):
            return "Taproom / brewery"
        if "bar and grill" in labels:
            return "Bar & grill"
        if "pub" in labels:
            return "Pub"
        if "night club" in labels:
            return "Nightclub"
        if (
            "live music venue" in labels
            or about_features.get(
                "highlights.live_music"
            )
        ):
            return "Music-led bar"
        return "Bar"

    if primary_group == "hair_services":
        if "barber shop" in labels:
            return "Barber"
        if "hair extension technician" in labels:
            return "Extension specialist"
        if "hair replacement service" in labels:
            return "Hair replacement specialist"
        if contains_phrase(
            combined_text(record),
            "men's hairdresser",
        ):
            return "Men's hairdresser"
        if "hair salon" in labels:
            return "Hair salon"
        return "Hairdresser"

    if primary_group == "coffee_cafes":
        if (
            "bakery" in labels
            and (
                "coffee shop" in labels
                or "cafe" in labels
            )
        ):
            return "Café-bakery"
        if "coffee roastery" in labels:
            return "Roastery"
        if (
            "brunch restaurant" in labels
            or "breakfast restaurant" in labels
        ):
            return "Brunch café"
        if "tea room" in labels:
            return "Tea room"
        if "coffee shop" in labels:
            return "Coffee shop"
        return "Café"

    if primary_group == "beauty_wellness":
        if "nail salon" in labels:
            return "Nail salon"
        if "eyelash salon" in labels:
            return "Eyelash salon"
        if "massage therapist" in labels:
            return "Massage"
        if (
            "spa" in labels
            or "day spa" in labels
            or "medical spa" in labels
        ):
            return "Spa"
        if "skin care clinic" in labels:
            return "Skin care clinic"
        return "Beauty salon"

    if primary_group == "restaurants":
        if "breakfast restaurant" in labels:
            return "Breakfast restaurant"
        if "brunch restaurant" in labels:
            return "Brunch restaurant"
        if "bar and grill" in labels:
            return "Bar & grill"
        return str(
            record.get("type")
            or "Restaurant"
        )

    if primary_group == "nightlife_entertainment":
        if "night club" in labels:
            return "Nightclub"
        if "live music venue" in labels:
            return "Live music venue"
        return "Entertainment venue"

    if primary_group == "workspaces":
        if (
            "co-working space" in labels
            or "coworking space" in labels
        ):
            return "Coworking space"
        return "Office workspace"

    return str(
        record.get("type")
        or record.get("category")
        or "Other local business"
    )


def extract_traits(
    record: dict[str, Any],
    primary_group: str,
    about_features: dict[str, bool],
) -> list[str]:
    rules = TRAIT_RULES.get(
        primary_group,
        {},
    )

    text = combined_text(record)
    traits: list[str] = []

    for trait_name, rule in rules.items():
        about_match = any(
            about_features.get(attribute) is True
            for attribute in rule.get(
                "about_true",
                [],
            )
        )

        text_match = any(
            contains_phrase(text, phrase)
            for phrase in rule.get(
                "text_terms",
                [],
            )
        )

        if about_match or text_match:
            traits.append(trait_name)

    return sorted(set(traits))


def extract_business_features(
    record: dict[str, Any],
) -> dict[str, Any]:
    place_id = (
        record.get("place_id")
        or record.get("google_place_id")
    )

    if not place_id:
        raise ValueError(
            "Business record has no Google Place ID."
        )

    about_features = flatten_about(
        record.get("about")
    )

    (
        primary_group,
        secondary_groups,
        confidence,
        reasons,
    ) = classify_groups(record)

    business_format = determine_business_format(
        record,
        primary_group,
        about_features,
    )

    traits = extract_traits(
        record,
        primary_group,
        about_features,
    )

    return {
        "google_place_id": str(place_id),
        "business_name": record.get("name"),
        "raw_category": record.get("category"),
        "raw_type": record.get("type"),
        "raw_subtypes": split_subtypes(
            record.get("subtypes")
        ),
        "primary_group": primary_group,
        "secondary_groups": secondary_groups,
        "business_format": business_format,
        "traits": traits,
        "about_features": about_features,
        "classification_confidence": confidence,
        "classification_reasons": reasons,
        "source_snapshot": {
            "category": record.get("category"),
            "type": record.get("type"),
            "subtypes": record.get("subtypes"),
            "description": record.get("description"),
            "reviews_tags": record.get("reviews_tags"),
        },
    }
