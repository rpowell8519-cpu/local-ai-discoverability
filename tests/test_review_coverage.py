"""Collection completion and profile identity must never be inferred from missing text."""
import pandas as pd
import pytest

from src.review_coverage import build_review_coverage, empty_text_check
from src.review_ingestion import SOURCE_YELP
from src.poc_audit_generic import assemble_generic_report_payload

URL = "https://www.yelp.com/biz/example-brighton"
LINKS = pd.DataFrame([{"google_place_id": "target", "platform": "yelp", "external_url": URL}])


def coverage(reviews=None, checks=None, links=LINKS):
    rows = build_review_coverage(business_names={"target": "Example"},
                                 reviews=reviews if reviews is not None else pd.DataFrame(),
                                 platform_links=links, checks=checks)
    return next(row for row in rows if row["source"] == SOURCE_YELP)


def test_linked_profile_with_no_collected_text_is_not_checked_and_count_unknown():
    row = coverage()
    assert row["profile_status"] == "linked" and row["source_url"] == URL
    assert row["status"] == "not_checked" and row["found_count"] is None


def test_completed_empty_check_preserves_zero_date_url_and_note():
    check = empty_text_check(source_url=URL, checked_at="2025-01-02", note="Read profile; no accessible review text.")
    row = coverage(checks={"target": {SOURCE_YELP: check}})
    assert row["status"] == "checked" and row["found_count"] == 0
    assert row["checked_at"] == "2025-01-02" and row["note"] == check["note"]


def test_saved_text_is_a_deduplicated_sample_not_a_profile_total():
    reviews = pd.DataFrame([
        {"google_place_id": "target", "source": SOURCE_YELP, "review_id": "1", "review_text": "Helpful staff"},
        {"google_place_id": "target", "source": SOURCE_YELP, "review_id": "1", "review_text": "Helpful staff"},
        {"google_place_id": "target", "source": SOURCE_YELP, "review_id": "2", "review_text": " "},
    ])
    row = coverage(reviews=reviews)
    assert row["status"] == "checked" and row["found_count"] == row["sampled_review_count"] == 1
    assert "not the platform's published total" in row["note"]
    assert "published_review_count" not in row


def test_incomplete_historical_check_does_not_turn_unknown_into_zero():
    row = coverage(checks={"target": {SOURCE_YELP: {"status": "checked", "found_count": 0}}})
    assert row["status"] == "not_checked" and row["found_count"] is None


def test_replacing_link_does_not_reuse_an_empty_check_of_another_profile():
    check = empty_text_check(source_url="https://www.yelp.com/biz/old-profile", checked_at="2025-01-02", note="No text accessible")
    row = coverage(checks={"target": {SOURCE_YELP: check}})
    assert row["source_url"] == URL and row["status"] == "not_checked"


def test_empty_check_requires_a_public_source_and_operator_explanation():
    with pytest.raises(ValueError, match="what was checked"):
        empty_text_check(source_url=URL, checked_at="2025-01-02", note=" ")
    with pytest.raises(ValueError, match="public profile"):
        empty_text_check(source_url="javascript:alert(1)", checked_at="2025-01-02", note="Checked")


def test_new_generic_report_rejects_old_presence_action_before_reading_database():
    with pytest.raises(ValueError, match="missing collected text"):
        assemble_generic_report_payload(audit_revision={
            "reviewer_decisions_complete": True,
            "reviewer_decisions": {"approved_recommendations": [{"id": "reviews:platform-yelp"}]},
        })
