"""End-to-end: a reviewer-approved positioning finding flows into the LS, nothing else does.

Mirrors tests/test_client_summary_mentions.py's shape: builds on
synthetic_owner_services_payload() (its default owner_report has no positioning_summary at all,
so every pre-existing test using that fixture is unaffected) and injects
payload["report"]["owner_report"]["positioning_summary"] exactly as
app/pages/10_AI_Report_Generator.py would after a reviewer includes a candidate from
build_positioning_candidates.
"""
from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader

from src.client_summary.adapter import build_client_summary_report, render_client_summary_pdf
from src.owner_services_synthetic import synthetic_owner_services_payload


def _candidate(**overrides):
    candidate = {
        "proposition_key": "balayage", "proposition": "Balayage", "suggestion": "CUSTOMER_STRENGTH",
        "reason": "Reviewed customer support meets the thresholds.", "owner_intended": None, "tested": None,
        "customer_support_records": 3, "customer_source_classes": 2, "interventions": [],
        "capture_id": "00000000-0000-0000-0000-000000000001", "capture_archived_at": "2026-10-02T09:00:00+00:00",
    }
    candidate.update(overrides)
    return candidate


def _payload_with_positioning(*candidates):
    payload = synthetic_owner_services_payload()
    payload["report"]["owner_report"]["positioning_summary"] = list(candidates)
    return payload


def _pdf_text(summary):
    text = " ".join(p.extract_text() for p in PdfReader(BytesIO(render_client_summary_pdf(summary))).pages)
    return " ".join(text.split())


def test_default_fixture_has_no_positioning_section():
    # The shared fixture sets no positioning_summary at all - must stay inert, same as every
    # pre-existing test that renders it unmodified.
    summary = build_client_summary_report(synthetic_owner_services_payload())
    assert summary["positioning_summary"] == []
    assert "POSITIONING EVIDENCE" not in _pdf_text(summary)
    assert "9 / 12" in _pdf_text(summary)  # page count unchanged by this feature


def test_an_unrecognised_suggestion_label_is_dropped_defensively():
    summary = build_client_summary_report(_payload_with_positioning(_candidate(suggestion="SOMETHING_NEW")))
    assert summary["positioning_summary"] == []
    assert "POSITIONING EVIDENCE" not in _pdf_text(summary)


def test_an_approved_finding_renders_as_its_own_extra_page():
    summary = build_client_summary_report(_payload_with_positioning(_candidate()))
    assert len(summary["positioning_summary"]) == 1
    text = _pdf_text(summary)
    assert "POSITIONING EVIDENCE" in text
    assert "Balayage" in text
    assert "Reviewed customer evidence supports this" in text
    assert "13 / 13" in text  # base fixture already has 3 review pages (9 + 3 + 1 = 13)


def test_a_recorded_action_appears_beside_its_finding():
    candidate = _candidate(interventions=[{"status": "PLANNED", "hypothesis": "Rewrite the balayage page"}])
    summary = build_client_summary_report(_payload_with_positioning(candidate))
    text = _pdf_text(summary)
    assert "PLANNED" in text
    assert "Rewrite the balayage page" in text


def test_up_to_six_findings_are_shown_and_no_more():
    candidates = [_candidate(proposition_key=f"prop-{i}", proposition=f"Priority {i}") for i in range(9)]
    summary = build_client_summary_report(_payload_with_positioning(*candidates))
    assert len(summary["positioning_summary"]) == 6
