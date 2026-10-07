"""Exercise archive/review forms with mocked stores only; never write production data."""
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

from src.proposition_catalog import starter_catalogue
from src.public_evidence_archive import build_capture
from src.public_evidence_archive_repository import ARCHIVE_TABLES
from src.review_ingestion import SOURCE

PAGE = str(Path(__file__).resolve().parents[1] / 'app/pages/12_Evidence_Review.py')


def run_page(*, ready=True, decided=False):
    catalogue, aliases = starter_catalogue()
    business = {"google_place_id": "place-1", "business_name": "Synthetic Salon"}
    bundle = {"business": business, "listing": None, "audit": None, "pages": [], "platform_links": [], "checks": {},
              "reviews": [{"id": "row-1", "google_place_id": "place-1", "source": SOURCE, "review_id": "review-1",
                           "review_text": "I love my balayage.", "imported_at": datetime(2025, 8, 5, tzinfo=timezone.utc)}]}
    cap = {"id": "capture-1", "archived_at": datetime(2026, 9, 1, tzinfo=timezone.utc), "archived_by": "Operator",
           **build_capture(bundle, catalogue, aliases)}
    stack = ExitStack()
    stack.enter_context(patch('src.public_evidence_archive_repository.archive_status', return_value={t: ready for t in ARCHIVE_TABLES}))
    stack.enter_context(patch('src.evidence_foundations_repository.list_foundation_businesses', return_value=[business]))
    stack.enter_context(patch('src.evidence_foundations_repository.load_catalogue', return_value=(catalogue, aliases, 'test catalogue')))
    stack.enter_context(patch('src.public_evidence_repository.load_public_evidence_bundle', return_value=bundle))
    stack.enter_context(patch('src.public_evidence_archive_repository.list_captures', return_value=[cap]))
    stack.enter_context(patch('src.public_evidence_archive_repository.load_capture', return_value=cap))
    evidence_id = next(o["evidence_id"] for o in cap["payload"]["matrix"]["observations"] if o["kind"] == "proposition_candidate")
    decisions = [{"capture_id": "capture-1", "evidence_id": evidence_id, "revision": 1, "decision": "EXPLICIT_SUPPORT", "origin": "customer_report",
                  "reviewer": "Operator", "identity_confirmed": True, "note": "Checked the preserved sentence"}] if decided else []
    stack.enter_context(patch('src.public_evidence_archive_repository.list_decisions', return_value=decisions))
    stack.enter_context(patch('src.public_evidence_archive_repository.list_collection_attempts', return_value=[]))
    stack.enter_context(patch('src.public_evidence_archive_repository.save_collection_attempt', return_value='attempt-1'))
    save_cap = stack.enter_context(patch('src.public_evidence_archive_repository.save_capture', return_value='capture-1'))
    save_review = stack.enter_context(patch('src.public_evidence_archive_repository.save_decision', return_value='decision-1'))
    at = AppTest.from_file(PAGE).run()
    return at, stack, save_cap, save_review


def test_missing_migration_exposes_no_write_controls():
    at, stack, save_cap, save_review = run_page(ready=False)
    with stack:
        assert not at.exception and not at.error
        assert any('migration is not applied' in i.value for i in at.info)
        assert not at.button and not at.text_input
        assert not save_cap.called and not save_review.called


def test_loading_ready_review_page_does_not_write_or_auto_approve_candidates():
    at, stack, save_cap, save_review = run_page()
    with stack:
        assert not at.exception and not at.error
        summary = next(d.value for d in at.dataframe if 'reviewed_source_breadth' in d.value.columns)
        assert summary['reviewed_source_breadth'].isna().all()
        assert next(s for s in at.selectbox if s.label == 'Decision').value == 'UNCERTAIN'
        assert next(s for s in at.selectbox if s.label == 'Evidence origin').value == 'unknown'
        assert not save_cap.called and not save_review.called


def test_explicit_archive_form_uses_only_saved_bundle_and_mocked_writer():
    at, stack, save_cap, save_review = run_page()
    with stack:
        next(t for t in at.text_input if t.label == 'Archiving operator').set_value('Operator')
        next(b for b in at.button if b.label == 'Archive current saved evidence').click()
        at.run()
        assert not at.exception and not at.error
        assert save_cap.call_count == 1 and not save_review.called
        assert save_cap.call_args.kwargs['archived_by'] == 'Operator'


def test_explicit_review_form_preserves_source_origin_and_identity_confirmation():
    at, stack, save_cap, save_review = run_page()
    with stack:
        next(s for s in at.selectbox if s.label == 'Decision').select('EXPLICIT_SUPPORT')
        next(s for s in at.selectbox if s.label == 'Evidence origin').select('customer_report')
        next(c for c in at.checkbox if c.label == 'I confirmed this evidence refers to this business').check()
        next(t for t in at.text_input if t.label == 'Reviewer').set_value('Operator')
        next(t for t in at.text_area if t.label == 'Explanation, including source context and origin').set_value('I checked the preserved review sentence and business identity')
        next(b for b in at.button if b.label == 'Save evidence decision').click()
        at.run()
        assert not at.exception and not at.error
        assert save_review.call_count == 1 and not save_cap.called
        assert save_review.call_args.kwargs['origin'] == 'customer_report'
        assert save_review.call_args.kwargs['identity_confirmed'] is True


@pytest.mark.parametrize('outcome,size,expected', [('CHECKED_EMPTY',0,0),('FAILED',0,None),('COLLECTED',63,63)])
def test_manual_collection_outcome_preserves_zero_sample_and_unknown(outcome,size,expected):
    at, stack, save_cap, save_review = run_page()
    with stack, patch('src.public_evidence_archive_repository.save_collection_attempt', return_value='attempt-1') as writer:
        next(t for t in at.text_input if t.label == 'Checked source URL').set_value('https://yelp.example/salon')
        next(s for s in at.selectbox if s.label == 'Collection outcome').select(outcome)
        next(t for t in at.text_input if t.label == 'What was checked').set_value('Linked platform profile review texts')
        next(t for t in at.text_area if t.label == 'Collection outcome explanation').set_value('Recorded the actual checked result')
        at.number_input[0].set_value(size)
        next(b for b in at.button if b.label == 'Save collection outcome').click()
        at.run()
        assert not at.exception and not at.error
        assert writer.call_count == 1 and not save_cap.called and not save_review.called
        assert writer.call_args.kwargs['sample_size'] == expected
        assert writer.call_args.kwargs['status'] == outcome


def test_review_queue_shows_progress_and_hides_excerpts_that_already_have_a_decision():
    at, stack, save_cap, save_review = run_page(decided=True)
    with stack:
        assert not at.exception and not at.error
        assert any('Every excerpt in this capture has a decision' in s.value for s in at.success)
        assert not any(s.label == 'Excerpt to review' for s in at.selectbox), "nothing is left in the queue"
        next(c for c in at.checkbox if c.label == 'Show only excerpts without a decision').uncheck()
        at.run()
        assert not at.exception and any(s.label == 'Excerpt to review' for s in at.selectbox)
        assert any('Current decision: EXPLICIT_SUPPORT (customer_report), by Operator' in c.value for c in at.caption)
        assert not save_cap.called and not save_review.called


def test_reviewer_name_is_remembered_after_a_saved_decision():
    at, stack, save_cap, save_review = run_page()
    with stack:
        next(c for c in at.checkbox if c.label == 'I confirmed this evidence refers to this business').check()
        next(t for t in at.text_input if t.label == 'Reviewer').set_value('Rob')
        next(t for t in at.text_area if t.label == 'Explanation, including source context and origin').set_value('Checked the preserved review sentence')
        next(b for b in at.button if b.label == 'Save evidence decision').click()
        at.run()
        assert save_review.call_count == 1 and not at.exception
        assert next(t for t in at.text_input if t.label == 'Reviewer').value == 'Rob'
