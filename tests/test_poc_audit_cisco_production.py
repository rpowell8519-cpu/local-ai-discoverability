from __future__ import annotations

import io
import os
import unittest
from unittest.mock import patch

from pypdf import PdfReader

from src.poc_audit_cisco_assembler import assemble_ciscos_karma_payload
from src.poc_audit_pdf import render_poc_audit_pdf
from src.poc_audit_payload import payload_sha256, sha256_json, sha256_text


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
            payload = assemble_ciscos_karma_payload()
            pdf_bytes = render_poc_audit_pdf(payload)

        self.assertEqual(payload_sha256(payload), GOLDEN_CISCO_PAYLOAD_SHA256)
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
        self.assertEqual(len(reader.pages), 12)
        text = " ".join(" ".join(page.extract_text().split()) for page in reader.pages)
        for expected in ("0 of 72", "251", "Cuttlefish Eco Salons", "Trevor Sorbie Brighton",
                         "Simon Webster Hair", "Methodology and limitations"):
            self.assertIn(expected, text)


if __name__ == "__main__":
    unittest.main()
