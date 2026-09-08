from __future__ import annotations

import copy
import unittest

from src.poc_audit_production import (
    PocAuditDefinition,
    build_reviewable_poc_audit,
    find_poc_audit_definition,
    list_report_generator_definitions,
)
from src.poc_audit_payload import payload_sha256, sha256_bytes
from tests.poc_audit_pdf_fixture import synthetic_poc_audit_payload


PDF = b"%PDF-1.4\n1 0 obj<</Type /Page>>endobj\n%%EOF"


class PocAuditProductionTests(unittest.TestCase):
    def setUp(self):
        self.payload = synthetic_poc_audit_payload()
        audit = self.payload["audit"]
        self.definition = PocAuditDefinition(
            key="synthetic",
            baseline_run_id=str(audit["baseline_run_id"]),
            target_google_place_id=str(audit["target_google_place_id"]),
            client_name=str(audit["target_business_name"]),
            pdf_filename="synthetic.pdf",
            assembler=lambda: copy.deepcopy(self.payload),
            approved_payload_sha256=payload_sha256(self.payload),
        )

    def test_one_action_returns_validated_payload_and_exact_pdf_bytes(self):
        rendered_payloads = []

        def renderer(payload):
            rendered_payloads.append(payload)
            return PDF

        result = build_reviewable_poc_audit(self.definition, renderer=renderer)
        self.assertEqual(result.payload_sha256, payload_sha256(self.payload))
        self.assertIs(rendered_payloads[0], result.payload)
        self.assertIs(result.pdf_bytes, PDF)
        self.assertEqual(result.pdf_sha256, sha256_bytes(PDF))

    def test_golden_hash_mismatch_fails_before_render(self):
        bad = copy.deepcopy(self.payload)
        bad["report"]["executive_summary"]["headline"] = "Changed conclusion"
        definition = PocAuditDefinition(
            **{**self.definition.__dict__, "assembler": lambda: bad}
        )
        with self.assertRaisesRegex(ValueError, "approved audit hash"):
            build_reviewable_poc_audit(
                definition,
                renderer=lambda payload: self.fail("renderer must not run"),
            )

    def test_identity_mismatch_fails_before_render(self):
        definition = PocAuditDefinition(
            **{**self.definition.__dict__, "target_google_place_id": "wrong"}
        )
        with self.assertRaisesRegex(ValueError, "target"):
            build_reviewable_poc_audit(definition, renderer=lambda payload: PDF)

    def test_invalid_pdf_fails(self):
        with self.assertRaisesRegex(ValueError, "valid PDF"):
            build_reviewable_poc_audit(self.definition, renderer=lambda payload: b"")

    def test_registry_resolves_exact_run_and_place_id_only(self):
        cisco = find_poc_audit_definition(
            baseline_run_id="631f46d0-8361-47b0-aa8c-6e544de0eca3",
            target_google_place_id="ChIJP6-pRwqFdUgRZotaM4dbr7w",
        )
        self.assertEqual(cisco.key, "ciscos_karma")
        self.assertIsNone(find_poc_audit_definition(
            baseline_run_id=cisco.baseline_run_id,
            target_google_place_id="discovery:unresolved",
        ))

    def test_report_generator_lists_only_accessible_owner_services_reports(self):
        definitions = list_report_generator_definitions()

        self.assertEqual(
            [item.key for item in definitions],
            ["udr_owner_services", "ciscos_karma_owner_services"],
        )
        self.assertEqual(
            definitions[1].baseline_run_id,
            "80cf853d-4e7c-4f7c-a446-bf7f40d6dddf",
        )
        self.assertTrue(
            all(item.report_template == "accessible_owner_services_v1" for item in definitions)
        )


if __name__ == "__main__":
    unittest.main()
