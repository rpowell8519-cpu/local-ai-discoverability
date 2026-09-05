from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from pypdf import PdfReader

from src.poc_audit_pdf import PdfRenderError, render_poc_audit_pdf
from src.poc_audit_payload import PayloadValidationError, sha256_json
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
        self.assertEqual(len(self.reader.pages), 13)

    def test_required_page_headings_appear(self):
        headings = [
            "Example Salon appeared in 0 of 24 AI responses",
            "What customers might ask AI - did Example Salon appear?",
            "These are the businesses AI recommended instead",
            "Different AI assistants produced different competitor lists",
            "Why we compared these three AI-recommended businesses",
            "What appears different about the businesses AI recommends",
            "Example Salon already has useful strengths to build on",
            "The biggest opportunities are clear and practical",
            "The three actions we recommend first",
            "What happens next",
            "Methodology and limitations",
            "Prompts tested",
        ]
        for heading in headings:
            with self.subTest(heading=heading):
                self.assertIn(heading, self.normalized_text)

    def test_headline_and_market_figures_appear(self):
        for expected in ("0 of 24", "33.33%", "3"):
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

    def test_all_exact_frozen_prompts_appear(self):
        expected = {
            item["prompt_text"]
            for item in self.payload["methodology"]["queries"]
        }
        self.assertEqual(len(expected), 8)
        for prompt in expected:
            with self.subTest(prompt=prompt):
                self.assertIn(prompt, self.normalized_text)

    def test_main_story_uses_plain_language_and_interpretation(self):
        main_story = " ".join(
            " ".join((page.extract_text() or "").split())
            for page in self.reader.pages[1:11]
        )
        for expected in (
            "WHAT THIS MEANS",
            "recommendations of named businesses were analysed",
            "AI assistants recommending them",
            "Customer questions they appeared for",
            "WHAT THIS INVOLVES",
            "WHY THIS COMES FIRST",
            "THE PRACTICAL BENEFIT",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, main_story)
        for technical_term in ("parsed slots", "valid business slots", "provider breadth"):
            with self.subTest(technical_term=technical_term):
                self.assertNotIn(technical_term, main_story.lower())

    def test_each_main_prompt_has_a_reconciled_target_outcome(self):
        prompt_page = " ".join((self.reader.pages[2].extract_text() or "").split())
        self.assertEqual(prompt_page.count("Example Salon: NOT RECOMMENDED"), 8)

    def test_missing_or_inconsistent_prompt_evidence_is_rejected(self):
        missing = copy.deepcopy(self.payload)
        missing["methodology"]["queries"].pop()
        with self.assertRaises(PdfRenderError):
            render_poc_audit_pdf(missing)

        inconsistent = copy.deepcopy(self.payload)
        inconsistent["baseline_validation"]["responses"][0]["prompt_text"] = "Different prompt"
        inconsistent["baseline_validation"]["response_audit_sha256"] = sha256_json(
            inconsistent["baseline_validation"]["responses"]
        )
        with self.assertRaises(PdfRenderError):
            render_poc_audit_pdf(inconsistent)

    def test_page_number_footer_appears_once_per_page(self):
        for page_number, page in enumerate(self.reader.pages, start=1):
            text = " ".join((page.extract_text() or "").split())
            marker = f"{page_number} / 13"
            self.assertEqual(text.count(marker), 1, marker)

    def test_accessible_beta_report_adds_method_and_verbatim_review_pages(self):
        payload = copy.deepcopy(self.payload)
        payload["report"].update({
            "report_format": "beta_accessible_v2",
            "introduction": {
                "owner_priority": "Example Salon wants to be known for service alpha and service beta.",
                "method_steps": [
                    {"title": "Start with owner priorities", "body": "Turn the owner's goals into realistic customer questions."},
                    {"title": "Test three AI platforms", "body": "Ask each platform the same questions and check every completed answer."},
                    {"title": "Compare public evidence", "body": "Review visible businesses alongside the client's website and reviews."},
                ],
                "scope_note": "This is a dated snapshot designed to support a useful owner conversation.",
            },
            "review_quotes": [
                {"review_id": "review-target-place", "google_place_id": "target-place",
                 "business_name": "Example Salon", "quote": "A useful synthetic review.",
                 "takeaway": "An example of existing customer evidence."},
                {"review_id": "review-place-a", "google_place_id": "place-a",
                 "business_name": "Alpha Salon", "quote": "A useful synthetic review.",
                 "takeaway": "A comparison example."},
                {"review_id": "review-place-b", "google_place_id": "place-b",
                 "business_name": "Beta Salon", "quote": "A useful synthetic review.",
                 "takeaway": "A second comparison example."},
            ],
            "question_performance": [
                {
                    "order": query["base_prompt_order"],
                    "prompt_category": query["prompt_category"],
                    "prompt_text": query["prompt_text"],
                    "answer_count": 3,
                    "target_appearances": 0,
                    "target_best_position": None,
                    "leaders": [{"google_place_id": "place-a", "business_name": "Alpha Salon",
                                 "appearances": 1, "best_position": 1, "average_position": 1.0,
                                 "providers": ["OpenAI"]}],
                    "provider_results": [
                        {"provider": provider, "answer_count": 1,
                         "leaders": [{"google_place_id": f"place-{letter}", "business_name": name,
                                      "appearances": 1, "best_position": 1, "average_position": 1.0,
                                      "providers": [provider]}]}
                        for provider, letter, name in (
                            ("OpenAI", "a", "Alpha Salon"),
                            ("Claude", "b", "Beta Salon"),
                            ("Gemini", "c", "Gamma Salon"),
                        )
                    ],
                }
                for query in payload["methodology"]["queries"]
            ],
        })
        rendered = render_poc_audit_pdf(payload)
        reader = PdfReader(__import__("io").BytesIO(rendered))
        self.assertEqual(len(reader.pages), 17)
        text = " ".join(" ".join((page.extract_text() or "").split()) for page in reader.pages)
        self.assertIn("How we explored your visibility in AI recommendations", text)
        self.assertIn("What customers say in their own words", text)
        self.assertIn("Question-by-question detail (1 of 2)", text)
        for page_number, page in enumerate(reader.pages, start=1):
            page_text = " ".join((page.extract_text() or "").split())
            self.assertEqual(page_text.count(f"{page_number} / 17"), 1)

        payload["report"]["review_quotes"][0]["quote"] = "Edited quotation."
        with self.assertRaisesRegex(PdfRenderError, "not verbatim"):
            render_poc_audit_pdf(payload)

    def test_rendering_never_opens_a_database(self):
        with patch(
            "src.database.get_engine",
            side_effect=AssertionError("database access is forbidden"),
        ):
            rendered = render_poc_audit_pdf(self.payload)
        self.assertTrue(rendered.startswith(b"%PDF-"))

    def test_renderer_source_contains_no_client_specific_truth(self):
        source = __import__("pathlib").Path("src/poc_audit_pdf.py").read_text()
        for forbidden in (
            "Cisco's Karma", "Cuttlefish Eco Salons", "Trevor Sorbie Brighton",
            "Simon Webster Hair", "11.95%", "9.16%", "8.37%",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

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
