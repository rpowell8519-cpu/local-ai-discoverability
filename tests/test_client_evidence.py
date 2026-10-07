"""The client evidence summary restates saved measurements and reviews; it never fills gaps itself."""
import sys
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.client_evidence import build_client_evidence  # noqa: E402

BUSINESS = {"google_place_id": "target", "business_name": "Synthetic Bistro", "primary_group": "restaurants"}
GOALS = ["Best restaurant in Hove", "Best date night restaurant"]
BRIEF = {"target_google_place_id": "target", "owner_context": {"priority_services": GOALS}}


def row(place, name, family, appearances, *, completed=3, names=()):
    return {"google_place_id": place, "business_name": name, "family": family, "provider": "Claude",
            "expected_answers": 3, "completed_answers": completed, "appearances": appearances,
            "unapproved_possible_names": [{"name": n, "recommendations": 1, "reason": "Contains the business's name"}
                                          for n in names]}


def wave(run_id, day, rows):
    return {"run_id": run_id, "started_at": datetime(2026, 10, day, tzinfo=timezone.utc), "rows": rows, "issues": []}


def excerpt(evidence_id, source):
    return {"evidence_id": evidence_id, "kind": "proposition_candidate", "source_class": source}


CAPTURE = {"id": "capture-1", "payload": {"matrix": {"observations": [
    excerpt("e1", "google_reviews"), excerpt("e2", "google_reviews"), excerpt("e3", "website"),
    {"evidence_id": "f1", "kind": "fact", "source_class": "website"}]}}}


def build(**changes):
    values = {"business": BUSINESS, "brief": BRIEF, "summaries": [], "incomplete_waves": 0, "capture": None,
              "decisions": [], "positioning": None, "actions": []}
    return build_client_evidence(**{**values, **changes})


def test_each_goal_uses_its_newest_complete_test_and_ranks_who_was_recommended_more():
    older = wave("run-1", 1, [row("target", "Synthetic Bistro", GOALS[0], 3), row("other", "Rival", GOALS[0], 0)])
    newer = wave("run-2", 3, [row("target", "Synthetic Bistro", GOALS[0], 1),
                              row("quiet", "Quiet Place", GOALS[0], 0),
                              row("rival", "Rival", GOALS[0], 2, names=["Rival (Church Road)"])])
    out = build(summaries=[older, newer])
    goal, = out["goals"]
    assert (goal["run_id"], goal["recommended"], goal["answers"]) == ("run-2", 1, 3)
    assert [o["business"] for o in goal["compared_with"]] == ["Rival", "Quiet Place"]
    assert goal["compared_with"][0] == {"business": "Rival", "recommended": 2, "answers": 3, "unconfirmed": 1}
    assert (out["total_recommended"], out["total_answers"]) == (1, 3)
    assert out["names_to_confirm"] == [{"ai_name": "Rival (Church Road)", "may_be": "Rival", "answers": 1,
                                        "why": "Contains the business's name"}]


def test_an_incomplete_answer_grid_is_not_reported_as_a_result():
    partial = wave("run-1", 3, [row("target", "Synthetic Bistro", GOALS[0], 0, completed=2)])
    out = build(summaries=[partial], incomplete_waves=1)
    assert out["goals"] == [] and out["total_answers"] == 0
    assert any("did not finish" in task["task"] for task in out["tasks"])


def test_tasks_follow_what_is_actually_missing():
    assert [t["task"] for t in build(brief=None)["tasks"]][0] == "Record what the owner wants to be known for"
    unmeasured = [t["task"] for t in build()["tasks"]]
    assert "Measure the owner's goals" in unmeasured and any("Save a copy" in t for t in unmeasured)
    assert "Measure the owner's goals" not in [t["task"] for t in build(has_benchmark=True)["tasks"]]
    tested = wave("run-1", 3, [row("target", "Synthetic Bistro", GOALS[0], 1)])
    out = build(summaries=[tested], capture=CAPTURE, decisions=[{"evidence_id": "e1"}])
    tasks = {t["task"]: t for t in out["tasks"]}
    assert "Review 2 excerpts (1 from customers)" in tasks, "facts and already-decided excerpts are not counted"
    assert tasks["1 owner goal has no completed test"]["detail"] == GOALS[1]
    assert out["excerpts"] == {"total": 3, "undecided": 2, "has_capture": True}
    done = build(summaries=[tested], capture=CAPTURE, decisions=[{"evidence_id": e} for e in ("e1", "e2", "e3")])
    assert not any(t["task"].startswith("Review") for t in done["tasks"])


def test_only_reviewed_suggestions_are_worded_and_actions_are_listed_as_recorded():
    positioning = {"rows": [
        {"proposition": "Wine selection", "suggestion": "CUSTOMER_STRENGTH", "owner_intended": None, "customer_support_records": 9},
        {"proposition": "Private dining", "suggestion": "NEEDS_REVIEW", "owner_intended": None, "customer_support_records": 0}]}
    actions = [{"record": {"finding": "No private dining page", "hypothesis": "Add one", "status": "PLANNED",
                           "planned_date": "2026-11-01", "implemented_date": None}}]
    out = build(capture=CAPTURE, positioning=positioning, actions=actions)
    assert [s["topic"] for s in out["suggestions"]] == ["Wine selection"] and out["topics_awaiting_review"] == 1
    assert "Customers praise this" in out["suggestions"][0]["meaning"]
    assert out["actions"] == [{"finding": "No private dining page", "action": "Add one", "status": "PLANNED",
                               "planned": "2026-11-01", "done": None}]


def run_page(*, runs, summaries_by_run, captures=()):
    pytest.importorskip("streamlit")
    import streamlit as st
    from streamlit.testing.v1 import AppTest
    st.cache_data.clear()
    page = str(Path(__file__).resolve().parents[1] / "app" / "shelved_pages" / "1_Client_Evidence.py")
    stack = ExitStack()
    patches = {
        "src.evidence_foundations_repository.list_foundation_businesses": [BUSINESS],
        "src.evidence_foundations_repository.list_business_runs": runs,
        "src.positioning_repository.load_owner_brief": BRIEF,
        "src.public_evidence_archive_repository.list_captures": list(captures),
        "src.public_evidence_archive_repository.list_decisions": [],
        "src.intervention_repository.list_interventions": [],
    }
    for name, value in patches.items():
        stack.enter_context(patch(name, return_value=value))
    stack.enter_context(patch("src.evidence_foundations_repository.load_measurement_wave",
                              side_effect=lambda run_id: {"panel_kind": "focused"} if run_id in summaries_by_run else None))
    stack.enter_context(patch("src.focused_monitoring_repository.load_wave_summary",
                              side_effect=lambda run, businesses: summaries_by_run[str(run["id"])]))
    with stack:
        return AppTest.from_file(page, default_timeout=60).run()


def saved_run(run_id):
    return {"id": run_id, "started_at": datetime(2026, 10, 3, tzinfo=timezone.utc), "status": "completed",
            "prompt_count": 1, "repeat_count": 3, "providers": ["Claude"]}


def test_page_shows_standing_tasks_and_unconfirmed_names_without_writing():
    summary = wave("run-1", 3, [row("target", "Synthetic Bistro", GOALS[0], 1),
                                row("rival", "Rival", GOALS[0], 2, names=["Rival (Church Road)"])])
    at = run_page(runs=[saved_run("run-1")], summaries_by_run={"run-1": summary})
    assert not at.exception and not at.error
    assert [(m.label, m.value) for m in at.metric] == [("Recommended in", "1 of 3 answers")]
    text = " ".join(m.value for m in at.markdown)
    assert "Synthetic Bistro was recommended in 1 of 3 answers." in text
    assert "1 owner goal has no completed test" in text and "1 name the AI used may be a business being compared" in text
    assert not at.button, "the page offers no action of its own"


def test_page_points_a_report_only_client_at_its_report_and_handles_nothing_measured():
    report_only = run_page(runs=[saved_run("benchmark-1")], summaries_by_run={})
    assert not report_only.exception
    assert any("report benchmark holds the reviewed results" in i.value for i in report_only.info)
    assert "Measure the owner's goals" not in " ".join(m.value for m in report_only.markdown)
    empty = run_page(runs=[], summaries_by_run={})
    assert not empty.exception and any("Nothing has been measured" in i.value for i in empty.info)
    assert "Measure the owner's goals" in " ".join(m.value for m in empty.markdown)
