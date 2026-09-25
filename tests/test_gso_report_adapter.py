from datetime import datetime, timezone

import pytest

from gso_report.metrics import kpis
from src.gso_report_adapter import build_gso_report_from_saved_run


def sample_data():
    run = {
        "id": "run-1", "status": "completed", "providers": '["OpenAI"]',
        "benchmark_mode": "search_grounded", "location_context": "London",
    }
    queries = [{
        "id": "query-1", "base_prompt_order": 1, "repeat_index": 1,
        "prompt_text": "Where should I rent an apartment?", "prompt_category": "Rentals",
        "report_intent": "comparison", "report_importance": None, "report_effort": None,
    }]
    results = [{
        "id": "result-1", "query_id": "query-1", "provider": "OpenAI", "model": "model-x",
        "raw_response": "1. UDR Properties", "target_mentioned": True, "target_recommended": True,
        "target_position": 1,
        "mentioned_known_businesses": [{"google_place_id": "udr", "business_name": "UDR Properties",
                                        "recommended": True, "recommendation_position": 1}],
        "mentioned_competitors": [],
        "report_metadata": {"citation_status": "unavailable", "citations": [], "refused": False},
        "response_complete": True, "status": "completed", "created_at": datetime(2026, 9, 24, tzinfo=timezone.utc),
    }]
    return run, queries, results


def test_adapter_keeps_unknown_citations_unavailable_and_prompt_ratings_optional():
    run, queries, results = sample_data()
    report = build_gso_report_from_saved_run(
        run, queries, results, target_google_place_id="udr", client_name="UDR Properties",
        client_website_url="https://www.udr.com/", category="Apartments", market="London",
    )
    assert report.observations[0].answer == "1. UDR Properties"
    assert report.observations[0].citation_status == "unavailable"
    assert report.observations[0].mentions[0].recommendation_position == 1
    assert report.prompts[0].intent == "comparison"
    assert report.prompts[0].importance is None
    assert kpis(report, report.observations)["Owned-site citation rate %"] is None
    assert "UDR Properties was matched" in report.executive_summary


def test_adapter_rejects_incomplete_planned_scan():
    run, queries, results = sample_data()
    results.clear()
    with pytest.raises(ValueError, match="no saved prompts or answer records"):
        build_gso_report_from_saved_run(
            run, queries, results, target_google_place_id="udr", client_name="UDR Properties"
        )


def test_reported_zero_requires_measured_citation_metadata():
    run, queries, results = sample_data()
    results[0]["report_metadata"] = {"citation_status": "measured", "citations": [], "refused": False}
    report = build_gso_report_from_saved_run(
        run, queries, results, target_google_place_id="udr", client_name="UDR Properties",
        client_website_url="https://udr.com",
    )
    stats = kpis(report, report.observations)
    assert stats["Citation evidence coverage %"] == 100.0
    assert stats["Owned-site citation rate %"] == 0.0

