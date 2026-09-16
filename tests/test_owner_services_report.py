from copy import deepcopy
import io

import pytest
from pypdf import PdfReader

from src.owner_services_report import build_owner_report, comparison_partition, evidence_index_html, tied_rank
from src.owner_services_synthetic import synthetic_owner_services_payload
from src.poc_audit_pdf import render_poc_audit_pdf
from src.poc_audit_payload import build_baseline_validation, validate_poc_audit_payload, sha256_text


@pytest.fixture
def payload():
    return synthetic_owner_services_payload()


def test_totals_reconcile_from_answer_records(payload):
    r = build_owner_report(payload)
    assert (r["appearances"], r["answers"]) == (12, 24)
    assert sum(q["appearances"] for q in r["questions"]) == r["appearances"]
    assert sum(q["answers"] for q in r["questions"]) == r["answers"]
    assert sum(s["appearances"] or 0 for s in r["services"]) == r["appearances"]
    assert sum(s["answers"] for s in r["services"]) == r["answers"]
    assert sum(p["appearances"] for p in r["provider_counts"]) == r["appearances"]
    assert sum(p["answers"] for p in r["provider_counts"]) == r["answers"]
    assert r["raw_entries"] == r["deduplicated_entries"] == 36


def test_multiple_questions_group_and_untested_is_not_zero(payload):
    r = build_owner_report(payload)
    colour, curly, bridal, extensions = r["services"]
    assert (colour["appearances"], colour["answers"]) == (10, 12)
    assert (curly["appearances"], curly["answers"]) == (2, 6)
    assert bridal["appearances"] == 0 and bridal["status"] == "Tested"
    assert extensions["appearances"] is None and extensions["status"] == "Not tested"


@pytest.mark.parametrize("count,counts,expected", [(17, [23, 21, 17, 17, 17, 13], (3, True)), (23, [23, 21, 17], (1, False)), (0, [2, 0, 0], (2, True))])
def test_competition_ranking_handles_ties(count, counts, expected):
    assert tied_rank(count, counts) == expected


def test_aliases_count_once_per_answer_without_changing_evidence(payload):
    slot = next(s for s in payload["recommendation_market"]["slot_evidence"] if s["google_place_id"] == "synthetic-target")
    alias = {**slot, "business_name": "Example Salon Limited", "raw_business_name": "Example Salon Ltd"}
    payload["recommendation_market"]["slot_evidence"].append(alias)
    original = deepcopy(payload)
    r = build_owner_report(payload)
    assert r["appearances"] == 12
    assert r["raw_entries"] == 37 and r["deduplicated_entries"] == 36
    assert payload == original


def test_incomplete_answers_are_excluded_not_zero(payload):
    record = payload["baseline_validation"]["responses"][0]
    record["response_complete"] = False
    record["status"] = "failed"
    record["raw_response"] = ""
    record["raw_response_sha256"] = sha256_text("")
    payload["baseline_validation"] = build_baseline_validation(payload["baseline_validation"]["responses"], expected_responses=24, status="reviewed", verification_method_version="test")
    validate_poc_audit_payload(payload)
    r = build_owner_report(payload)
    assert (r["appearances"], r["answers"], r["excluded"]) == (11, 23, 1)


def test_completed_without_named_recommendations_stays_in_denominator(payload):
    first = payload["baseline_validation"]["responses"][0]
    payload["recommendation_market"]["slot_evidence"] = [s for s in payload["recommendation_market"]["slot_evidence"] if (s["query_id"], s["provider"]) != (first["query_id"], first["provider"])]
    r = build_owner_report(payload)
    assert r["answers"] == 24 and r["no_named_answers"] == 1 and r["appearances"] == 11


@pytest.mark.parametrize("scenario", ["zero", "all", "insufficient"])
def test_summary_does_not_force_a_negative_narrative(payload, scenario):
    if scenario == "zero":
        payload["recommendation_market"]["slot_evidence"] = [s for s in payload["recommendation_market"]["slot_evidence"] if s["google_place_id"] != "synthetic-target"]
        assert "did not appear" in build_owner_report(payload)["headline"]
    elif scenario == "all":
        for s in payload["recommendation_market"]["slot_evidence"]:
            s["google_place_id"] = "synthetic-target"
        assert "every completed answer" in build_owner_report(payload)["headline"]
    else:
        for r in payload["baseline_validation"]["responses"]:
            r["response_complete"] = False
        report = build_owner_report(payload)
        assert "not enough completed evidence" in report["headline"]
        assert report["services"][0]["status"] == "No complete answers"


def test_unknown_priority_mapping_is_not_invented(payload):
    payload["report"]["owner_report"]["services"][0]["questions"] = None
    r = build_owner_report(payload)
    assert r["services"][0]["status"] == "Coverage not mapped"
    assert sum(s["answers"] for s in r["services"]) == 24


def test_overlap_or_unknown_questions_rejected(payload):
    payload["report"]["owner_report"]["services"][1]["questions"] = [2, 3]
    with pytest.raises(ValueError, match="partition"):
        build_owner_report(payload)


def test_duplicate_answer_or_retry_rejected(payload):
    payload["baseline_validation"]["responses"].append(deepcopy(payload["baseline_validation"]["responses"][0]))
    with pytest.raises(ValueError, match="Duplicate"):
        build_owner_report(payload)
    payload["baseline_validation"]["responses"][-1]["response_id"] = "retry"
    with pytest.raises(ValueError, match="resolve retries"):
        build_owner_report(payload)


def test_missing_evidence_is_not_a_negative_finding(payload):
    payload["report"]["owner_report"] = {"services": [{"name": "Priority", "questions": None}]}
    payload["website_evidence"]["audits"] = []
    payload["review_evidence"]["review_sets"] = []
    r = build_owner_report(payload)
    assert len(r["config"]["actions"]) == 1
    assert r["config"]["actions"][0]["title"].startswith("Investigation:")
    assert "strengths" not in r["config"] and "gaps" not in r["config"]


def test_sources_and_quotes_fail_closed(payload):
    payload["report"]["owner_report"]["sources"][0]["excerpt"] = "Invented quotation"
    with pytest.raises(ValueError, match="Unverified exact excerpt"):
        build_owner_report(payload)
    payload["report"]["owner_report"]["sources"][0]["record_id"] = "missing"
    with pytest.raises(ValueError, match="Missing website evidence"):
        build_owner_report(payload)


def test_action_requires_inspectable_deliverable(payload):
    del payload["report"]["owner_report"]["actions"][0]["check"]
    with pytest.raises(ValueError, match="completion check"):
        build_owner_report(payload)


def test_new_or_edited_questions_stay_separate(payload):
    baseline = build_owner_report(payload)
    future = deepcopy(baseline)
    future["questions"].append({"order": 5, "prompt": "A newly added service question"})
    result = comparison_partition(baseline, future)
    assert len(result["baseline_questions"]) == 4 and len(result["new_questions"]) == 1
    assert result["settings_comparable"]
    future["mode"] = "search_grounded"
    assert not comparison_partition(baseline, future)["settings_comparable"]
    future["questions"][0]["prompt"] = "An edited baseline question"
    result = comparison_partition(baseline, future)
    assert len(result["baseline_questions"]) == 3 and len(result["new_questions"]) == 2 and len(result["removed_questions"]) == 1


def test_synthetic_pdf_is_consistent_linked_and_has_no_empty_owner_page(payload):
    reader = PdfReader(io.BytesIO(render_poc_audit_pdf(payload)))
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert "12 of 24 answers" in text
    assert "10 of 12 answers" in text and "2 of 6 answers" in text
    assert "Hair extensions" in text and "Not tested" in text
    assert "Owner-nominated competitors" not in text
    assert "see page 6" not in text.lower() and "on page 6" not in text.lower()
    assert "SYNTHETIC" in reader.metadata.title and "Synthetic" in reader.metadata.subject
    assert "2 repetitions per question per provider" in text
    assert len(reader.outline) >= 10
    assert all(page.extract_text().strip() for page in reader.pages)
    assert any(page.get("/Annots") for page in reader.pages)


def test_no_verified_competitors_does_not_allocate_comparison_page(payload):
    payload["diagnostic"]["cohort"] = []
    reader = PdfReader(io.BytesIO(render_poc_audit_pdf(payload)))
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert "RELEVANT BUSINESSES" not in text
    assert len(reader.pages) < len(PdfReader(io.BytesIO(render_poc_audit_pdf(synthetic_owner_services_payload()))).pages)


def test_long_business_names_and_missing_reviews_flow(payload):
    payload["diagnostic"]["cohort"][0]["business_name"] = "Example Specialist Hair Colour and Curly Hair Consultation Studio Serving Several Neighbourhoods"
    data = render_poc_audit_pdf(payload)
    assert data.startswith(b"%PDF")
    assert "Not assessed" in "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(data)).pages)


def test_provider_and_repetition_data_not_fixed_to_three(payload):
    payload["baseline_validation"]["responses"] = [r for r in payload["baseline_validation"]["responses"] if r["provider"] == "OpenAI" and r["repetition"] == 1]
    payload["methodology"]["providers"] = ["OpenAI"]
    r = build_owner_report(payload)
    assert r["providers"] == ["OpenAI"] and r["repetition_values"] == [1]
    assert r["answers"] == 4


def test_index_escapes_untrusted_answers_and_keeps_provenance(payload):
    payload["baseline_validation"]["responses"][0]["raw_response"] += "<script>alert(1)</script>"
    index = evidence_index_html(payload)
    assert "<script>" not in index and "&lt;script&gt;" in index
    assert "synthetic-q1-r1-OpenAI" in index and "Complete unfiltered recommendation market" in index
    assert "Read-only copy" in index


def test_v4_render_is_deterministic_and_database_free(payload):
    from unittest.mock import patch
    with patch("src.database.get_engine", side_effect=AssertionError("No database access")):
        assert render_poc_audit_pdf(payload) == render_poc_audit_pdf(payload)
