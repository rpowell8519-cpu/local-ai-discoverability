from __future__ import annotations

import unittest

import pandas as pd

from src.ai_recommendation_intelligence import (
    build_recommendation_records,
    extract_numbered_recommendations,
)
from src.ai_visibility_analysis import analyse_visibility_response


class RecommendationExtractionTests(unittest.TestCase):
    def test_numbered_markdown_heading_is_extracted(self):
        rows = extract_numbered_recommendations(
            "## 1. **Brighton Salon** - strong local option\n2) Other Salon: good colour work"
        )

        self.assertEqual(
            rows,
            [
                {"position": 1, "raw_business_name": "Brighton Salon"},
                {"position": 2, "raw_business_name": "Other Salon"},
            ],
        )

    def test_numbered_advice_and_platform_names_are_not_businesses(self):
        rows = extract_numbered_recommendations(
            "1. Search Instagram - look at recent work\n"
            "2. Trustpilot or Yelp - compare reviews\n"
            "3. Ask your letting agent: they may know someone\n"
            "4. Contacting a trade association - request member referrals\n"
            "5. ChecXatrader or Trustpilot - compare listings\n"
            "6. Real Cleaning Company - a local option"
        )

        self.assertEqual(
            rows,
            [{"position": 6, "raw_business_name": "Real Cleaning Company"}],
        )

    def test_target_mention_inside_another_business_entry_is_not_a_recommendation(self):
        result = analyse_visibility_response(
            response_text=(
                "1. Other Salon - a strong alternative if Cisco's Karma is unavailable.\n"
                "2. Third Salon - another option."
            ),
            target_google_place_id="target-id",
            target_business_name="Cisco's Karma",
            known_businesses=[
                {"google_place_id": "target-id", "business_name": "Cisco's Karma"},
                {"google_place_id": "other-id", "business_name": "Other Salon"},
            ],
        )

        self.assertTrue(result["target_mentioned"])
        self.assertFalse(result["target_recommended"])
        self.assertIsNone(result["target_position"])

    def test_one_business_is_counted_once_per_answer_after_alias_resolution(self):
        results = pd.DataFrame(
            [
                {
                    "query_id": "query-1",
                    "base_prompt_order": 1,
                    "repeat_index": 1,
                    "prompt_category": "General",
                    "prompt_text": "Recommend a salon",
                    "provider": "OpenAI",
                    "model": "example-model",
                    "status": "completed",
                    "response_complete": True,
                    "raw_response": "1. The Example Salon\n2. Example Salon",
                }
            ]
        )
        businesses = pd.DataFrame(
            [
                {
                    "google_place_id": "example-id",
                    "business_name": "The Example Salon",
                    "primary_group": "hair_services",
                    "business_format": "Hair salon",
                }
            ]
        )

        records = build_recommendation_records(
            results=results,
            businesses=businesses,
            target_google_place_id="target-id",
            commercial_competitor_ids=set(),
            primary_group="hair_services",
        )

        self.assertEqual(len(records), 1)
        self.assertEqual(records.iloc[0]["google_place_id"], "example-id")
        self.assertEqual(records.iloc[0]["position"], 1)


if __name__ == "__main__":
    unittest.main()
