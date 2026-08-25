from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from pypdf import PdfReader

from src.poc_audit_pdf import PdfRenderError, render_poc_audit_pdf
from src.poc_audit_payload import PayloadValidationError
from tests.poc_audit_pdf_fixture import synthetic_poc_audit_payload


class PocAuditPdfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = synthetic_poc_audit_payload()
        cls.pdf_bytes = render_poc_audit_pdf(cls.payload)
        cls.reader = PdfReader(__import__("io").BytesIO(cls.pdf_bytes))
        cls.text = "\n".join(page.extract_text() or "" for page in cls.reader.pages)
        cls.normalized_text = " ".join(cls.text.split())

    def test_pdf_opens_and_has_exact_page_count(self):
        self.assertTrue(self.pdf_bytes.startswith(b"%PDF-"))
        self.assertEqual(len(self.reader.pages), 12)

    def test_required_page_headings_appear(self):
        headings = [
            "The finding in one minute",
            "Example Salon's AI visibility baseline",
            "Who AI recommends instead",
            "Different assistants favour different businesses",
            "Three useful comparison businesses",
            "The evidence across the four businesses",
            "A credible foundation to build on",
            "Where the discoverability evidence is weakest",
            "The three actions we recommend first",
            "From baseline to measurable improvement",
            "Methodology and limitations",
        ]
        for heading in headings:
            with self.subTest(heading=heading):
                self.assertIn(heading, self.normalized_text)

    def test_headline_and_market_figures_appear(self):
        for expected in ("0 of 3", "33.33%", "3"):
            with self.subTest(expected=expected):
                self.assertIn(expected, self.normalized_text)

    def test_selected_leaders_appear(self):
        for leader in (
            "Alpha Salon", "Beta Salon", "Gamma Salon",
        ):
            with self.subTest(leader=leader):
                self.assertIn(leader, self.normalized_text)

    def test_review_exception_appears(self):
        self.assertIn("Gamma review evidence is unavailable", self.normalized_text)
        self.assertIn("review evidence is unavailable", self.normalized_text)

    def test_priority_actions_appear(self):
        actions = [
            "Synthetic action 1", "Synthetic action 2", "Synthetic action 3",
        ]
        for action in actions:
            with self.subTest(action=action):
                self.assertIn(action, self.normalized_text)

    def test_methodology_and_non_causality_appear(self):
        self.assertIn(
            "Synthetic model-memory benchmark",
            self.normalized_text,
        )
        self.assertIn(
            "a proven AI ranking factor",
            self.normalized_text,
        )
        self.assertIn(
            "No visibility outcome is guaranteed",
            self.normalized_text,
        )

    def test_malformed_payload_is_rejected(self):
        malformed = copy.deepcopy(self.payload)
        malformed["baseline_validation"]["responses"][0][
            "raw_response"
        ] = "tampered"
        with self.assertRaises(PayloadValidationError):
            render_poc_audit_pdf(malformed)

    def test_incomplete_report_is_rejected(self):
        incomplete = copy.deepcopy(self.payload)
        incomplete["report"].pop("priority_actions")
        with self.assertRaises(PdfRenderError):
            render_poc_audit_pdf(incomplete)

    def test_material_evidence_removals_are_rejected(self):
        mutations = [
            lambda p: p["report"]["visibility"].update({"responses_complete": 2}),
            lambda p: p["report"]["recommendation_market"].update({"business_slots": 2}),
            lambda p: p["report"]["diagnostic_cohort"].pop(),
            lambda p: p["website_evidence"].update({"audits": []}),
            lambda p: p["review_evidence"].update({"review_sets": []}),
            lambda p: p["diagnostic"].update({"analyst_decisions": {}}),
            lambda p: p["report"].update({"full_action_plan": []}),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                malformed = copy.deepcopy(self.payload)
                mutation(malformed)
                with self.assertRaises((PdfRenderError, PayloadValidationError)):
                    render_poc_audit_pdf(malformed)

    def test_rendering_never_opens_a_database(self):
        with patch(
            "src.database.get_engine",
            side_effect=AssertionError("database access is forbidden"),
        ):
            rendered = render_poc_audit_pdf(self.payload)
        self.assertTrue(rendered.startswith(b"%PDF-"))

    def test_output_is_deterministic(self):
        self.assertEqual(
            self.pdf_bytes,
            render_poc_audit_pdf(self.payload),
        )

    def test_unicode_apostrophe_and_dash_render(self):
        payload = copy.deepcopy(self.payload)
        payload["audit"]["target_business_name"] = "Example’s Salon – North"
        rendered = render_poc_audit_pdf(payload)
        text = " ".join(
            page.extract_text() or ""
            for page in PdfReader(__import__("io").BytesIO(rendered)).pages
        )
        self.assertIn("Example’s Salon – North", text)


if __name__ == "__main__":
    unittest.main()
