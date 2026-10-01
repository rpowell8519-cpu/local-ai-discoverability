"""Durable copies cannot manufacture freshness, identity, support or independent evidence."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch
from types import MappingProxyType
from uuid import UUID

import pytest

from src.proposition_catalog import starter_catalogue
from src.public_evidence_archive import (
    build_capture, canonical_json, collection_attempt, json_value, payload_hash,
    summarize_reviewed_evidence, validate_decision, verify_capture,
)
from src.public_evidence_archive_repository import ARCHIVE_TABLES, save_capture, save_decision, save_collection_attempt
from src.review_ingestion import SOURCE, SOURCE_YELP


def source_bundle():
    return {"business": {"google_place_id": "place-cisco", "business_name": "Cisco's Karma"},
        "listing": {"id": "listing-1", "google_place_id": "place-cisco", "created_at": datetime(2025, 8, 3, tzinfo=timezone.utc),
                    "raw_data": {"phone": "01273 123456", "reviews": 214}},
        "audit": {"id": "audit-1", "google_place_id": "place-cisco", "audit_status": "completed"},
        "pages": [{"id": "page-1", "audit_run_id": "audit-1", "http_status": 200,
                   "text_excerpt": "We offer balayage.", "crawled_at": datetime(2025, 8, 5, tzinfo=timezone.utc)}],
        "reviews": [{"id": "review-row-1", "google_place_id": "place-cisco", "review_id": "review-1", "source": SOURCE,
                     "review_text": "I love my balayage.", "imported_at": datetime(2025, 8, 7, tzinfo=timezone.utc),
                     "review_datetime_utc": datetime(2025, 8, 1, tzinfo=timezone.utc), "raw_data": {"original": "provider payload"}}],
        "platform_links": [], "checks": {}}


def capture(bundle=None):
    catalogue, aliases = starter_catalogue()
    return {"id": "capture-1", **build_capture(bundle or source_bundle(), catalogue, aliases)}


def candidates(cap):
    return [o for o in cap["payload"]["matrix"]["observations"] if o["kind"] == "proposition_candidate"]


def decision(cap, observation, *, choice="EXPLICIT_SUPPORT", origin="owner_claim", revision=1, identity=True):
    return {"capture_id": cap["id"], "revision": revision,
            **validate_decision(cap, evidence_id=observation["evidence_id"], decision=choice, origin=origin,
                                reviewer="Operator", note="Checked the source sentence and business identity", identity_confirmed=identity)}


def test_archiving_copies_raw_sources_and_original_dates_without_refresh():
    bundle = source_bundle()
    cap = capture(bundle)
    assert cap["payload"]["source_bundle"]["reviews"][0]["raw_data"] == {"original": "provider payload"}
    assert cap["payload"]["source_bundle"]["listing"]["raw_data"]["reviews"] == 214
    assert cap["payload"]["source_bundle"]["reviews"][0]["imported_at"].startswith("2025-08-07")
    bundle["reviews"][0]["review_text"] = "Changed after archival"
    assert cap["payload"]["source_bundle"]["reviews"][0]["review_text"] == "I love my balayage."
    assert cap["payload_sha256"] == capture()["payload_sha256"]
    assert "not a fresh" in cap["payload"]["scope"]


def test_archive_remains_valid_if_original_source_changes_but_modified_capture_fails_hash():
    cap = capture()
    assert verify_capture(cap)["google_place_id"] == "place-cisco"
    tampered = deepcopy(cap)
    tampered["payload"]["source_bundle"]["pages"][0]["text_excerpt"] = "Invented expertise"
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_capture(tampered)
    with pytest.raises(ValueError, match="identity mismatch"):
        verify_capture({**cap, "google_place_id": "another-place"})
    with pytest.raises(ValueError, match="Unsupported"):
        verify_capture({**cap, "capture_version": "future-version"})


def test_canonical_bytes_survive_jsonb_number_formatting_without_accepting_boolean_changes():
    bundle = source_bundle()
    bundle['listing']['raw_data']['large_numeric'] = 1e20
    cap = capture(bundle)
    cap['payload']['source_bundle']['listing']['raw_data']['large_numeric'] = 100000000000000000000
    assert verify_capture(cap)
    bundle['listing']['raw_data']['large_numeric'] = 0
    cap = capture(bundle)
    cap['payload']['source_bundle']['listing']['raw_data']['large_numeric'] = False
    with pytest.raises(ValueError, match='hash mismatch'):
        verify_capture(cap)


@pytest.mark.parametrize("change", ["reviews", "listing", "audit", "platform_links", "pages"])
def test_source_identity_and_audit_page_links_are_not_silently_resolved(change):
    bundle = source_bundle()
    if change in {"listing", "audit"}:
        bundle[change]["google_place_id"] = "another-business"
    elif change == "pages":
        bundle["pages"][0]["audit_run_id"] = "another-audit"
    elif change == "platform_links":
        bundle[change] = [{"google_place_id": "another-business", "platform": "yelp"}]
    else:
        bundle[change][0]["google_place_id"] = "another-business"
    with pytest.raises(ValueError):
        capture(bundle)


def test_empty_business_cannot_be_archived_as_primary_evidence():
    bundle = source_bundle()
    bundle.update(listing=None, audit=None, pages=[], reviews=[])
    with pytest.raises(ValueError, match="no saved primary"):
        capture(bundle)


def test_canonical_payload_handles_database_values_without_guessing_unknown_types():
    assert json_value(UUID(int=1)) == "00000000-0000-0000-0000-000000000001"
    assert json_value(Decimal("4.7")) == "4.7"
    assert json_value(float("nan")) is None
    assert json_value(MappingProxyType({"label": "Balayage"})) == {"label": "Balayage"}
    assert canonical_json({"b": 2, "a": "£"}) == canonical_json({"a": "£", "b": 2})
    with pytest.raises(ValueError, match="Unsupported"):
        json_value(object())


def test_support_requires_confirmed_identity_origin_reviewer_and_note():
    cap = capture()
    eid = candidates(cap)[0]["evidence_id"]
    options = dict(evidence_id=eid, decision="EXPLICIT_SUPPORT", origin="owner_claim", reviewer="Operator", note="Proof checked", identity_confirmed=True)
    for change in [{"identity_confirmed": False}, {"origin": "unknown"}, {"reviewer": None}, {"note": " "}, {"decision": "invented"}]:
        with pytest.raises(ValueError):
            validate_decision(cap, **{**options, **change})
    with pytest.raises(ValueError, match="exact capture"):
        validate_decision(cap, **{**options, "evidence_id": "nonexistent"})
    fact = next(o for o in cap["payload"]["matrix"]["observations"] if o["kind"] == "fact")
    with pytest.raises(ValueError, match="proposition excerpt"):
        validate_decision(cap, **{**options, "evidence_id": fact["evidence_id"]})


def test_unknown_and_uncertain_review_do_not_become_zero_breadth():
    cap = capture()
    assert summarize_reviewed_evidence(cap, [])[0]["reviewed_source_breadth"] is None
    uncertain = decision(cap, candidates(cap)[0], choice="UNCERTAIN", origin="unknown", identity=False)
    result = summarize_reviewed_evidence(cap, [uncertain])[0]
    assert result["reviewed_source_breadth"] is None and result["uncertain_excerpts"] == 1
    assert result["coverage"] == "partial_candidate_review"


def test_owner_customer_and_syndicated_evidence_are_separate_and_decisions_append():
    bundle = source_bundle()
    bundle["reviews"].append({**bundle["reviews"][0], "id": "review-row-2", "source": SOURCE_YELP})
    cap = capture(bundle)
    owner, customer, syndicated = candidates(cap)
    decisions = [decision(cap, owner), decision(cap, customer, origin="customer_report"),
                 decision(cap, syndicated, origin="syndicated_claim")]
    result = summarize_reviewed_evidence(cap, decisions)[0]
    assert result["reviewed_source_breadth"] == 2 and result["customer_source_breadth"] == 1
    assert result["third_party_source_breadth"] == 0 and result["coverage"] == "complete_candidate_review"
    withdrawal = decision(cap, customer, choice="UNCERTAIN", origin="unknown", revision=2, identity=False)
    result = summarize_reviewed_evidence(cap, [withdrawal, *decisions])[0]
    assert result["reviewed_source_breadth"] == 1 and result["coverage"] == "partial_candidate_review"
    assert len(decisions) == 3  # prior records untouched; newest revision controls current support
    contradiction = decision(cap, customer, choice="CONTRADICTS", origin="customer_report", revision=3)
    assert summarize_reviewed_evidence(cap, [*decisions, withdrawal, contradiction])[0]["reviewed_contradiction_count"] == 1


def test_decisions_cannot_leak_between_captures_or_have_conflicting_revisions():
    cap = capture()
    d = decision(cap, candidates(cap)[0])
    with pytest.raises(ValueError, match="another capture"):
        summarize_reviewed_evidence(cap, [{**d, "capture_id": "capture-2"}])
    with pytest.raises(ValueError, match="Conflicting"):
        summarize_reviewed_evidence(cap, [d, {**d, "decision": "NO_SUPPORT"}])


def attempt(**changes):
    return collection_attempt(**{**dict(google_place_id="place-cisco", source_class="yelp_reviews", source_url="https://yelp.example/salon",
        status="CHECKED_EMPTY", observed_at="2025-08-05T00:00:00+00:00", sample_size=0,
        scope="Linked profile text reviews", note="No usable text returned", adapter_version="manual-v1"), **changes})


@pytest.mark.parametrize("changes", [
    {"status": "NOT_CHECKED"}, {"status": "FAILED", "sample_size": 0}, {"status": "COLLECTED", "sample_size": 0},
    {"sample_size": False}, {"sample_size": None}, {"observed_at": "2099-01-01T00:00:00Z"},
    {"observed_at": "2025-08-05"}, {"note": ""}, {"source_url": "https://user:pass@example.com/profile"},
])
def test_collection_attempt_outcomes_keep_unknowns_explicit(changes):
    with pytest.raises(ValueError):
        attempt(**changes)


def test_failed_and_checked_empty_are_different_from_sample_totals():
    assert attempt()["sample_size"] == 0
    assert attempt(status="FAILED", sample_size=None)["sample_size"] is None
    assert attempt(status="COLLECTED", sample_size=63)["sample_size"] == 63


def mock_engine():
    engine, connection = MagicMock(), MagicMock()
    engine.begin.return_value.__enter__.return_value = connection
    return engine, connection


def test_repository_capture_and_observations_save_in_one_transaction_and_duplicate_reuses_capture():
    catalogue, aliases = starter_catalogue()
    engine, connection = mock_engine()
    with patch("src.public_evidence_archive_repository.archive_status", return_value={t: True for t in ARCHIVE_TABLES}):
        connection.execute.return_value.mappings.return_value.first.return_value = {"id": "new-capture"}
        assert save_capture(source_bundle(), catalogue, aliases, archived_by="Operator", engine=engine) == "new-capture"
        sql = [str(c.args[0]) for c in connection.execute.call_args_list]
        assert "on conflict" in sql[0] and "cast(:body as text)" in sql[0]
        assert sum("insert into public.public_evidence_observations" in q for q in sql) == 3
        assert engine.begin.call_count == 1
        connection.reset_mock()
        connection.execute.return_value.mappings.return_value.first.return_value = None
        connection.execute.return_value.scalar_one.return_value = "existing-capture"
        assert save_capture(source_bundle(), catalogue, aliases, archived_by="Operator", engine=engine) == "existing-capture"
        assert connection.execute.call_count == 2


def test_pending_migration_prevents_all_archive_writes():
    catalogue, aliases = starter_catalogue()
    engine, connection = mock_engine()
    with patch("src.public_evidence_archive_repository.archive_status", return_value={t: False for t in ARCHIVE_TABLES}):
        with pytest.raises(ValueError, match="migration"):
            save_capture(source_bundle(), catalogue, aliases, archived_by="Operator", engine=engine)
        with pytest.raises(ValueError, match="migration"):
            save_collection_attempt(engine=engine, **attempt())
    assert not engine.begin.called


def test_repository_decisions_lock_and_append_instead_of_updating_old_reviews():
    cap = capture()
    d = decision(cap, candidates(cap)[0])
    engine, connection = mock_engine()
    connection.execute.return_value.scalar_one.side_effect = [2, "new-decision"]
    with patch("src.public_evidence_archive_repository.archive_status", return_value={t: True for t in ARCHIVE_TABLES}), \
         patch("src.public_evidence_archive_repository.load_capture", return_value=cap):
        assert save_decision(cap["id"], engine=engine, **{k: d[k] for k in
            ("evidence_id", "decision", "origin", "reviewer", "note", "identity_confirmed")}) == "new-decision"
    calls = connection.execute.call_args_list
    assert "pg_advisory_xact_lock" in str(calls[0].args[0])
    assert "max(revision)" in str(calls[1].args[0])
    assert "insert into" in str(calls[2].args[0]) and calls[2].args[1]["revision"] == 2
