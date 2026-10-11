"""A test may hold up to twenty questions. Final Beta reports all of them; the summary PDF keeps its eight-question layout."""
import io
from datetime import date

import pytest

from src.client_summary.adapter import ClientSummaryError, build_client_summary_report
from src.client_summary.model import MAX_QUESTIONS
from src.client_summary.pdf import LAYOUT_QUESTIONS, ReportLayoutError, render_pdf
from src.final_beta_pdf import render_final_beta_pdf
from src.final_beta_report import build_final_beta_report
from src.owner_services_synthetic import synthetic_owner_services_payload


def test_final_beta_reports_a_twenty_question_test_in_full():
    from pypdf import PdfReader
    payload = synthetic_owner_services_payload(extra_questions=16)
    summary = build_client_summary_report(payload, max_questions=MAX_QUESTIONS)
    assert len(summary["questions"]) == 20
    data = build_final_beta_report(summary, responses=list(payload["baseline_validation"]["responses"]), results=[],
                                   confirmed_names=[], today=date(2026, 10, 11))
    assert len([q for q in data["questions"] if q["complete"]]) == 20
    assert data["total"] == 20 * 6 and data["recommended"] == 12, "the extra questions add answers, not appearances"
    text = " ".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(render_final_beta_pdf(data))).pages)
    assert "synthetic service 16" in " ".join(text.split()), "the last question is laid out, not dropped"


def test_a_twenty_first_question_is_refused():
    with pytest.raises(ClientSummaryError, match="at most 20 questions"):
        build_client_summary_report(synthetic_owner_services_payload(extra_questions=17), max_questions=MAX_QUESTIONS)


def test_the_client_summary_still_refuses_more_than_eight_questions_and_names_the_alternative():
    payload = synthetic_owner_services_payload(extra_questions=5)
    with pytest.raises(ClientSummaryError, match="Final Beta"):
        build_client_summary_report(payload)
    with pytest.raises(ReportLayoutError, match="Final Beta"):
        render_pdf(build_client_summary_report(payload, max_questions=MAX_QUESTIONS))
    assert LAYOUT_QUESTIONS == 8
    assert len(build_client_summary_report(synthetic_owner_services_payload(extra_questions=4))["questions"]) == 8
