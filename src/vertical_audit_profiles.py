from __future__ import annotations

from typing import Any


BASELINE_CHECKS: list[dict[str, Any]] = [
    {
        "key": "https",
        "label": "HTTPS",
        "category": "Technical foundation",
        "weight": 3,
        "run_field": "is_https",
        "recommendation": (
            "Serve the entire website securely over HTTPS."
        ),
    },
    {
        "key": "homepage_title",
        "label": "Homepage title",
        "category": "Technical foundation",
        "weight": 3,
        "run_field": "has_title",
        "recommendation": (
            "Add a clear, descriptive homepage title."
        ),
    },
    {
        "key": "meta_description",
        "label": "Meta description",
        "category": "Technical foundation",
        "weight": 2,
        "run_field": "has_meta_description",
        "recommendation": (
            "Add a useful homepage meta description."
        ),
    },
    {
        "key": "canonical",
        "label": "Canonical URL",
        "category": "Technical foundation",
        "weight": 2,
        "run_field": "has_canonical",
        "recommendation": (
            "Add a canonical link to the homepage."
        ),
    },
    {
        "key": "sitemap",
        "label": "XML sitemap",
        "category": "Machine readability",
        "weight": 3,
        "value_field": "sitemap_url",
        "recommendation": (
            "Publish and reference an XML sitemap."
        ),
    },
    {
        "key": "relevant_schema",
        "label": "Relevant local-business schema",
        "category": "Machine readability",
        "weight": 5,
        "schema_types": [
            "LocalBusiness",
            "Organization",
        ],
        "allow_local_schema_fallback": True,
        "recommendation": (
            "Add relevant Schema.org structured data "
            "describing the business and location."
        ),
    },
    {
        "key": "contact",
        "label": "Contact information",
        "category": "Entity clarity",
        "weight": 4,
        "run_field": "has_contact_signals",
        "recommendation": (
            "Expose clear contact information in "
            "crawlable page content."
        ),
    },
    {
        "key": "address",
        "label": "Address/location information",
        "category": "Entity clarity",
        "weight": 4,
        "run_field": "has_address_signals",
        "recommendation": (
            "Expose the full address and location details "
            "in crawlable page content."
        ),
    },
    {
        "key": "services",
        "label": "Service or offering coverage",
        "category": "Content coverage",
        "weight": 5,
        "run_field": "has_service_pages",
        "page_signal": "service_page",
        "recommendation": (
            "Create crawlable pages that clearly describe "
            "the main services or offerings."
        ),
    },
    {
        "key": "pricing",
        "label": "Pricing information",
        "category": "Content coverage",
        "weight": 4,
        "run_field": "has_pricing_page",
        "page_signal": "pricing_page",
        "page_terms": [
            "price list",
            "pricing",
            "our prices",
            "treatment prices",
        ],
        "url_terms": [
            "price",
            "pricing",
        ],
        "recommendation": (
            "Publish clear, crawlable pricing or "
            "indicative price information."
        ),
    },
    {
        "key": "faq",
        "label": "FAQ content",
        "category": "Content coverage",
        "weight": 4,
        "run_field": "has_faq_content",
        "page_signal": "faq_content",
        "page_terms": [
            "frequently asked questions",
            "common questions",
        ],
        "url_terms": [
            "faq",
            "faqs",
        ],
        "recommendation": (
            "Add useful FAQs that answer common customer "
            "questions in crawlable content."
        ),
    },
    {
        "key": "booking",
        "label": "Booking or reservation journey",
        "category": "Conversion journey",
        "weight": 4,
        "run_field": "has_booking_link",
        "page_signal": "booking_link",
        "page_terms": [
            "book now",
            "book online",
            "make a reservation",
            "book an appointment",
        ],
        "recommendation": (
            "Expose a prominent, crawlable booking or "
            "reservation route."
        ),
    },
    {
        "key": "social",
        "label": "Social-profile links",
        "category": "Entity connections",
        "weight": 2,
        "run_field": "has_social_links",
        "recommendation": (
            "Link clearly to the business's active "
            "social profiles."
        ),
    },
]


HAIR_CHECKS: list[dict[str, Any]] = [
    {
        "key": "hair_schema",
        "label": "Hair-salon-specific schema",
        "category": "Machine readability",
        "weight": 5,
        "schema_types": [
            "HairSalon",
            "BeautySalon",
            "HealthAndBeautyBusiness",
        ],
        "recommendation": (
            "Use HairSalon or another appropriate "
            "specialist local-business schema type."
        ),
    },
    {
        "key": "stylist_bios",
        "label": "Stylist or team biographies",
        "category": "Trust and expertise",
        "weight": 4,
        "page_terms": [
            "meet the team",
            "meet our team",
            "our stylists",
            "our hairdressers",
            "our colourists",
            "our colorists",
            "stylist profile",
        ],
        "url_terms": [
            "team",
            "stylists",
            "hairdressers",
        ],
        "recommendation": (
            "Publish stylist biographies covering "
            "experience, expertise and specialisms."
        ),
    },
    {
        "key": "consultations",
        "label": "Consultation information",
        "category": "Service clarity",
        "weight": 4,
        "page_terms": [
            "free consultation",
            "colour consultation",
            "color consultation",
            "book a consultation",
            "consultation appointment",
        ],
        "url_terms": [
            "consultation",
        ],
        "recommendation": (
            "Explain the consultation process and how "
            "customers can book one."
        ),
    },
    {
        "key": "gallery",
        "label": "Gallery or before-and-after work",
        "category": "Proof and differentiation",
        "weight": 4,
        "page_terms": [
            "before and after",
            "before & after",
            "our work",
            "hair gallery",
            "client transformations",
        ],
        "url_terms": [
            "gallery",
            "portfolio",
            "before-after",
            "our-work",
        ],
        "recommendation": (
            "Publish a crawlable gallery or before-and-"
            "after portfolio of client work."
        ),
    },
    {
        "key": "specialist_services",
        "label": "Specialist service coverage",
        "category": "Service clarity",
        "weight": 5,
        "page_terms": [
            "balayage",
            "colour correction",
            "color correction",
            "hair extensions",
            "curly hair",
            "creative colour",
            "creative color",
            "blonding",
        ],
        "url_terms": [
            "balayage",
            "colour",
            "color",
            "extensions",
            "curly",
        ],
        "recommendation": (
            "Create dedicated content for the salon's "
            "most valuable specialist services."
        ),
    },
]


BAR_PUB_CHECKS: list[dict[str, Any]] = [
    {
        "key": "bar_schema",
        "label": "Bar/pub/restaurant schema",
        "category": "Machine readability",
        "weight": 5,
        "schema_types": [
            "BarOrPub",
            "Restaurant",
            "FoodEstablishment",
        ],
        "recommendation": (
            "Use BarOrPub, Restaurant or another "
            "appropriate food-and-drink schema type."
        ),
    },
    {
        "key": "food_menu",
        "label": "Crawlable food menu",
        "category": "Offering clarity",
        "weight": 5,
        "run_field": "has_menu_page",
        "page_signal": "menu_page",
        "page_terms": [
            "food menu",
            "main menu",
            "lunch menu",
            "dinner menu",
            "sunday roast",
        ],
        "url_terms": [
            "food-menu",
            "menu",
            "food",
        ],
        "recommendation": (
            "Publish a crawlable and current food menu."
        ),
    },
    {
        "key": "drinks_menu",
        "label": "Drinks, beer, wine or cocktail menu",
        "category": "Offering clarity",
        "weight": 5,
        "page_terms": [
            "drinks menu",
            "cocktail menu",
            "wine list",
            "beer list",
            "our beers",
            "our cocktails",
        ],
        "url_terms": [
            "drinks",
            "cocktails",
            "wine",
            "beer",
        ],
        "recommendation": (
            "Publish a crawlable drinks, beer, wine or "
            "cocktail menu."
        ),
    },
    {
        "key": "events_music",
        "label": "Events or live-music information",
        "category": "Experience and occasions",
        "weight": 4,
        "page_terms": [
            "live music",
            "what's on",
            "whats on",
            "upcoming events",
            "live performances",
            "dj night",
            "quiz night",
        ],
        "url_terms": [
            "events",
            "whats-on",
            "what-s-on",
            "live-music",
        ],
        "recommendation": (
            "Publish crawlable information about events, "
            "live music or recurring entertainment."
        ),
    },
    {
        "key": "private_hire",
        "label": "Private-hire information",
        "category": "Experience and occasions",
        "weight": 4,
        "page_terms": [
            "private hire",
            "venue hire",
            "function room",
            "private party",
            "group bookings",
        ],
        "url_terms": [
            "private-hire",
            "venue-hire",
            "functions",
            "parties",
        ],
        "recommendation": (
            "Create a clear private-hire or group-booking "
            "page where relevant."
        ),
    },
    {
        "key": "outdoor_space",
        "label": "Outdoor-space information",
        "category": "Experience and occasions",
        "weight": 3,
        "page_terms": [
            "beer garden",
            "roof terrace",
            "rooftop terrace",
            "outdoor seating",
            "courtyard garden",
        ],
        "url_terms": [
            "garden",
            "terrace",
            "outdoor",
            "rooftop",
        ],
        "recommendation": (
            "Describe outdoor seating, gardens or terraces "
            "clearly in crawlable content."
        ),
    },
    {
        "key": "opening_hours",
        "label": "Opening-hours information",
        "category": "Entity clarity",
        "weight": 4,
        "page_terms": [
            "opening hours",
            "opening times",
            "hours of operation",
            "monday",
            "tuesday",
        ],
        "recommendation": (
            "Publish clear opening hours in crawlable "
            "website content and structured data."
        ),
    },
    {
        "key": "accessibility",
        "label": "Accessibility information",
        "category": "Customer information",
        "weight": 3,
        "page_terms": [
            "accessibility",
            "wheelchair accessible",
            "wheelchair-accessible",
            "accessible entrance",
            "disabled access",
        ],
        "url_terms": [
            "accessibility",
            "access",
        ],
        "recommendation": (
            "Publish practical accessibility information."
        ),
    },
]


COFFEE_CHECKS: list[dict[str, Any]] = [
    {
        "key": "cafe_schema",
        "label": "Café/restaurant schema",
        "category": "Machine readability",
        "weight": 5,
        "schema_types": [
            "CafeOrCoffeeShop",
            "Restaurant",
            "FoodEstablishment",
        ],
        "recommendation": (
            "Use CafeOrCoffeeShop or another appropriate "
            "food-establishment schema type."
        ),
    },
    {
        "key": "menu",
        "label": "Crawlable menu",
        "category": "Offering clarity",
        "weight": 5,
        "run_field": "has_menu_page",
        "page_signal": "menu_page",
        "page_terms": [
            "coffee menu",
            "brunch menu",
            "breakfast menu",
            "food menu",
        ],
        "url_terms": [
            "menu",
            "food",
            "brunch",
        ],
        "recommendation": (
            "Publish a crawlable coffee and food menu."
        ),
    },
    {
        "key": "opening_hours",
        "label": "Opening-hours information",
        "category": "Entity clarity",
        "weight": 4,
        "page_terms": [
            "opening hours",
            "opening times",
            "monday",
            "tuesday",
        ],
        "recommendation": (
            "Publish clear opening hours in crawlable "
            "website content."
        ),
    },
    {
        "key": "workspace_signals",
        "label": "Wi-Fi or workspace information",
        "category": "Experience and occasions",
        "weight": 3,
        "page_terms": [
            "free wi-fi",
            "free wifi",
            "laptop friendly",
            "work from",
            "remote working",
        ],
        "recommendation": (
            "Clarify Wi-Fi and laptop-working suitability "
            "where this is part of the proposition."
        ),
    },
]


PROFILE_LABELS = {
    "hair_services": "Hair-services website benchmark",
    "bars_pubs": "Bars and pubs website benchmark",
    "coffee_cafes": "Coffee shops and cafés website benchmark",
    "generic": "Generic local-business website benchmark",
}


def get_audit_profile(
    primary_group: str,
) -> dict[str, Any]:
    group = str(primary_group or "generic")

    vertical_checks = {
        "hair_services": HAIR_CHECKS,
        "bars_pubs": BAR_PUB_CHECKS,
        "coffee_cafes": COFFEE_CHECKS,
    }.get(group, [])

    return {
        "key": group,
        "label": PROFILE_LABELS.get(
            group,
            PROFILE_LABELS["generic"],
        ),
        "checks": [
            *BASELINE_CHECKS,
            *vertical_checks,
        ],
    }
