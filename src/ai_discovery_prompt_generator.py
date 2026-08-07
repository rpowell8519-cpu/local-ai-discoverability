from __future__ import annotations

import re
from typing import Any

import pandas as pd


VERTICALS = {
    "Bars & pubs": {
        "key": "bars_pubs",
        "noun": "pub",
        "core": [
            (
                "General recommendation",
                "Recommend a good pub in {location}.",
            ),
            (
                "Food and drink",
                "Where is a good pub in {location} for food and drinks?",
            ),
            (
                "Atmosphere",
                "Recommend a pub in {location} with a great atmosphere.",
            ),
            (
                "Groups",
                "Where is a good pub in {location} for a group of friends?",
            ),
            (
                "Local",
                "Recommend a good neighbourhood pub in {location}.",
            ),
            (
                "Occasion",
                "Which pub in {location} would you recommend for a casual celebration?",
            ),
            (
                "Quality",
                "What are some of the best pubs in {location}?",
            ),
            (
                "Independent",
                "Recommend a good independent pub in {location}.",
            ),
        ],
    },
    "Hair services": {
        "key": "hair_services",
        "noun": "hair salon",
        "core": [
            (
                "General recommendation",
                "Recommend a good hair salon in {location}.",
            ),
            (
                "Quality",
                "What are some of the best hair salons in {location}?",
            ),
            (
                "Friendly service",
                "Recommend a friendly, welcoming hair salon in {location}.",
            ),
            (
                "Expertise",
                "Which hair salons in {location} are known for highly skilled stylists?",
            ),
            (
                "Consultation",
                "Where should I go in {location} for a salon that gives good consultations?",
            ),
            (
                "Results",
                "Which salons in {location} are known for consistently good results?",
            ),
            (
                "Independent",
                "Recommend a high-quality independent hair salon in {location}.",
            ),
            (
                "Experience",
                "Which hair salons in {location} offer a particularly good client experience?",
            ),
        ],
    },
    "Coffee shops & cafés": {
        "key": "coffee_cafes",
        "noun": "café",
        "core": [
            (
                "General recommendation",
                "Recommend a good café in {location}.",
            ),
            (
                "Coffee quality",
                "Where can I get really good coffee in {location}?",
            ),
            (
                "Food",
                "Recommend a café in {location} with good coffee and food.",
            ),
            (
                "Atmosphere",
                "Which cafés in {location} have a great atmosphere?",
            ),
            (
                "Local",
                "Recommend a good independent café in {location}.",
            ),
            (
                "Brunch",
                "Where is a good café in {location} for brunch?",
            ),
            (
                "Relaxed",
                "Recommend a relaxed café in {location}.",
            ),
            (
                "Quality",
                "What are some of the best coffee shops in {location}?",
            ),
        ],
    },
    "Restaurants": {
        "key": "restaurants",
        "noun": "restaurant",
        "core": [
            (
                "General recommendation",
                "Recommend a good restaurant in {location}.",
            ),
            (
                "Quality",
                "What are some of the best restaurants in {location}?",
            ),
            (
                "Local",
                "Recommend a good independent restaurant in {location}.",
            ),
            (
                "Atmosphere",
                "Which restaurants in {location} have a great atmosphere?",
            ),
            (
                "Groups",
                "Where is a good restaurant in {location} for a group?",
            ),
            (
                "Occasion",
                "Which restaurant in {location} would you recommend for a special occasion?",
            ),
            (
                "Casual",
                "Recommend a good casual restaurant in {location}.",
            ),
            (
                "Experience",
                "Which restaurants in {location} offer a particularly good overall experience?",
            ),
        ],
    },
    "Beauty & wellness": {
        "key": "beauty_wellness",
        "noun": "beauty or wellness business",
        "core": [
            (
                "General recommendation",
                "Recommend a good beauty or wellness business in {location}.",
            ),
            (
                "Quality",
                "Which beauty and wellness businesses in {location} are known for high quality?",
            ),
            (
                "Service",
                "Recommend a beauty or wellness business in {location} with excellent service.",
            ),
            (
                "Local",
                "Recommend a good independent beauty or wellness business in {location}.",
            ),
            (
                "Experience",
                "Which beauty or wellness businesses in {location} offer a great customer experience?",
            ),
            (
                "Trusted",
                "Which beauty or wellness businesses in {location} are particularly well regarded?",
            ),
        ],
    },
    "Workspaces": {
        "key": "workspaces",
        "noun": "workspace",
        "core": [
            (
                "General recommendation",
                "Recommend a good workspace in {location}.",
            ),
            (
                "Quality",
                "What are some of the best workspaces in {location}?",
            ),
            (
                "Independent",
                "Recommend a good independent workspace in {location}.",
            ),
            (
                "Community",
                "Which workspaces in {location} have a strong community?",
            ),
            (
                "Flexible",
                "Where can I find a good flexible workspace in {location}?",
            ),
            (
                "Experience",
                "Which workspaces in {location} offer the best overall experience?",
            ),
        ],
    },
    "Other local business": {
        "key": "other_local_business",
        "noun": "local business",
        "core": [
            (
                "General recommendation",
                "Recommend a good local business in {location} for this type of service.",
            ),
            (
                "Quality",
                "Which local businesses in {location} are known for high quality?",
            ),
            (
                "Service",
                "Recommend a local business in {location} with excellent customer service.",
            ),
            (
                "Trusted",
                "Which local businesses in {location} are particularly well regarded?",
            ),
            (
                "Independent",
                "Recommend a good independent local business in {location}.",
            ),
        ],
    },
}


def vertical_key(
    category_label: str,
) -> str:
    return VERTICALS.get(
        category_label,
        VERTICALS[
            "Other local business"
        ],
    )["key"]


def _split_propositions(
    value: Any,
) -> list[str]:
    if isinstance(
        value,
        list,
    ):
        parts = value
    else:
        parts = re.split(
            r"[\n,;]+",
            str(value or ""),
        )

    cleaned = []

    for part in parts:
        item = re.sub(
            r"\s+",
            " ",
            str(part).strip(),
        )

        if (
            not item
            or len(item) < 3
        ):
            continue

        cleaned.append(item)

    return list(
        dict.fromkeys(
            cleaned
        )
    )


def generate_discovery_prompts(
    *,
    category_label: str,
    location: str,
    propositions: Any = None,
    max_prompts: int = 20,
) -> pd.DataFrame:
    vertical = VERTICALS.get(
        category_label,
        VERTICALS[
            "Other local business"
        ],
    )

    location_value = (
        str(location or "").strip()
        or "the local area"
    )

    rows = []

    for category, template in (
        vertical["core"]
    ):
        rows.append(
            {
                "include": True,
                "category": category,
                "source": "core_market",
                "prompt": template.format(
                    location=(
                        location_value
                    )
                ),
            }
        )

    noun = vertical["noun"]

    for proposition in (
        _split_propositions(
            propositions
        )
    ):
        proposition_clean = (
            proposition.strip(
                " ."
            )
        )

        rows.append(
            {
                "include": True,
                "category":
                    "Client proposition",
                "source":
                    "client_proposition",
                "prompt": (
                    f"Recommend a {noun} in "
                    f"{location_value} for "
                    f"{proposition_clean}."
                ),
            }
        )

    # Deduplicate while preserving order.
    seen = set()
    deduped = []

    for row in rows:
        key = row[
            "prompt"
        ].lower()

        if key in seen:
            continue

        seen.add(key)
        deduped.append(row)

    return pd.DataFrame(
        deduped[
            :max(
                1,
                int(
                    max_prompts
                ),
            )
        ],
        columns=[
            "include",
            "category",
            "source",
            "prompt",
        ],
    )
