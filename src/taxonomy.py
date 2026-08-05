from __future__ import annotations

import re
from typing import Any


def normalise_label(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = text.replace("&", " and ")
    text = re.sub(r"\s+", " ", text)
    return text


def split_subtypes(value: Any) -> list[str]:
    if value is None:
        return []

    return [
        normalise_label(item)
        for item in str(value).split(",")
        if normalise_label(item)
    ]


def contains_phrase(text: str, phrase: str) -> bool:
    normalised_text = normalise_label(text)
    normalised_phrase = normalise_label(phrase)

    if not normalised_text or not normalised_phrase:
        return False

    pattern = (
        r"(?<![a-z0-9])"
        + re.escape(normalised_phrase)
        + r"(?![a-z0-9])"
    )

    return bool(re.search(pattern, normalised_text))


GROUP_LABELS = {
    "bars_pubs": "Bars & pubs",
    "coffee_cafes": "Coffee shops & cafés",
    "hair_services": "Hair services",
    "beauty_wellness": "Beauty & wellness",
    "restaurants": "Restaurants",
    "nightlife_entertainment": "Nightlife & entertainment",
    "workspaces": "Workspaces",
    "other": "Other local business",
}


GROUP_RULES = {
    "bars_pubs": {
        "category_values": {
            "bars",
            "bar",
            "pub",
            "gay bar",
            "hookah bar",
        },
        "type_values": {
            "pub",
            "bar",
            "cocktail bar",
            "wine bar",
            "gastropub",
            "sports bar",
            "bar and grill",
            "gay bar",
            "lounge bar",
            "brewpub",
            "brewery",
            "taproom",
            "hookah bar",
        },
        "subtype_values": {
            "pub",
            "bar",
            "cocktail bar",
            "wine bar",
            "gastropub",
            "sports bar",
            "bar and grill",
            "gay bar",
            "lounge bar",
            "brewpub",
            "brewery",
            "taproom",
            "beer garden",
            "live music bar",
            "shisha bar",
        },
    },
    "coffee_cafes": {
        "category_values": {
            "coffee shops",
            "coffee shop",
            "cafés",
            "cafe",
            "bakery",
            "tea house",
        },
        "type_values": {
            "coffee shop",
            "cafe",
            "bakery",
            "tea room",
            "breakfast restaurant",
            "brunch restaurant",
            "coffee roastery",
            "coffee store",
        },
        "subtype_values": {
            "coffee shop",
            "cafe",
            "bakery",
            "tea room",
            "breakfast restaurant",
            "brunch restaurant",
            "coffee roastery",
            "coffee store",
            "sandwich shop",
            "cake shop",
            "tea shop",
        },
    },
    "hair_services": {
        "category_values": {
            "barber shop",
            "hairdresser",
            "hair salon",
            "hair replacement service",
        },
        "type_values": {
            "barber shop",
            "hairdresser",
            "hair salon",
            "hair extension technician",
            "hair replacement service",
            "hair extensions supplier",
        },
        "subtype_values": {
            "barber shop",
            "barbers school",
            "barber supply shop",
            "hairdresser",
            "hair salon",
            "hair extension technician",
            "hair replacement service",
            "hair extensions supplier",
        },
    },
    "beauty_wellness": {
        "category_values": {
            "beauty salon",
            "nail salon",
            "skin care clinic",
            "massage therapist",
            "make-up artist",
            "eyelash salon",
            "spa",
        },
        "type_values": {
            "beauty salon",
            "nail salon",
            "skin care clinic",
            "massage therapist",
            "make-up artist",
            "eyelash salon",
            "spa",
            "day spa",
            "waxing hair-removal service",
            "laser hair removal service",
            "beautician",
            "medical spa",
            "facial spa",
            "eyebrow bar",
        },
        "subtype_values": {
            "beauty salon",
            "nail salon",
            "skin care clinic",
            "massage therapist",
            "make-up artist",
            "eyelash salon",
            "spa",
            "day spa",
            "waxing hair-removal service",
            "laser hair removal service",
            "beautician",
            "medical spa",
            "facial spa",
            "eyebrow bar",
            "hair removal service",
        },
    },
    "restaurants": {
        "category_values": {
            "restaurants",
            "restaurant",
        },
        "type_values": {
            "restaurant",
            "bar and grill",
            "mediterranean restaurant",
            "french restaurant",
            "british restaurant",
            "vegan restaurant",
            "vegetarian restaurant",
            "breakfast restaurant",
            "brunch restaurant",
            "lunch restaurant",
        },
        "subtype_values": {
            "restaurant",
            "bar and grill",
            "mediterranean restaurant",
            "french restaurant",
            "british restaurant",
            "vegan restaurant",
            "vegetarian restaurant",
            "breakfast restaurant",
            "brunch restaurant",
            "lunch restaurant",
            "mexican restaurant",
            "moroccan restaurant",
        },
    },
    "nightlife_entertainment": {
        "category_values": {
            "live music venue",
            "night club",
            "events venue",
        },
        "type_values": {
            "live music venue",
            "night club",
            "events venue",
            "dance club",
            "music venue",
        },
        "subtype_values": {
            "live music venue",
            "night club",
            "events venue",
            "dance club",
            "music venue",
            "function room facility",
        },
    },
    "workspaces": {
        "category_values": {
            "coworking space",
            "office space rental agency",
        },
        "type_values": {
            "co-working space",
            "coworking space",
            "office rental agency",
            "business centre",
            "virtual office rental",
        },
        "subtype_values": {
            "co-working space",
            "coworking space",
            "office rental agency",
            "business centre",
            "virtual office rental",
        },
    },
}


GROUP_RELATIONSHIPS = {
    "bars_pubs": {
        "bars_pubs": 1.00,
        "nightlife_entertainment": 0.65,
        "restaurants": 0.35,
        "coffee_cafes": 0.10,
    },
    "coffee_cafes": {
        "coffee_cafes": 1.00,
        "restaurants": 0.55,
        "bars_pubs": 0.10,
    },
    "hair_services": {
        "hair_services": 1.00,
        "beauty_wellness": 0.35,
    },
    "beauty_wellness": {
        "beauty_wellness": 1.00,
        "hair_services": 0.35,
    },
    "restaurants": {
        "restaurants": 1.00,
        "bars_pubs": 0.45,
        "coffee_cafes": 0.45,
    },
    "nightlife_entertainment": {
        "nightlife_entertainment": 1.00,
        "bars_pubs": 0.70,
    },
    "workspaces": {
        "workspaces": 1.00,
        "coffee_cafes": 0.20,
    },
}


TRAIT_RULES = {
    "bars_pubs": {
        "Beer": {
            "about_true": [
                "offerings.beer",
                "highlights.great_beer_selection",
            ],
            "text_terms": [
                "craft beer",
                "real ale",
                "taproom",
            ],
        },
        "Cocktails": {
            "about_true": ["offerings.cocktails"],
            "text_terms": ["cocktail", "mixology"],
        },
        "Wine": {
            "about_true": [
                "offerings.wine",
                "highlights.great_wine_list",
            ],
            "text_terms": ["wine bar", "natural wine"],
        },
        "Food": {
            "about_true": [
                "offerings.food",
                "offerings.food_at_bar",
            ],
            "text_terms": [
                "bar food",
                "small plates",
                "gastropub",
            ],
        },
        "Live music": {
            "about_true": [
                "highlights.live_music",
                "highlights.live_performances",
            ],
            "text_terms": ["live music", "live band"],
        },
        "Dancing": {
            "about_true": ["offerings.dancing"],
            "text_terms": ["dance floor", "dancing", "dj"],
        },
        "Sports viewing": {
            "about_true": [],
            "text_terms": [
                "sports bar",
                "live sports",
                "football",
                "big screen",
            ],
        },
        "Quiz night": {
            "about_true": ["highlights.quiz_night"],
            "text_terms": ["quiz night", "pub quiz"],
        },
        "Bar games": {
            "about_true": ["highlights.bar_games"],
            "text_terms": ["bar games", "pool table"],
        },
        "Outdoor seating": {
            "about_true": [
                "service_options.outdoor_seating",
            ],
            "text_terms": [
                "beer garden",
                "terrace",
                "rooftop",
            ],
        },
        "Table service": {
            "about_true": [
                "dining_options.table_service",
            ],
            "text_terms": [],
        },
        "Reservations": {
            "about_true": [
                "planning.accepts_reservations",
            ],
            "text_terms": [
                "book a table",
                "reservations",
            ],
        },
        "Dog friendly": {
            "about_true": ["pets.dogs_allowed"],
            "text_terms": [
                "dog friendly",
                "dog-friendly",
            ],
        },
        "Wi-Fi": {
            "about_true": ["amenities.wi_fi"],
            "text_terms": ["wifi", "wi-fi"],
        },
        "Casual": {
            "about_true": ["atmosphere.casual"],
            "text_terms": [],
        },
        "Cosy": {
            "about_true": ["atmosphere.cosy"],
            "text_terms": [],
        },
        "Trendy": {
            "about_true": ["atmosphere.trendy"],
            "text_terms": [],
        },
    },
    "coffee_cafes": {
        "Speciality coffee": {
            "about_true": [],
            "text_terms": [
                "speciality coffee",
                "specialty coffee",
                "single origin",
                "pour over",
                "filter coffee",
                "coffee roastery",
            ],
        },
        "Brunch": {
            "about_true": [],
            "text_terms": ["brunch", "breakfast"],
        },
        "Pastries": {
            "about_true": [],
            "text_terms": [
                "pastry",
                "pastries",
                "croissant",
                "bakery",
            ],
        },
        "Vegan options": {
            "about_true": [],
            "text_terms": [
                "vegan",
                "plant based",
                "plant-based",
            ],
        },
        "Takeaway": {
            "about_true": [
                "service_options.takeaway",
            ],
            "text_terms": ["takeaway", "takeout"],
        },
        "Dine-in": {
            "about_true": [
                "service_options.dine_in",
            ],
            "text_terms": [],
        },
        "Delivery": {
            "about_true": [
                "service_options.delivery",
            ],
            "text_terms": [],
        },
        "Outdoor seating": {
            "about_true": [
                "service_options.outdoor_seating",
            ],
            "text_terms": ["terrace", "garden"],
        },
        "Wi-Fi": {
            "about_true": ["amenities.wi_fi"],
            "text_terms": ["wifi", "wi-fi", "laptop"],
        },
        "Dog friendly": {
            "about_true": ["pets.dogs_allowed"],
            "text_terms": [
                "dog friendly",
                "dog-friendly",
            ],
        },
    },
    "hair_services": {
        "Balayage": {
            "about_true": [],
            "text_terms": ["balayage"],
        },
        "Blonde": {
            "about_true": [],
            "text_terms": ["blonde", "blonding"],
        },
        "Hair colour": {
            "about_true": [],
            "text_terms": [
                "hair colour",
                "hair color",
                "colourist",
                "colorist",
                "colouring",
                "coloring",
            ],
        },
        "Highlights": {
            "about_true": [],
            "text_terms": ["highlights", "foils"],
        },
        "Colour correction": {
            "about_true": [],
            "text_terms": [
                "colour correction",
                "color correction",
            ],
        },
        "Hair extensions": {
            "about_true": [],
            "text_terms": [
                "hair extension",
                "extensions",
            ],
        },
        "Bridal hair": {
            "about_true": [],
            "text_terms": ["bridal", "wedding hair"],
        },
        "Men's hair": {
            "about_true": [],
            "text_terms": [
                "men's hair",
                "mens hair",
                "male grooming",
            ],
        },
        "Children's hair": {
            "about_true": [
                "children.good_for_kids",
            ],
            "text_terms": [
                "children's hair",
                "childrens hair",
                "kids haircut",
            ],
        },
        "Curly hair": {
            "about_true": [],
            "text_terms": [
                "curly",
                "curl specialist",
                "curls",
            ],
        },
        "Afro-textured hair": {
            "about_true": [],
            "text_terms": [
                "afro",
                "textured hair",
                "coily",
            ],
        },
        "Appointments": {
            "about_true": [
                "planning.appointment_required",
                "planning.appointments_recommended",
            ],
            "text_terms": [],
        },
    },
}


FORMAT_RELATIONSHIPS = {
    "Pub": {
        "Pub": 1.00,
        "Gastropub": 0.95,
        "Sports bar": 0.85,
        "Bar": 0.80,
        "Taproom / brewery": 0.80,
        "Music-led bar": 0.75,
        "Cocktail bar": 0.60,
        "Nightclub": 0.30,
        "Restaurant": 0.25,
    },
    "Barber": {
        "Barber": 1.00,
        "Men's hairdresser": 0.95,
        "Hairdresser": 0.80,
        "Hair salon": 0.70,
        "Beauty salon": 0.20,
    },
}
