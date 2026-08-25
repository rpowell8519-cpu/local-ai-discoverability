from __future__ import annotations

import copy
import unittest

from src.poc_audit_payload import (
    PayloadValidationError,
    build_baseline_validation,
    build_poc_audit_payload,
    canonical_json_bytes,
    freeze_ai_response,
    freeze_review_set,
    payload_sha256,
    sha256_json,
    sha256_text,
    validate_poc_audit_payload,
)


def response(index: int = 1) -> dict:
    return freeze_ai_response(
        {
            "id": f"response-{index}",
            "query_id": f"query-{index}",
            "provider": "OpenAI",
            "model": "model-1",
            "base_prompt_order": index,
            "prompt_category": "General",
            "prompt_text": "Recommend a business.",
            "repeat_index": 1,
            "raw_response": "1. Example Business — Evidence.",
            "status": "completed",
            "response_complete": True,
            "finish_reason": "completed",
            "error_message": None,
            "created_at": "2026-08-25T00:00:00+00:00",
        },
        parser_reconciliation={
            "target_correct": True,
            "parsed_recommendations": ["Example Business"],
        },
    )


def review_set() -> dict:
    return freeze_review_set(
        google_place_id="place-1",
        business_name="Example Business",
        records=[
            {
                "id": "row-1",
                "google_place_id": "place-1",
                "business_name": "Example Business",
                "review_id": "review-1",
                "review_text": "Excellent service.",
                "review_rating": 5,
                "owner_answer": "Thank you, Personal name!",
                "owner_answer_timestamp": 12345,
                "author_title": "Personal name",
                "author_id": "profile-123",
                "author_reviews_count": 99,
                "raw_data": {
                    "author_image": "https://example.test/avatar.jpg"
                },
            },
            {
                "id": "row-2",
                "google_place_id": "place-1",
                "business_name": "Example Business",
                "review_id": "review-2",
                "review_text": "Very helpful.",
                "review_rating": 4,
            },
        ],
    )


def payload() -> dict:
    frozen_response = response()
    baseline = build_baseline_validation(
        [frozen_response],
        expected_responses=1,
        status="verified_zero",
        verification_method_version="test-v1",
    )

    return build_poc_audit_payload(
        audit={
            "baseline_run_id": "run-1",
            "target_google_place_id": "canonical-place-1",
            "client_name": "Example",
        },
        revision={
            "snapshot_revision": 1,
            "supersedes_snapshot_id": None,
            "revision_reason": "Original audit",
        },
        methodology={},
        baseline_validation=baseline,
        source_traceability={},
        recommendation_market={
            "slot_evidence": [],
        },
        website_evidence={
            "audits": [],
        },
        review_evidence={
            "review_sets": [review_set()],
        },
        diagnostic={},
        report={},
    )


class PocAuditPayloadTests(unittest.TestCase):
    def test_canonical_json_is_stable_across_key_order(self):
        self.assertEqual(
            canonical_json_bytes({"b": 2, "a": 1}),
            canonical_json_bytes({"a": 1, "b": 2}),
        )

    def test_full_raw_response_is_frozen_and_hashed(self):
        item = response()
        self.assertEqual(
            item["raw_response"],
            "1. Example Business — Evidence.",
        )
        self.assertEqual(
            item["raw_response_sha256"],
            sha256_text(item["raw_response"]),
        )

    def test_response_audit_hash_covers_full_text(self):
        first = response()
        baseline = build_baseline_validation(
            [first],
            expected_responses=1,
            status="verified_zero",
            verification_method_version="test-v1",
        )
        changed = copy.deepcopy(baseline)
        changed["responses"][0]["raw_response"] += " Changed"
        self.assertNotEqual(
            baseline["response_audit_sha256"],
            sha256_json(changed["responses"]),
        )

    def test_noncredible_indirect_finding_is_preserved_not_counted(self):
        item = response()
        item["indirect_matches"] = [
            {
                "term": "East Street",
                "credible": False,
                "assessment": "Refers to another named business",
            }
        ]
        baseline = build_baseline_validation(
            [item],
            expected_responses=1,
            status="verified_zero",
            verification_method_version="test-v1",
        )
        self.assertEqual(
            baseline["possible_indirect_target_recommendations"],
            0,
        )
        self.assertEqual(
            len(baseline["responses"][0]["indirect_matches"]),
            1,
        )

    def test_review_order_and_full_text_are_frozen(self):
        frozen = review_set()
        self.assertEqual(
            frozen["ordered_review_ids"],
            ["review-1", "review-2"],
        )
        self.assertEqual(
            frozen["records"][0]["review_text"],
            "Excellent service.",
        )

    def test_reviewer_personal_and_raw_fields_are_discarded(self):
        record = review_set()["records"][0]
        self.assertNotIn("author_title", record)
        self.assertNotIn("author_id", record)
        self.assertNotIn("author_reviews_count", record)
        self.assertNotIn("raw_data", record)
        self.assertNotIn("author_image", record)
        self.assertNotIn("owner_answer", record)
        self.assertNotIn("owner_answer_timestamp", record)
        self.assertTrue(record["owner_response_present"])

    def test_review_order_changes_hash(self):
        frozen = review_set()
        self.assertNotEqual(
            frozen["ordered_review_ids_sha256"],
            sha256_json(list(reversed(frozen["ordered_review_ids"]))),
        )

    def test_revision_one_cannot_supersede(self):
        candidate = payload()
        candidate["revision"]["supersedes_snapshot_id"] = "old"
        with self.assertRaises(PayloadValidationError):
            validate_poc_audit_payload(candidate)

    def test_later_revision_requires_lineage_and_reason(self):
        candidate = payload()
        candidate["revision"] = {
            "snapshot_revision": 2,
            "supersedes_snapshot_id": None,
            "revision_reason": "",
        }
        with self.assertRaises(PayloadValidationError) as raised:
            validate_poc_audit_payload(candidate)
        self.assertGreaterEqual(len(raised.exception.errors), 2)

    def test_valid_later_revision_passes(self):
        candidate = payload()
        candidate["revision"] = {
            "snapshot_revision": 2,
            "supersedes_snapshot_id": "snapshot-1",
            "revision_reason": "Corrected client address",
        }
        validate_poc_audit_payload(candidate)

    def test_synthetic_target_is_rejected(self):
        candidate = payload()
        candidate["audit"][
            "target_google_place_id"
        ] = "discovery:run-1"
        with self.assertRaises(PayloadValidationError):
            validate_poc_audit_payload(candidate)

    def test_tampered_raw_response_is_rejected(self):
        candidate = payload()
        candidate["baseline_validation"]["responses"][0][
            "raw_response"
        ] += " tampered"
        candidate["baseline_validation"][
            "response_audit_sha256"
        ] = sha256_json(
            candidate["baseline_validation"]["responses"]
        )
        with self.assertRaises(PayloadValidationError):
            validate_poc_audit_payload(candidate)

    def test_tampered_review_text_is_rejected(self):
        candidate = payload()
        review = candidate["review_evidence"]["review_sets"][0]
        review["records"][0]["review_text"] = "Changed"
        with self.assertRaises(PayloadValidationError):
            validate_poc_audit_payload(candidate)

    def test_undocumented_review_exception_is_rejected(self):
        candidate = payload()
        review = candidate["review_evidence"]["review_sets"][0]
        review["status"] = "exception"
        with self.assertRaises(PayloadValidationError):
            validate_poc_audit_payload(candidate)

    def test_payload_hash_reproduces(self):
        candidate = payload()
        self.assertEqual(
            payload_sha256(candidate),
            sha256_json(candidate),
        )


if __name__ == "__main__":
    unittest.main()
