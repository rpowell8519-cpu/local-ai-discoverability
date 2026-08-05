from __future__ import annotations

from typing import Any


GENERIC_PROFILE = {
    "key": "generic",
    "label": "Generic local business",
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
            "Early opening": [
                "early opening",
                "open early",
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
    output = [
        {
            "key": GENERIC_PROFILE["key"],
            "label": GENERIC_PROFILE["label"],
        }
    ]

    output.extend(
        {
            "key": profile["key"],
            "label": profile["label"],
        }
        for profile in VERTICAL_PROFILES.values()
    )

    return output

def get_profile_by_key(
    profile_key: str,
) -> dict:
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
