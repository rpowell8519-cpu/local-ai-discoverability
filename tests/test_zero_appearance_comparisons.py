import copy
import pytest
from src.poc_audit_assembler import _market_row


def test_zero_comparison_does_not_expand_or_change_observed_market():
    market = [{'google_place_id': 'leader', 'recommendations': 9, 'share_of_recommendation': 1.0}]
    before = copy.deepcopy(market)
    assert _market_row(market, 'not-recommended', allow_zero=True) == {
        'google_place_id': 'not-recommended', 'recommendations': 0, 'share_of_recommendation': 0.0}
    assert market == before
    assert _market_row(market, 'leader', allow_zero=True) == market[0]


def test_missing_target_and_duplicate_id_still_fail():
    with pytest.raises(ValueError, match='0 rows'):
        _market_row([], 'target')
    with pytest.raises(ValueError, match='2 rows'):
        _market_row([{'google_place_id': 'duplicate'}]*2, 'duplicate', allow_zero=True)


def test_report_builds_cohort_and_matrix_with_absent_comparisons(monkeypatch):
    from src import poc_audit_assembler as assembler
    from src.poc_audit_udr_owner_services import CONFIG
    config = copy.deepcopy(CONFIG)
    target = config['target_google_place_id']
    market = [{'google_place_id': target, 'business_name': config['target_business_name'],
               'recommendations': 0, 'share_of_recommendation': 0.0}]
    config['analyst_decisions']['matrix_dimensions'] = [{'label': 'Recommendations in this test', 'values': {}}]
    monkeypatch.setattr(assembler, '_question_performance', lambda **kwargs: [])
    report = assembler._build_report(config=config,
        run={'providers': ['OpenAI'], 'models': {'OpenAI':'test'}, 'prompt_count':1, 'repeat_count':1},
        baseline={'responses':[{'response_complete':True, 'status':'completed', 'provider':'OpenAI',
                              'base_prompt_order':1, 'prompt_category':'Test', 'parser_reconciliation':{}}]},
        slots=[], market=market, websites=[], review_sets=[])
    assert all(row['recommendations'] == 0 for row in report['diagnostic_cohort'])
    assert set(report['evidence_matrix']['dimensions'][0]['values'].values()) == {'0'}
    assert report['recommendation_market']['business_count'] == 1
