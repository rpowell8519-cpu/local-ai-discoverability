from __future__ import annotations

from typing import Any


GENERIC_THEMES: list[dict[str, Any]] = [
    {
        "key": "friendly_staff",
        "label": "Friendly staff",
        "category": "Service",
        "terms": [
            "friendly staff", "friendly service", "welcoming staff",
            "lovely staff", "great staff", "helpful staff",
            "attentive staff", "warm service", "warm and efficient",
        ],
    },
    {
        "key": "service_quality",
        "label": "Service quality",
        "category": "Service",
        "terms": [
            "great service", "excellent service", "good service",
            "amazing service", "service was great", "service was excellent",
            "service was good",
        ],
    },
    {
        "key": "slow_service",
        "label": "Slow service / waiting",
        "category": "Problems",
        "terms": [
            "slow service", "service was slow", "waited", "waiting",
            "long wait", "took ages", "took forever", "45 minutes",
            "one hour", "1.5 hours", "unacceptably slow",
        ],
    },
    {
        "key": "atmosphere",
        "label": "Atmosphere / vibe",
        "category": "Experience",
        "terms": [
            "atmosphere", "ambience", "ambiance", "vibe",
            "buzzing", "cosy", "cozy", "relaxed",
        ],
    },
    {
        "key": "value",
        "label": "Value / price",
        "category": "Value",
        "terms": [
            "good value", "great value", "value for money",
            "reasonable price", "reasonably priced", "expensive",
            "overpriced", "pricey", "cheap",
        ],
    },
    {
        "key": "booking",
        "label": "Booking / reservations",
        "category": "Journey",
        "terms": [
            "booking", "booked", "book a table", "reservation",
            "reserved", "recommend booking",
        ],
    },
    {
        "key": "groups_occasions",
        "label": "Groups / occasions",
        "category": "Occasions",
        "terms": [
            "birthday", "party", "staff party", "group", "groups",
            "celebration", "work do", "work party", "family gathering",
        ],
    },
    {
        "key": "dog_friendly",
        "label": "Dog friendly",
        "category": "Audience",
        "terms": [
            "dog friendly", "dog-friendly", "dogs allowed",
            "with our dog", "dogs welcome",
        ],
    },
]


BAR_PUB_THEMES: list[dict[str, Any]] = [
    {
        "key": "sunday_roast",
        "label": "Sunday roast / Sunday lunch",
        "category": "Food & drink",
        "terms": [
            "sunday roast", "sunday lunch", "roast dinner",
            "roast beef", "roast pork", "roasties", "yorkshire pud",
            "yorkshire pudding",
        ],
    },
    {
        "key": "food_quality",
        "label": "Food quality",
        "category": "Food & drink",
        "terms": [
            "delicious food", "food was fantastic", "food was amazing",
            "great food", "excellent food", "good food",
            "food was delicious", "tasty food", "lovely food",
        ],
    },
    {
        "key": "food_portions",
        "label": "Generous portions",
        "category": "Food & drink",
        "terms": [
            "generous portions", "large portions", "big portions",
            "generous helping", "generous helpings", "portion size",
        ],
    },
    {
        "key": "beer_cider",
        "label": "Beer / cider range",
        "category": "Food & drink",
        "terms": [
            "beer", "beers", "cider", "ciders", "ale", "ales",
            "lager", "harvey's", "harveys", "on tap", "craft beer",
        ],
    },
    {
        "key": "cocktails_wine",
        "label": "Cocktails / wine",
        "category": "Food & drink",
        "terms": [
            "cocktail", "cocktails", "wine", "wines", "prosecco",
        ],
    },
    {
        "key": "pub_garden",
        "label": "Pub garden / outdoor space",
        "category": "Experience",
        "terms": [
            "pub garden", "beer garden", "garden", "outdoor",
            "terrace", "courtyard", "outside seating",
        ],
    },
    {
        "key": "music_entertainment",
        "label": "Music / entertainment",
        "category": "Experience",
        "terms": [
            "live music", "music", "dj", "quiz", "quiz night",
            "entertainment", "live band",
        ],
    },
    {
        "key": "community_local",
        "label": "Community / local pub",
        "category": "Positioning",
        "terms": [
            "community pub", "local pub", "proper pub",
            "traditional pub", "neighbourhood pub", "neighborhood pub",
            "locals pub",
        ],
    },
    {
        "key": "sport",
        "label": "Sport viewing",
        "category": "Experience",
        "terms": [
            "football", "rugby", "sport", "sports", "match",
            "game on", "watch the game",
        ],
    },
    {
        "key": "family_friendly",
        "label": "Family friendly",
        "category": "Audience",
        "terms": [
            "family friendly", "family-friendly", "kids", "children",
            "child friendly", "with the family",
        ],
    },
]


HAIR_THEMES: list[dict[str, Any]] = [
    {
        "key": "colour",
        "label": "Colour expertise",
        "category": "Services",
        "terms": [
            "colour", "color", "colouring", "coloring",
            "highlights", "blonde", "blonding",
        ],
    },
    {
        "key": "balayage",
        "label": "Balayage",
        "category": "Services",
        "terms": ["balayage"],
    },
    {
        "key": "cut",
        "label": "Haircuts / styling",
        "category": "Services",
        "terms": [
            "haircut", "hair cut", "cut and blow", "blow dry",
            "blow-dry", "styling", "restyle",
        ],
    },
    {
        "key": "extensions",
        "label": "Hair extensions",
        "category": "Services",
        "terms": ["extensions", "hair extensions"],
    },
    {
        "key": "consultation",
        "label": "Consultation",
        "category": "Journey",
        "terms": ["consultation", "consult", "listened to what i wanted"],
    },
    {
        "key": "results",
        "label": "Results / transformation",
        "category": "Outcome",
        "terms": [
            "love my hair", "amazing result", "amazing results",
            "transformation", "exactly what i wanted", "so happy with my hair",
        ],
    },
    {
        "key": "stylist_expertise",
        "label": "Stylist expertise",
        "category": "Trust",
        "terms": [
            "stylist", "hairdresser", "colourist", "colorist",
            "knowledgeable", "expert", "professional",
        ],
    },
]


COFFEE_THEMES: list[dict[str, Any]] = [
    {
        "key": "coffee_quality",
        "label": "Coffee quality",
        "category": "Food & drink",
        "terms": [
            "great coffee", "excellent coffee", "good coffee",
            "amazing coffee", "best coffee", "flat white",
            "espresso", "latte", "cappuccino",
        ],
    },
    {
        "key": "brunch_food",
        "label": "Breakfast / brunch / food",
        "category": "Food & drink",
        "terms": [
            "breakfast", "brunch", "pastry", "pastries",
            "cake", "cakes", "sandwich", "food",
        ],
    },
    {
        "key": "workspace",
        "label": "Laptop / workspace",
        "category": "Experience",
        "terms": [
            "laptop", "work from", "working", "wifi", "wi-fi",
            "plug socket", "remote work",
        ],
    },
]


PROFILE_LABELS = {
    "bars_pubs": "Bars & pubs",
    "hair_services": "Hair services",
    "coffee_cafes": "Coffee shops & cafés",
    "generic": "Generic local business",
}


def get_review_profile(primary_group: str) -> dict[str, Any]:
    group = str(primary_group or "generic")

    vertical_themes = {
        "bars_pubs": BAR_PUB_THEMES,
        "hair_services": HAIR_THEMES,
        "coffee_cafes": COFFEE_THEMES,
    }.get(group, [])

    return {
        "key": group,
        "label": PROFILE_LABELS.get(
            group, PROFILE_LABELS["generic"]
        ),
        "themes": [
            *GENERIC_THEMES,
            *vertical_themes,
        ],
    }
