"""Only reviewed, reportable positioning rows reach a candidate list; nothing is invented here."""
from unittest.mock import patch

import pandas as pd

from src.positioning_report_summary import build_positioning_candidates
from test_positioning_triangulation import inputs, reviews

MODULE = "src.positioning_report_summary"


def _patched(cap, *, decisions=(), interventions=(), ready=True, captures=None):
    cap.setdefault("archived_at", "2026-10-02T09:00:00+00:00")
    values = {
        f"{MODULE}.list_captures": captures if captures is not None else [{"id": cap["id"]}],
        f"{MODULE}.load_capture": cap,
        f"{MODULE}.list_decisions": list(decisions),
        f"{MODULE}.load_owner_brief": None,
        f"{MODULE}.get_run_queries": pd.DataFrame([]),
        f"{MODULE}.load_confirmed_question_map": {},
        f"{MODULE}.intervention_storage_ready": ready,
        f"{MODULE}.list_interventions": list(interventions),
    }
    stack = [patch(target, return_value=value) for target, value in values.items()]
    for ctx in stack:
        ctx.start()
    return stack


def _stop(stack):
    for ctx in stack:
        ctx.stop()


def intervention(cap, *, proposition_key="balayage", status="PLANNED"):
    return {"proposition_key": proposition_key, "record": {
        "hypothesis": "Rewrite the balayage page and align the Google listing", "status": status,
        "planned_date": "2026-10-10", "implemented_date": None,
    }}


def test_no_capture_means_no_candidates():
    stack = _patched({"id": "unused"}, captures=[])
    try:
        assert build_positioning_candidates("place") == []
    finally:
        _stop(stack)


def test_capture_with_no_reviewed_decisions_means_no_candidates():
    cap, *_ = inputs()
    stack = _patched(cap, decisions=[])
    try:
        assert build_positioning_candidates("place") == []
    finally:
        _stop(stack)


def test_reportable_suggestion_becomes_a_candidate_without_raw_excerpts():
    cap, brief, run, questions = inputs()
    stack = _patched(cap, decisions=reviews(cap))
    try:
        candidates = build_positioning_candidates("place", benchmark_run=run)
    finally:
        _stop(stack)
    assert len(candidates) == 1
    row = candidates[0]
    assert row["proposition_key"] == "balayage"
    assert row["suggestion"] in {"CUSTOMER_STRENGTH", "STRATEGIC_CORE", "HIDDEN_STRENGTH"}
    assert row["customer_support_records"] == 2
    assert "raw_value" not in row and "evidence_id" not in row


def test_needs_review_without_a_linked_intervention_is_not_a_candidate():
    cap, *_ = inputs()
    # UNCERTAIN decisions produce a NEEDS_REVIEW row (reviewed, but nothing affirmed) - that
    # alone must not reach the client without a recorded intervention naming it.
    stack = _patched(cap, decisions=reviews(cap, choice="UNCERTAIN"))
    try:
        candidates = build_positioning_candidates("place")
    finally:
        _stop(stack)
    assert candidates == []


def test_a_linked_intervention_is_reportable_even_without_strong_evidence():
    cap, *_ = inputs()
    stack = _patched(cap, decisions=[], interventions=[intervention(cap)])
    try:
        candidates = build_positioning_candidates("place")
    finally:
        _stop(stack)
    assert len(candidates) == 1
    assert candidates[0]["suggestion"] == "NEEDS_REVIEW"
    assert candidates[0]["interventions"] == [
        {"hypothesis": "Rewrite the balayage page and align the Google listing", "status": "PLANNED",
         "planned_date": "2026-10-10", "implemented_date": None}
    ]


def test_intervention_storage_not_ready_is_treated_as_no_interventions():
    cap, *_ = inputs()
    stack = _patched(cap, decisions=[], ready=False, interventions=[intervention(cap)])
    try:
        candidates = build_positioning_candidates("place")
    finally:
        _stop(stack)
    assert candidates == []
