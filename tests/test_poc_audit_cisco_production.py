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


GOLDEN_CISCO_PAYLOAD_SHA256 = (
    "fac0cf2db538b18dc440ad732251352602d1da57b508a7306b22cdaaf6d92a31"
)


@unittest.skipUnless(
    os.getenv("POC_AUDIT_VERIFY_CISCO") == "1",
    "set POC_AUDIT_VERIFY_CISCO=1 for the read-only production-path check",
)
class CiscoProductionPathTests(unittest.TestCase):
    def test_read_only_golden_evidence_to_pdf(self):
        with patch("requests.request", side_effect=AssertionError("external API forbidden")), \
             patch("requests.get", side_effect=AssertionError("external API forbidden")), \
             patch("requests.post", side_effect=AssertionError("external API forbidden")):
            definition = find_poc_audit_definition(
                baseline_run_id="631f46d0-8361-47b0-aa8c-6e544de0eca3",
                target_google_place_id="ChIJP6-pRwqFdUgRZotaM4dbr7w",
            )
            self.assertIsNotNone(definition)
            reviewable = build_reviewable_poc_audit(definition)
            payload = reviewable.payload
            pdf_bytes = reviewable.pdf_bytes

        self.assertEqual(payload_sha256(payload), GOLDEN_CISCO_PAYLOAD_SHA256)
        self.assertEqual(reviewable.payload_sha256, GOLDEN_CISCO_PAYLOAD_SHA256)
        counts = payload["primary_evidence_counts"]
        self.assertEqual(counts["ai_raw_responses"], 72)
        self.assertEqual(counts["recommendation_slots"], 287)
        self.assertEqual(payload["recommendation_market"]["business_slot_count"], 251)
        self.assertEqual(payload["recommendation_market"]["non_business_slot_count"], 36)
        self.assertEqual(counts["website_pages"], 52)
        self.assertEqual(counts["review_records"], 263)
        self.assertEqual(len(payload["diagnostic"]["cohort"]), 3)
        self.assertEqual(len(payload["report"]["full_action_plan"]), 5)
        self.assertEqual(len(payload["report"]["priority_actions"]), 3)
        self.assertEqual(payload["baseline_validation"]["explicit_target_recommendations"], 0)
        self.assertEqual(payload["baseline_validation"]["possible_indirect_target_recommendations"], 0)
        for response in payload["baseline_validation"]["responses"]:
            self.assertEqual(response["raw_response_sha256"], sha256_text(response["raw_response"]))
        for review_set in payload["review_evidence"]["review_sets"]:
            self.assertEqual(review_set["records_sha256"], sha256_json(review_set["records"]))
        reader = PdfReader(io.BytesIO(pdf_bytes))
        self.assertEqual(len(reader.pages), 13)
        text = " ".join(" ".join(page.extract_text().split()) for page in reader.pages)
        for expected in (
            "0 of 72", "251 recommendations of named businesses were analysed",
            "11.95%", "9.16%", "8.37%", "Cuttlefish Eco Salons",
            "Trevor Sorbie Brighton", "Simon Webster Hair",
            "What customers might ask AI", "WHAT THIS MEANS",
            "What appears different about the businesses AI recommends",
            "Methodology and limitations",
        ):
            self.assertIn(expected, text)
        prompt_page = " ".join((reader.pages[2].extract_text() or "").split())
        self.assertEqual(prompt_page.count("Cisco's Karma: NOT RECOMMENDED"), 8)
        review_exception = payload["review_evidence"]["review_sets"][3]["exception"]
        self.assertIn(review_exception["comparison_treatment"], text)
        exact_prompts = {item["prompt_text"] for item in payload["methodology"]["queries"]}
        self.assertEqual(len(exact_prompts), 8)
        for prompt in exact_prompts:
            self.assertIn(prompt, text)
        for page_number, page in enumerate(reader.pages, start=1):
            page_text = " ".join((page.extract_text() or "").split())
            self.assertEqual(page_text.count(f"{page_number} / 13"), 1)


if __name__ == "__main__":
    unittest.main()
