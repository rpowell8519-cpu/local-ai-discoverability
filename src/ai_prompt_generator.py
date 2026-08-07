from __future__ import annotations

from typing import Any

import pandas as pd

from src.review_analysis import analyse_reviews
from src.review_profiles import get_review_profile


BASE_PROMPTS = {
    "bars_pubs": [
        (
            "General recommendation",
            "Recommend a good pub in {location}.",
        ),
        (
            "Food and drink",
            "Where is a good pub in {location} for food and drinks?",
        ),
        (
            "Local atmosphere",
            "Recommend a friendly local pub in {location} with a good atmosphere.",
        ),
        (
            "Sunday roast",
            "Where should I go for a good Sunday roast in {location}?",
        ),
        (
            "Beer",
            "Recommend a pub in {location} with a good beer selection.",
        ),
        (
            "Outdoor space",
            "Which pubs in {location} are good for drinks with outdoor space?",
        ),
        (
            "Groups",
            "Where is a good pub in {location} for a group of friends?",
        ),
        (
            "Cosy",
            "Recommend a cosy pub in {location} for a relaxed drink.",
        ),
        (
            "Events",
            "Which pubs in {location} are good for live music or events?",
        ),
        (
            "Family",
            "Recommend a family-friendly pub in {location} for lunch.",
        ),
        (
            "Dog friendly",
            "Where is a good dog-friendly pub in {location}?",
        ),
        (
            "Occasion",
            "Which pub in {location} would you recommend for a casual birthday gathering?",
        ),
    ],
    "hair_services": [
        (
            "General recommendation",
            "Recommend a good hair salon in {location}.",
        ),
        (
            "Colour",
            "Where should I go for hair colouring in {location}?",
        ),
        (
            "Balayage",
            "Recommend a good salon for balayage in {location}.",
        ),
        (
            "Consultation",
            "Which hair salons in {location} are good for a colour consultation?",
        ),
        (
            "Friendly service",
            "Recommend a friendly, welcoming hair salon in {location}.",
        ),
        (
            "Specialist expertise",
            "Which salons in {location} are known for experienced colourists?",
        ),
        (
            "Restyle",
            "Where should I go in {location} for a haircut and restyle?",
        ),
        (
            "Extensions",
            "Recommend a good salon for hair extensions in {location}.",
        ),
        (
            "Results",
            "Which salons in {location} are known for great hair transformations?",
        ),
        (
            "Premium",
            "Recommend a high-quality independent hair salon in {location}.",
        ),
    ],
    "coffee_cafes": [
        (
            "General recommendation",
            "Recommend a good coffee shop in {location}.",
        ),
        (
            "Coffee quality",
            "Where can I get really good coffee in {location}?",
        ),
        (
            "Brunch",
            "Recommend a café in {location} for brunch.",
        ),
        (
            "Atmosphere",
            "Which cafés in {location} have a relaxed atmosphere?",
        ),
        (
            "Workspace",
            "Where is a good café in {location} to work on a laptop?",
        ),
        (
            "Food",
            "Recommend a café in {location} with good coffee and food.",
        ),
    ],
    "generic": [
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
            "Recommend a local business in {location} with friendly service.",
        ),
    ],
}


THEME_PROMPTS = {
    "bars_pubs": {
        "sunday_roast": (
            "Customer association",
            "What are the best pubs in {location} for a Sunday roast?",
        ),
        "friendly_staff": (
            "Customer association",
            "Recommend a welcoming pub in {location} with friendly staff.",
        ),
        "beer_cider": (
            "Customer association",
            "Which pubs in {location} have a good range of beer or cider?",
        ),
        "pub_garden": (
            "Customer association",
            "Recommend a pub in {location} with a good garden or outdoor space.",
        ),
        "community_local": (
            "Customer association",
            "What is a good community or neighbourhood pub in {location}?",
        ),
        "atmosphere": (
            "Customer association",
            "Which pubs in {location} are known for a great atmosphere?",
        ),
        "food_quality": (
            "Customer association",
            "Recommend a pub in {location} that is particularly good for food.",
        ),
        "groups_occasions": (
            "Customer association",
            "Which pubs in {location} are good for groups or celebrations?",
        ),
        "music_entertainment": (
            "Customer association",
            "Recommend a pub in {location} for music or entertainment.",
        ),
    },
    "hair_services": {
        "colour": (
            "Customer association",
            "Which hair salons in {location} are particularly good for colour?",
        ),
        "balayage": (
            "Customer association",
            "What are the best salons in {location} for balayage?",
        ),
        "friendly_staff": (
            "Customer association",
            "Recommend a hair salon in {location} with friendly, welcoming staff.",
        ),
        "consultation": (
            "Customer association",
            "Which salons in {location} are good at listening to clients and giving consultations?",
        ),
        "stylist_expertise": (
            "Customer association",
            "Recommend a salon in {location} with highly skilled stylists.",
        ),
        "results": (
            "Customer association",
            "Which salons in {location} are known for excellent hair results?",
        ),
    },
}


def generate_prompts(
    *,
    primary_group: str,
    location: str,
    reviews: pd.DataFrame | None = None,
    max_prompts: int = 20,
) -> pd.DataFrame:
    group = str(
        primary_group
        or "generic"
    )

    location_value = (
        str(location or "").strip()
        or "the local area"
    )

    candidates = []

    for category, template in BASE_PROMPTS.get(
        group,
        BASE_PROMPTS["generic"],
    ):
        candidates.append(
            {
                "include": True,
                "category": category,
                "source": "vertical",
                "prompt": template.format(
                    location=location_value
                ),
            }
        )

    if (
        reviews is not None
        and not reviews.empty
    ):
        profile = get_review_profile(
            group
        )

        themes = analyse_reviews(
            reviews,
            profile,
        )

        available = THEME_PROMPTS.get(
            group,
            {},
        )

        strong_themes = themes[
            (
                themes["mention_count"]
                >= 3
            )
            & (
                themes["mention_pct"]
                >= 0.03
            )
        ].copy()

        for row in strong_themes.to_dict(
            "records"
        ):
            theme_prompt = available.get(
                row["theme_key"]
            )

            if not theme_prompt:
                continue

            category, template = (
                theme_prompt
            )

            candidates.append(
                {
                    "include": True,
                    "category": category,
                    "source": (
                        "review_theme:"
                        + str(
                            row[
                                "theme_key"
                            ]
                        )
                    ),
                    "prompt": (
                        template.format(
                            location=(
                                location_value
                            )
                        )
                    ),
                }
            )

    deduped = []
    seen = set()

    for item in candidates:
        key = item["prompt"].lower()

        if key in seen:
            continue

        seen.add(key)
        deduped.append(item)

    return pd.DataFrame(
        deduped[:max_prompts],
        columns=[
            "include",
            "category",
            "source",
            "prompt",
        ],
    )
