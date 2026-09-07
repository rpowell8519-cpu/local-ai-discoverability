from __future__ import annotations

import unittest

from src.ai_prompt_generator import generate_prompts
from src.feature_extraction import extract_business_features


class CleaningServicesTests(unittest.TestCase):
    def test_udr_style_record_is_classified_as_cleaning_services(self):
        features = extract_business_features(
            {
                "place_id": "cleaning-place-id",
                "name": "Example Cleaning Company",
                "category": "Cleaners",
                "type": "Cleaners",
                "subtypes": (
                    "Cleaners, Carpet cleaning service, House cleaning service, "
                    "Upholstery cleaning service"
                ),
            }
        )

        self.assertEqual(features["primary_group"], "cleaning_services")
        self.assertEqual(features["business_format"], "Cleaning company")
        self.assertIn("Carpet cleaning", features["traits"])
        self.assertIn("Upholstery cleaning", features["traits"])

    def test_cleaning_prompts_cover_priority_services(self):
        prompts = generate_prompts(
            primary_group="cleaning_services",
            location="Brighton",
        )
        combined = " ".join(prompts["prompt"].tolist()).lower()

        for expected in (
            "commercial premises",
            "office cleaning",
            "end-of-tenancy",
            "carpet cleaning",
            "upholstery cleaning",
            "laundry service",
        ):
            self.assertIn(expected, combined)


if __name__ == "__main__":
    unittest.main()
