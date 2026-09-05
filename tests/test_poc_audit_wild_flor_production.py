from __future__ import annotations

import io
import os
import unittest
from unittest.mock import patch

from pypdf import PdfReader

from src.poc_audit_payload import payload_sha256, sha256_json, sha256_text
from src.poc_audit_production import (
    build_reviewable_poc_audit,
    find_poc_audit_definition,
)


GOLDEN_WILD_FLOR_PAYLOAD_SHA256 = (
    "dc15dff60b057967bd9aea939de82c6219b3d9a29838f5feedeb82774a4c1a93"
)


@unittest.skipUnless(
    os.getenv("POC_AUDIT_VERIFY_WILD_FLOR") == "1",
    "set POC_AUDIT_VERIFY_WILD_FLOR=1 for the read-only production-path check",
)
class WildFlorProductionPathTests(unittest.TestCase):
    def test_read_only_evidence_to_pdf(self):
        with patch("requests.request", side_effect=AssertionError("external API forbidden")), \
             patch("requests.get", side_effect=AssertionError("external API forbidden")), \
             patch("requests.post", side_effect=AssertionError("external API forbidden")):
            definition = find_poc_audit_definition(
                baseline_run_id="3c5a98b6-41f1-4cec-b7fe-4e788a4ab8f1",
                target_google_place_id="ChIJOc835RGFdUgRWxPGO6RNcoc",
            )
            self.assertIsNotNone(definition)
            reviewable = build_reviewable_poc_audit(definition)
            payload = reviewable.payload
            pdf_bytes = reviewable.pdf_bytes

        counts = payload["primary_evidence_counts"]
        self.assertEqual(counts["ai_raw_responses"], 72)
        self.assertEqual(payload["baseline_validation"]["complete_raw_responses"], 71)
        self.assertEqual(counts["recommendation_slots"], 353)
        self.assertEqual(payload["recommendation_market"]["business_slot_count"], 353)
        self.assertEqual(payload["recommendation_market"]["non_business_slot_count"], 0)
        self.assertEqual(counts["website_audits"], 4)
        self.assertEqual(counts["website_pages"], 43)
        self.assertEqual(counts["review_records"], 400)
        self.assertEqual(len(payload["diagnostic"]["cohort"]), 3)
        self.assertEqual(len(payload["report"]["full_action_plan"]), 5)
        self.assertEqual(len(payload["report"]["priority_actions"]), 3)
        visibility = payload["report"]["visibility"]
        self.assertEqual(visibility["recommendations"], 36)
        self.assertEqual(visibility["market_rank"], 4)
        self.assertAlmostEqual(visibility["business_sor_pct"], 10.1983002833)
        self.assertEqual(
            {item["name"]: item["recommendations"] for item in visibility["providers"]},
            {"OpenAI": 14, "Claude": 0, "Gemini": 22},
        )
        for response in payload["baseline_validation"]["responses"]:
            self.assertEqual(response["raw_response_sha256"], sha256_text(response["raw_response"]))
        for review_set in payload["review_evidence"]["review_sets"]:
            self.assertEqual(review_set["record_count"], 100)
            self.assertEqual(review_set["records_sha256"], sha256_json(review_set["records"]))

        reader = PdfReader(io.BytesIO(pdf_bytes))
        self.assertEqual(len(reader.pages), 13)
        text = " ".join(" ".join((page.extract_text() or "").split()) for page in reader.pages)
        for expected in (
            "Wild Flor appeared in 36 of 71 AI responses",
            "Wild Flor ranks #4 in the measured recommendation market",
            "13.60%", "11.90%", "6.23%",
            "etch. by Steven Edwards",
            "The Ginger Pig - Restaurant & Rooms",
            "FOURTH AND CHURCH",
            "RECOMMENDED IN 6 OF 8 RESPONSES",
            "Methodology and limitations",
            "Prompts tested",
        ):
            self.assertIn(expected, text)
        prompt_page = " ".join((reader.pages[2].extract_text() or "").split())
        self.assertEqual(prompt_page.count("Wild Flor: RECOMMENDED IN"), 8)
        self.assertEqual(len({item["prompt_text"] for item in payload["methodology"]["queries"]}), 8)
        self.assertEqual(payload_sha256(payload), GOLDEN_WILD_FLOR_PAYLOAD_SHA256)
        self.assertEqual(reviewable.payload_sha256, GOLDEN_WILD_FLOR_PAYLOAD_SHA256)


if __name__ == "__main__":
    unittest.main()
