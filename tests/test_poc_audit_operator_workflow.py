from __future__ import annotations

import copy
import unittest

from src.poc_audit_operator_workflow import (
    APPROVAL_KEYS, bind_pdf_preview, bind_reviewable_report, freeze_initial_snapshot, freeze_readiness,
    revision_one_metadata, stored_pdf_bytes, sync_payload_session,
)
from src.poc_audit_payload import payload_sha256, sha256_bytes
from src.poc_audit_production import PocAuditDefinition, ReviewablePocAudit
from tests.poc_audit_pdf_fixture import synthetic_poc_audit_payload


PDF = b"%PDF-1.4\n1 0 obj<</Type /Page>>endobj\n%%EOF"


def approved() -> dict[str, bool]:
    return {key: True for key in APPROVAL_KEYS}


class PocAuditOperatorWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.payload = synthetic_poc_audit_payload()
        self.payload_hash = payload_sha256(self.payload)

    def readiness(self, **overrides):
        values = dict(payload_valid=True, canonical_hash=self.payload_hash,
                      preview_bytes=PDF, preview_payload_hash=self.payload_hash,
                      approvals=approved(), confirmation="FREEZE", frozen_by="Operator",
                      existing_snapshot=None)
        values.update(overrides)
        return freeze_readiness(**values)

    def test_freeze_disabled_with_failed_payload_validation(self):
        self.assertFalse(self.readiness(payload_valid=False).enabled)

    def test_freeze_disabled_without_pdf(self):
        self.assertFalse(self.readiness(preview_bytes=None).enabled)

    def test_freeze_disabled_for_pdf_from_older_payload(self):
        self.assertFalse(self.readiness(preview_payload_hash="0" * 64).enabled)

    def test_freeze_disabled_without_all_approvals(self):
        values = approved(); values["evidence"] = False
        self.assertFalse(self.readiness(approvals=values).enabled)

    def test_freeze_disabled_without_exact_confirmation(self):
        self.assertFalse(self.readiness(confirmation="freeze").enabled)

    def test_existing_snapshot_blocks_duplicate_initial_freeze(self):
        self.assertFalse(self.readiness(existing_snapshot={"id": "existing"}).enabled)

    def test_revision_one_metadata_matches_payload(self):
        result = revision_one_metadata(self.payload, frozen_by="Operator", pdf_filename="audit.pdf")
        self.assertEqual(result.snapshot_revision, 1)
        self.assertIsNone(result.supersedes_snapshot_id)
        self.assertEqual(result.ai_run_id, self.payload["audit"]["baseline_run_id"])
        self.assertEqual(result.frozen_by, "Operator")

    def test_payload_change_invalidates_preview_and_approvals(self):
        state = {"canonical_hash": "old", "pdf_bytes": PDF, "pdf_sha256": "old",
                 "approvals": approved(), "confirmation": "FREEZE"}
        self.assertTrue(sync_payload_session(
            state, payload=self.payload, canonical_hash=self.payload_hash,
            representation_version="renderer-v2",
        ))
        self.assertNotIn("pdf_bytes", state)
        self.assertFalse(any(state["approvals"].values()))

    def test_renderer_change_invalidates_preview_and_approvals(self):
        state = {"canonical_hash": self.payload_hash, "representation_version": "renderer-v1",
                 "pdf_bytes": PDF, "pdf_sha256": sha256_bytes(PDF), "approvals": approved()}
        self.assertTrue(sync_payload_session(
            state, payload=self.payload, canonical_hash=self.payload_hash,
            representation_version="renderer-v2",
        ))
        self.assertNotIn("pdf_bytes", state)
        self.assertFalse(any(state["approvals"].values()))

    def test_exact_preview_bytes_are_passed_and_stored_pdf_is_returned(self):
        state = {"approvals": approved(), "confirmation": "FREEZE"}
        bind_pdf_preview(state, pdf_bytes=PDF, canonical_hash=self.payload_hash, filename="audit.pdf",
                         representation_version="renderer-v2")
        state["approvals"] = approved()
        captured = {}
        stored = {"id": "snapshot-1", "pdf_bytes": PDF, "pdf_sha256": sha256_bytes(PDF)}

        def create(**kwargs):
            captured.update(kwargs)
            return {"id": "snapshot-1"}

        result = freeze_initial_snapshot(
            state=state, payload=self.payload, canonical_hash=self.payload_hash,
            frozen_by="Operator", existing_snapshots=[], create=create,
            load=lambda snapshot_id: stored,
        )
        self.assertIs(captured["pdf_bytes"], PDF)
        self.assertEqual(stored_pdf_bytes(result), PDF)
        self.assertEqual(captured["expected_payload_sha256"], self.payload_hash)
        self.assertEqual(captured["metadata"].snapshot_revision, 1)

    def test_repository_error_leaves_state_unfrozen(self):
        state = {"approvals": approved(), "confirmation": "FREEZE"}
        bind_pdf_preview(state, pdf_bytes=PDF, canonical_hash=self.payload_hash, filename="audit.pdf",
                         representation_version="renderer-v2")
        state["approvals"] = approved()
        with self.assertRaisesRegex(RuntimeError, "database unavailable"):
            freeze_initial_snapshot(
                state=state, payload=self.payload, canonical_hash=self.payload_hash,
                frozen_by="Operator", existing_snapshots=[],
                create=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("database unavailable")),
                load=lambda snapshot_id: None,
            )
        self.assertNotIn("stored_snapshot", state)

    def test_success_records_expected_payload_and_pdf_hashes(self):
        state = {"approvals": approved(), "confirmation": "FREEZE"}
        details = bind_pdf_preview(state, pdf_bytes=PDF, canonical_hash=self.payload_hash, filename="audit.pdf",
                                   representation_version="renderer-v2")
        state["approvals"] = approved()
        stored = {"id": "snapshot-1", "pdf_bytes": PDF,
                  "report_payload_sha256": self.payload_hash,
                  "pdf_sha256": details["pdf_sha256"]}
        result = freeze_initial_snapshot(
            state=state, payload=self.payload, canonical_hash=self.payload_hash,
            frozen_by="Operator", existing_snapshots=[], create=lambda **kwargs: {"id": "snapshot-1"},
            load=lambda snapshot_id: stored,
        )
        self.assertEqual(result["report_payload_sha256"], self.payload_hash)
        self.assertEqual(result["pdf_sha256"], sha256_bytes(PDF))

    def test_one_action_binds_payload_and_exact_reviewable_pdf(self):
        definition = PocAuditDefinition(
            key="fixture", baseline_run_id=self.payload["audit"]["baseline_run_id"],
            target_google_place_id=self.payload["audit"]["target_google_place_id"],
            client_name=self.payload["audit"]["target_business_name"],
            pdf_filename="fixture.pdf", assembler=lambda: self.payload,
        )
        report = ReviewablePocAudit(
            definition=definition, payload=self.payload,
            payload_sha256=self.payload_hash, pdf_bytes=PDF,
            pdf_sha256=sha256_bytes(PDF), renderer_version="renderer-v3",
        )
        state = {"approvals": approved(), "confirmation": "FREEZE"}
        details = bind_reviewable_report(state, report)
        self.assertIs(state["pdf_bytes"], PDF)
        self.assertEqual(state["canonical_hash"], self.payload_hash)
        self.assertEqual(details["pdf_sha256"], sha256_bytes(PDF))
        self.assertFalse(state["approvals"]["client_report"])


if __name__ == "__main__":
    unittest.main()
