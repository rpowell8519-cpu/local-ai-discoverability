"""Free check: customer-safe projection and worker flow. Synthetic data only; no provider calls."""
from contextlib import contextmanager
from unittest.mock import patch

import pandas as pd
import pytest

from src import free_check_worker as worker
from src.free_check_projection import PROJECTION_VERSION, build_projection

PROVIDERS = ["OpenAI", "Claude", "Gemini"]
QUESTIONS = [f"Where can I find good private dining option {n} in Hove?" for n in range(1, 6)]
QUERIES = [{"id": f"q{n}", "base_prompt_order": n, "prompt_text": q} for n, q in enumerate(QUESTIONS, 1)]
TARGET = "discovery:run"


def result(query, provider, *, recommended=False, mentioned=False, status="completed", complete=True):
    return {"query_id": query, "provider": provider, "status": status, "response_complete": complete,
            "target_recommended": recommended, "target_mentioned": mentioned}


def rec(query, provider, name, *, place_id="", status="unresolved", business_name=None):
    return {"query_id": query, "provider": provider, "raw_business_name": name, "google_place_id": place_id,
            "business_name": business_name or name, "resolution_status": status}


def project(results, recommendations):
    return build_projection(business_name="Synthetic Bistro", questions=QUESTIONS, providers=PROVIDERS,
                            queries=QUERIES, results=results, recommendations=recommendations,
                            target_id=TARGET, measured_at="2026-10-03T12:00:00+00:00",
                            benchmark_mode="search_grounded")


def full_results(overrides=None):
    rows = {(q["id"], p): result(q["id"], p) for q in QUERIES for p in PROVIDERS}
    rows.update(overrides or {})
    return list(rows.values())


def test_counts_are_per_valid_answer_and_consistent_across_breakdowns():
    results = full_results({("q1", "OpenAI"): result("q1", "OpenAI", recommended=True),
                              ("q1", "Claude"): result("q1", "Claude", recommended=True),
                              ("q5", "Gemini"): result("q5", "Gemini", mentioned=True)})
    out = project(results, [])
    assert out["schema_version"] == PROJECTION_VERSION
    assert (out["expected_answers"], out["valid_answers"]) == (15, 15)
    assert out["target"] == {"name": "Synthetic Bistro", "recommended_answers": 2, "mentioned_answers": 3,
                             "recommendation_rate": round(2 / 15, 4)}
    assert sum(p["target_recommended"] for p in out["providers"]) == 2
    assert sum(q["target_recommended"] for q in out["questions"]) == 2
    assert [q["text"] for q in out["questions"]] == QUESTIONS


def test_other_businesses_count_once_per_answer_and_never_absorb_the_target():
    recommendations = [
        rec("q1", "OpenAI", "Rival One"), rec("q1", "OpenAI", "Rival One"),  # repeated within one answer
        rec("q2", "Claude", "rival  one!"),  # same name, different formatting
        rec("q1", "OpenAI", "The Listed Place", place_id="place-1", status="exact", business_name="Listed Place"),
        rec("q3", "Gemini", "Listed Place Hove", place_id="place-1", status="exact_group", business_name="Listed Place"),
        rec("q4", "Gemini", "Listed Place", place_id="place-1", status="exact", business_name="Listed Place"),
        rec("q1", "OpenAI", "Synthetic Bistro", place_id=TARGET, status="exact"),
        rec("q2", "OpenAI", "synthetic bistro"),  # unresolved spelling of the target is not a competitor
    ]
    out = project(full_results(), recommendations)
    assert out["businesses"] == [
        {"name": "Listed Place", "answers": 3, "identity": "matched", "is_target": False},
        {"name": "Rival One", "answers": 2, "identity": "unverified", "is_target": False},
    ]
    assert out["rank"] == {"position": 3, "of": 3, "tied_with": 0}


def test_missing_answers_shrink_the_denominator_and_are_not_zero():
    results = full_results({("q1", "OpenAI"): result("q1", "OpenAI", status="failed"),
                              ("q2", "OpenAI"): result("q2", "OpenAI", complete=False),
                              ("q3", "Claude"): result("q3", "Claude", recommended=True)})
    out = project(results, [rec("q1", "OpenAI", "Counted Nowhere")])
    assert out["valid_answers"] == 13
    assert out["target"]["recommendation_rate"] == round(1 / 13, 4)
    assert out["providers"][0] == {"provider": "OpenAI", "expected": 5, "valid": 3, "target_recommended": 0}
    assert out["questions"][0]["valid"] == 2
    assert out["businesses"] == [], "a recommendation in an invalid answer is not counted"
    assert any("2 of 15 answers" in c for c in out["caveats"])
    assert out["rank"] is not None


def test_missing_flags_and_fuzzy_matches_are_never_counted_as_confirmed():
    nan = float("nan")
    results = full_results({("q1", "OpenAI"): result("q1", "OpenAI", recommended=nan, mentioned=nan),
                            ("q2", "OpenAI"): result("q2", "OpenAI", complete=nan)})
    out = project(results, [rec("q3", "Claude", "Maybe Listed", place_id="place-9", status="fuzzy", business_name="Listed Nine"),
                            rec("q4", "Claude", "Nameless", place_id=nan)])
    assert out["valid_answers"] == 14
    assert out["target"]["recommended_answers"] == 0 and out["target"]["mentioned_answers"] == 0
    assert out["businesses"] == [
        {"name": "Maybe Listed", "answers": 1, "identity": "unverified", "is_target": False},
        {"name": "Nameless", "answers": 1, "identity": "unverified", "is_target": False},
    ]


def test_no_combined_rank_without_adequate_coverage():
    one_provider_missing = [result(q["id"], p) for q in QUERIES for p in PROVIDERS if p != "Gemini"]
    assert project(one_provider_missing, [])["rank"] is None
    too_few = [result("q1", p) for p in PROVIDERS]
    out = project(too_few, [])
    assert out["rank"] is None and any("Too few answers" in c for c in out["caveats"])
    empty = project([], [])
    assert empty["target"]["recommendation_rate"] is None and empty["valid_answers"] == 0


def test_tied_businesses_share_the_reported_position():
    results = full_results({("q1", "OpenAI"): result("q1", "OpenAI", recommended=True)})
    out = project(results, [rec("q2", "Claude", "Level Rival"), rec("q1", "Gemini", "Ahead"), rec("q2", "Gemini", "Ahead")])
    assert out["rank"] == {"position": 2, "of": 3, "tied_with": 1}


# ---- worker flow ---------------------------------------------------------------------------------

class Engine:
    @contextmanager
    def begin(self):
        yield "connection"


CHECK = {"id": "check-1", "business_name": " Synthetic Bistro ", "location": "Hove", "website": None,
         "services": "private dining", "questions": QUESTIONS}
SETTINGS = {"api_keys": {p: "synthetic" for p in PROVIDERS}, "models": dict(worker.DEFAULT_MODELS), "daily_cap": 10}


def job(**changes):
    return {"id": "job-1", "check_id": "check-1", "run_id": None, "reserved_calls": 15,
            "attempt_count": 1, "max_attempts": 3, **changes}


@contextmanager
def harness(run_status, *, retry_plan=None):
    calls = {"execute": [], "complete": [], "release": [], "attach": [], "created": [], "heartbeat": []}
    queries = [{"id": q["id"], "base_prompt_order": q["base_prompt_order"]} for q in QUERIES]

    def execute(**kwargs):
        calls["execute"].append(kwargs)
        kwargs["progress_callback"](len(kwargs["call_plan"]), len(kwargs["call_plan"]))

    def create(**kwargs):
        calls["created"].append(kwargs)
        return {"run_id": "run-1", "target_google_place_id": "discovery:run-1"}

    patches = {
        "create_discovery_run": create,
        "create_visibility_queries": lambda **k: queries,
        "execute_calls": execute,
        "finalise_run_from_results": lambda **k: run_status,
        "get_run_results": lambda run_id: pd.DataFrame(full_results()),
        "get_run_queries": lambda run_id: pd.DataFrame(queries),
        "get_visibility_run": lambda run_id: {"target_google_place_id": "discovery:run-1",
                                               "models": {"OpenAI": "saved-model"}, "completed_at": "2026-10-03"},
        "build_retry_plan": lambda **k: retry_plan or [],
        "build_recommendation_records": lambda **k: pd.DataFrame([]),
        "load_entity_aliases": lambda: pd.DataFrame([]),
        "_directory": lambda *a: pd.DataFrame([]),
    }
    job_patches = {
        "load_check": lambda connection, check_id: dict(CHECK),
        "attach_run": lambda connection, **k: calls["attach"].append(k),
        "heartbeat": lambda connection, **k: calls["heartbeat"].append(k),
        "complete_job": lambda connection, **k: calls["complete"].append(k),
        "release_for_retry": lambda connection, **k: calls["release"].append(k),
    }
    active = [patch.object(worker, name, value) for name, value in patches.items()]
    active += [patch.object(worker.jobs, name, value) for name, value in job_patches.items()]
    for item in active:
        item.start()
    try:
        yield calls
    finally:
        for item in active:
            item.stop()


def test_new_check_runs_fifteen_calls_as_a_free_check_and_delivers():
    with harness("completed") as calls:
        assert worker.run_job(job(), settings=SETTINGS, worker_id="w", engine=Engine()) == "completed"
    created = calls["created"][0]
    assert created["panel_kind"] == "free_check" and created["target_google_place_id"] is None
    assert created["repeat_count"] == 1 and [p["prompt"] for p in created["prompts"]] == QUESTIONS
    assert calls["attach"] == [{"job_id": "job-1", "worker_id": "w", "run_id": "run-1"}]
    executed = calls["execute"][0]
    assert len(executed["call_plan"]) == 15 and executed["target_business_name"] == "Synthetic Bistro"
    assert executed["known_businesses"] == [{"google_place_id": "discovery:run-1", "business_name": "Synthetic Bistro"}]
    assert calls["heartbeat"][-1]["completed_calls"] == 15
    delivered = calls["complete"][0]
    assert delivered["check_status"] == "completed" and delivered["projection"]["valid_answers"] == 15
    assert calls["release"] == []


def test_retry_reuses_the_saved_run_and_only_repeats_missing_calls():
    missing = [{"id": "q5", "provider": "Gemini"}]
    with harness("completed", retry_plan=missing) as calls:
        outcome = worker.run_job(job(run_id="run-1", attempt_count=2), settings=SETTINGS, worker_id="w", engine=Engine())
    assert outcome == "completed" and calls["created"] == [] and calls["attach"] == []
    assert calls["execute"][0]["call_plan"] == missing
    assert calls["execute"][0]["models"] == {"OpenAI": "saved-model"}, "a retry keeps the run's original models"
    assert calls["heartbeat"][-1]["completed_calls"] == 15


@pytest.mark.parametrize("run_status,attempt,expected,delivered", [
    ("partial", 1, "retry", False),    # attempts remain: try the missing answers again
    ("partial", 3, "partial", True),   # last attempt: deliver what completed
    ("failed", 1, "retry", False),
    ("failed", 3, "retry", False),     # released; the queue closes it as failed
])
def test_partial_and_failed_runs(run_status, attempt, expected, delivered):
    with harness(run_status) as calls:
        assert worker.run_job(job(attempt_count=attempt), settings=SETTINGS, worker_id="w", engine=Engine()) == expected
    assert bool(calls["complete"]) is delivered and bool(calls["release"]) is not delivered


def test_check_larger_than_its_reservation_makes_no_calls():
    with harness("completed") as calls:
        with pytest.raises(ValueError, match="reserved"):
            worker.run_job(job(reserved_calls=10), settings=SETTINGS, worker_id="w", engine=Engine())
    assert calls["created"] == [] and calls["execute"] == []


def test_crashed_job_is_released_and_idle_queue_returns_none():
    released = []
    with patch.object(worker.jobs, "claim_next_job", return_value=job()), \
         patch.object(worker, "run_job", side_effect=RuntimeError("secret detail")), \
         patch.object(worker.jobs, "release_for_retry", lambda connection, **k: released.append(k)):
        assert worker.process_one(settings=SETTINGS, worker_id="w", engine=Engine()) == "error"
    assert released == [{"job_id": "job-1", "worker_id": "w", "error": "RuntimeError"}], "no exception text is stored"
    with patch.object(worker.jobs, "claim_next_job", return_value=None):
        assert worker.process_one(settings=SETTINGS, worker_id="w", engine=Engine()) is None


def test_worker_refuses_to_start_without_every_provider_key():
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        worker.load_settings({"OPENAI_API_KEY": "a", "ANTHROPIC_API_KEY": "b"})
    settings = worker.load_settings({"OPENAI_API_KEY": "a", "ANTHROPIC_API_KEY": "b", "GEMINI_API_KEY": "c",
                                     "ANTHROPIC_MODEL": "override", "FREE_CHECK_DAILY_CAP": "4"})
    assert settings["models"]["Claude"] == "override" and settings["daily_cap"] == 4
