VERTICAL_PROFILES = {
    "Hair salon": {
        "matching_types": [
            "Hairdresser",
            "Hair salon",
            "Hair extension technician",
        ],
        "traits": {
            "Balayage": ["balayage"],
            "Blonde": ["blonde", "blonding"],
            "Hair extensions": ["extensions"],
            "Bridal": ["bridal", "wedding hair"],
        },
        "excluded_types": [
            "Nail salon",
            "Massage spa",
        ],
        "default_distance_miles": 5,
    },

    "Coffee shop": {
        "matching_types": [
            "Coffee shop",
            "Cafe",
            "Brunch restaurant",
        ],
        "traits": {
            "Speciality coffee": [
                "speciality coffee",
                "specialty coffee",
                "single origin",
            ],
            "Brunch": ["brunch", "breakfast"],
            "Laptop friendly": [
                "wifi",
                "wi-fi",
                "laptop",
            ],
        },
        "default_distance_miles": 3,
    },
}
