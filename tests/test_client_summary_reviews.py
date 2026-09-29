from copy import deepcopy
from io import BytesIO

import pytest
from pypdf import PdfReader

from src.client_summary.adapter import build_client_summary_report, render_client_summary_pdf
from src.client_summary.model import ReportValidationError, validate_report
from src.client_summary.reviews import build_review_summary
from src.owner_services_report import build_owner_report, provider_name
from src.owner_services_synthetic import synthetic_owner_services_payload
from src.review_ingestion import SOURCE, SOURCE_TRIPADVISOR, SOURCE_YELP


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


def test_missing_reviews_are_unavailable_and_no_review_sets_keep_nine_pages():
    payload = synthetic_owner_services_payload()
    summary = build_client_summary_report(payload)
    text = '\n'.join(p.extract_text() for p in PdfReader(BytesIO(render_client_summary_pdf(summary))).pages)
    assert 'keyword matching' in text and 'does not establish whether an AI tool read these reviews' in text
    # Build the no-review projection without source excerpts referring to removed records.
    summary['review_analysis'] = None
    # 9, not 8: page 9 (mentioned vs. recommended) is unconditional, unlike the review pages.
    assert len(PdfReader(BytesIO(render_client_summary_pdf(summary))).pages) == 9


def test_review_visibility_link_cannot_disagree_with_measured_questions():
    summary = build_client_summary_report(synthetic_owner_services_payload())
    summary['review_analysis']['themes'][0]['appearances'] += 1
    with pytest.raises(ReportValidationError, match='disagrees with measured questions'):
        validate_report(summary)


def _platform_record(review_id, source, rating=5):
    return {'review_id': review_id, 'review_text': 'Great service, would recommend.',
            'review_rating': rating, 'review_datetime_utc': '2026-01-01', 'source': source}


def test_reviews_from_more_than_one_platform_show_a_breakdown_and_rationale():
    report = build_owner_report(synthetic_owner_services_payload())
    target = report['audit']['target_google_place_id']
    report['review_sets'] = [{
        'google_place_id': target, 'business_name': report['name'],
        'records': [
            _platform_record('g1', SOURCE), _platform_record('g2', SOURCE),
            _platform_record('y1', SOURCE_YELP),
            _platform_record('t1', SOURCE_TRIPADVISOR),
        ],
    }]
    review = build_review_summary(report, 'coworking')
    sample = review['businesses'][0]
    assert sample['source_counts'] == {SOURCE: 2, SOURCE_YELP: 1, SOURCE_TRIPADVISOR: 1}
    assert review['target_platforms'] == [SOURCE, SOURCE_YELP, SOURCE_TRIPADVISOR]

    payload = synthetic_owner_services_payload()
    summary = build_client_summary_report(payload)
    summary['review_analysis'] = review
    validate_report(summary)  # extra keys must not break the existing schema check
    text = '\n'.join(p.extract_text() for p in PdfReader(BytesIO(render_client_summary_pdf(summary))).pages)
    assert 'WHERE THIS EVIDENCE COMES FROM' in text
    assert 'a key input for how Gemini grounds' in text  # Google's rationale clause
    assert 'also informs other AI assistants, including ChatGPT' in text  # Yelp's
    assert 'hospitality and leisure context' in text  # TripAdvisor's
    assert 'Google 2' in text and 'Yelp 1' in text and 'TripAdvisor 1' in text


def test_a_single_platform_still_shows_the_rationale_but_no_breakdown_parenthetical():
    report = build_owner_report(synthetic_owner_services_payload())
    target = report['audit']['target_google_place_id']
    report['review_sets'] = [{
        'google_place_id': target, 'business_name': report['name'],
        'records': [_platform_record('g1', SOURCE)],
    }]
    review = build_review_summary(report, 'coworking')
    assert review['businesses'][0]['source_counts'] == {SOURCE: 1}
    assert review['target_platforms'] == [SOURCE]

    payload = synthetic_owner_services_payload()
    summary = build_client_summary_report(payload)
    summary['review_analysis'] = review
    text = '\n'.join(p.extract_text() for p in PdfReader(BytesIO(render_client_summary_pdf(summary))).pages)
    assert 'WHERE THIS EVIDENCE COMES FROM' in text
    assert 'Google 1' not in text  # plain count, no parenthetical breakdown for one source


def test_a_review_row_with_no_source_field_defaults_to_google_not_dropped():
    # Every row in business_reviews has always had a source value in practice, but this is the
    # graceful-degradation path if one were ever missing rather than raising or miscounting.
    report = build_owner_report(synthetic_owner_services_payload())
    target = report['audit']['target_google_place_id']
    record = {'review_id': 'g1', 'review_text': 'Great service.', 'review_rating': 5,
              'review_datetime_utc': '2026-01-01'}
    report['review_sets'] = [{'google_place_id': target, 'business_name': report['name'], 'records': [record]}]
    review = build_review_summary(report, 'coworking')
    assert review['businesses'][0]['source_counts'] == {SOURCE: 1}
