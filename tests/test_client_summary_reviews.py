from copy import deepcopy
from io import BytesIO

import pytest
from pypdf import PdfReader

from src.client_summary.adapter import build_client_summary_report, render_client_summary_pdf
from src.client_summary.model import ReportValidationError, validate_report
from src.client_summary.reviews import build_review_summary
from src.owner_services_report import build_owner_report, provider_name
from src.owner_services_synthetic import synthetic_owner_services_payload


def test_every_business_provider_count_is_derived_from_unique_saved_answers():
    payload = synthetic_owner_services_payload()
    # Duplicate recommendation slots must not inflate either totals or provider cells.
    payload['recommendation_market']['slot_evidence'] *= 2
    report = build_owner_report(payload)
    summary = build_client_summary_report(payload)
    for business in summary['businesses']:
        for provider in summary['providers']:
            expected = sum(business['id'] in report['answer_businesses'].get(r['response_id'], [])
                           for r in report['responses'] if provider_name(r['provider']).casefold() == provider['id'])
            assert business['provider_appearances'][provider['id']] == expected
        assert sum(business['provider_appearances'].values()) == business['appearances']
    broken = deepcopy(summary)
    broken['businesses'][0]['provider_appearances'][summary['providers'][0]['id']] += 1
    with pytest.raises(ReportValidationError, match='sum to its total'):
        validate_report(broken)


def test_review_mentions_are_deduplicated_and_do_not_imply_positive_feedback():
    report = build_owner_report(synthetic_owner_services_payload())
    target = report['audit']['target_google_place_id']
    record = {'review_id': 'one', 'review_text': 'Bad carpet cleaning. Carpet still dirty.',
              'review_rating': 1, 'review_datetime_utc': '2026-01-01'}
    report['review_sets'] = [{'google_place_id': target, 'business_name': report['name'],
                              'records': [record, record, {'review_id': 'empty', 'review_text': ''}]}]
    review = build_review_summary(report, 'cleaning_services')
    sample = review['businesses'][0]
    assert sample['sample_size'] == sample['low_ratings'] == sample['themes']['Carpet cleaning'] == 1
    assert sample['rating'] == 1
    assert next(t for t in review['themes'] if t['label'] == 'Carpet cleaning')['answers'] == 0


def test_missing_reviews_are_unavailable_and_no_review_sets_keep_eight_pages():
    payload = synthetic_owner_services_payload()
    summary = build_client_summary_report(payload)
    text = '\n'.join(p.extract_text() for p in PdfReader(BytesIO(render_client_summary_pdf(summary))).pages)
    assert 'keyword matching' in text and 'does not establish whether an AI tool read these reviews' in text
    # Build the no-review projection without source excerpts referring to removed records.
    summary['review_analysis'] = None
    assert len(PdfReader(BytesIO(render_client_summary_pdf(summary))).pages) == 8


def test_review_visibility_link_cannot_disagree_with_measured_questions():
    summary = build_client_summary_report(synthetic_owner_services_payload())
    summary['review_analysis']['themes'][0]['appearances'] += 1
    with pytest.raises(ReportValidationError, match='disagrees with measured questions'):
        validate_report(summary)
