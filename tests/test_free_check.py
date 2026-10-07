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


def test_target_recommendation_uses_the_name_resolver_not_only_the_scan_flag():
    # The owner typed one spelling; the answers list another. The scan-time flag saw a mention only.
    results = full_results({("q2", "Claude"): result("q2", "Claude", mentioned=True),
                            ("q5", "OpenAI"): result("q5", "OpenAI", mentioned=True),
                            ("q3", "Gemini"): result("q3", "Gemini", mentioned=True)})
    recommendations = [
        rec("q2", "Claude", "The Synthetic Bistro", place_id=TARGET, status="exact_group"),
        rec("q5", "OpenAI", "The Synthetic Bistro", place_id=TARGET, status="exact"),
        rec("q3", "Gemini", "Synthetic Bistrot", place_id=TARGET, status="fuzzy"),  # not confident: not counted
        rec("q1", "Gemini", "The Synthetic Bistro", place_id=TARGET, status="exact"),
        rec("q4", "Claude", "Rival One"),
    ]
    results = [r for r in results if not (r["query_id"] == "q1" and r["provider"] == "Gemini")]  # invalid answer
    out = project(results, recommendations)
    assert out["target"]["recommended_answers"] == 2 and out["target"]["mentioned_answers"] == 3
    assert [q["target_recommended"] for q in out["questions"]] == [0, 1, 0, 0, 1]
    assert sum(p["target_recommended"] for p in out["providers"]) == 2
    assert out["businesses"] == [{"name": "Rival One", "answers": 1, "identity": "unverified", "is_target": False}]
    assert out["rank"]["position"] == 1


def test_cells_show_each_question_and_provider_and_keep_missing_distinct():
    results = full_results({("q1", "OpenAI"): result("q1", "OpenAI", recommended=True),
                            ("q2", "Claude"): result("q2", "Claude", status="failed")})
    out = project(results, [rec("q3", "Gemini", "The Synthetic Bistro", place_id=TARGET, status="exact")])
    cells = {(c["order"], c["provider"]): c["state"] for c in out["cells"]}
    assert len(out["cells"]) == 15
    assert cells[(1, "OpenAI")] == "recommended" and cells[(3, "Gemini")] == "recommended"
    assert cells[(2, "Claude")] == "missing" and cells[(1, "Claude")] == "not_recommended"
    for question in out["questions"]:
        assert question["target_recommended"] == sum(
            1 for (order, _), state in cells.items() if order == question["order"] and state == "recommended")
    assert project([], [])["cells"][0]["state"] == "missing"


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


CHECK = {"id": "check-1", "owner_user_id": "owner-1", "business_name": " Synthetic Bistro ", "location": "Hove",
         "website": None, "services": "private dining", "questions": QUESTIONS, "claimed_google_place_id": None}
SETTINGS = {"api_keys": {p: "synthetic" for p in PROVIDERS}, "models": dict(worker.DEFAULT_MODELS),
            "daily_cap": 10, "email": None}
EMAIL = {"api_key": "synthetic-key", "sender": "Found.in.Brighton <hello@example.org>", "site_url": "https://example.org"}


def job(**changes):
    return {"id": "job-1", "check_id": "check-1", "run_id": None, "reserved_calls": 15,
            "attempt_count": 1, "max_attempts": 3, **changes}


@contextmanager
def harness(run_status, *, retry_plan=None, check=None, listing=None):
    calls = {"execute": [], "complete": [], "release": [], "attach": [], "created": [], "heartbeat": [], "emails": []}
    queries = [{"id": q["id"], "base_prompt_order": q["base_prompt_order"]} for q in QUERIES]

    def execute(**kwargs):
        calls["execute"].append(kwargs)
        kwargs["progress_callback"](len(kwargs["call_plan"]), len(kwargs["call_plan"]))

    def create(**kwargs):
        calls["created"].append(kwargs)
        return {"run_id": "run-1", "target_google_place_id": kwargs["target_google_place_id"] or "discovery:run-1"}

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
        "send_results_email": lambda **k: calls["emails"].append(k) or True,
    }
    job_patches = {
        "load_check": lambda connection, check_id: dict(check or CHECK),
        "confirmed_listing": lambda connection, place_id: listing,
        "owner_email": lambda connection, owner_user_id: "owner@example.org",
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


def test_reproject_rebuilds_a_delivered_summary_without_provider_calls():
    saved = []
    delivered = {**CHECK, "status": "completed", "run_id": "run-1"}
    with harness("completed") as calls, \
         patch.object(worker.jobs, "load_check", lambda connection, check_id: dict(delivered)), \
         patch.object(worker.jobs, "replace_projection", lambda connection, **k: saved.append(k)):
        projection = worker.reproject_check("check-1", engine=Engine())
        assert calls["execute"] == [] and calls["created"] == []
    assert saved == [{"check_id": "check-1", "projection": projection}] and projection["valid_answers"] == 15
    with patch.object(worker.jobs, "load_check", lambda connection, check_id: {**CHECK, "status": "queued", "run_id": None}):
        with pytest.raises(ValueError, match="delivered"):
            worker.reproject_check("check-1", engine=Engine())


def test_wake_endpoint_answers_but_does_no_work():
    import urllib.error
    import urllib.request
    with patch.object(worker, "process_one") as process_one:
        server = worker.start_wake_server(0)
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            for path in ("/health", "/wake", "/"):
                with urllib.request.urlopen(base + path, timeout=5) as response:
                    assert response.status == 200 and response.read() == b"ok\n"
            request = urllib.request.Request(base + "/wake", data=b"{}", method="POST")
            with urllib.request.urlopen(request, timeout=5) as response:
                assert response.status == 200
            with pytest.raises(urllib.error.HTTPError) as missing:
                urllib.request.urlopen(base + "/admin", timeout=5)
            assert missing.value.code == 404
        finally:
            server.shutdown()
            server.server_close()
        process_one.assert_not_called()


# ---- confirmed listing ("Is this you?") ----------------------------------------------------------

def test_confirmed_listing_is_measured_under_its_listed_name_and_recorded_as_the_owners_claim():
    claimed = {**CHECK, "business_name": "Synthetic Bistro", "claimed_google_place_id": "place-7"}
    listing = {"business_name": "The Synthetic Bistro & Bar", "primary_group": "restaurants"}
    with harness("completed", check=claimed, listing=listing) as calls:
        assert worker.run_job(job(), settings=SETTINGS, worker_id="w", engine=Engine()) == "completed"
    created = calls["created"][0]
    assert created["target_google_place_id"] == "place-7" and created["target_resolution_status"] == "owner_confirmed"
    assert created["target_dataset_match_name"] == "The Synthetic Bistro & Bar"
    assert created["target_business_name"] == "Synthetic Bistro", "the owner's own wording is kept on the run"
    assert created["primary_group"] == "restaurants" and created["panel_kind"] == "free_check"
    executed = calls["execute"][0]
    assert executed["target_google_place_id"] == "place-7"
    assert executed["known_businesses"] == [{"google_place_id": "place-7", "business_name": "The Synthetic Bistro & Bar"}]


def test_listing_that_no_longer_exists_falls_back_to_the_typed_business():
    claimed = {**CHECK, "claimed_google_place_id": "gone"}
    with harness("completed", check=claimed, listing=None) as calls:
        worker.run_job(job(), settings=SETTINGS, worker_id="w", engine=Engine())
    created = calls["created"][0]
    assert created["target_google_place_id"] is None and created["target_resolution_status"] == "unresolved"


def test_directory_adds_a_stub_only_for_a_business_without_a_listing():
    class Rows:
        def mappings(self): return self
        def all(self): return [{"google_place_id": "place-7", "business_name": "Listed", "primary_group": "x", "business_format": None}]

    class Connection:
        def execute(self, statement): return Rows()
        def __enter__(self): return self
        def __exit__(self, *a): return False

    class ReadEngine:
        def connect(self): return Connection()

    assert list(worker._directory(ReadEngine(), "place-7", "Typed")["google_place_id"]) == ["place-7"]
    assert list(worker._directory(ReadEngine(), "discovery:r", "Typed")["business_name"]) == ["Listed", "Typed"]


# ---- results-ready email -------------------------------------------------------------------------

from src import free_check_email as mail  # noqa: E402


def sample_projection(recommended=4, valid=15):
    return {"valid_answers": valid, "expected_answers": 15, "target": {"recommended_answers": recommended}}


def test_results_email_states_the_saved_count_and_nothing_it_was_not_given():
    message = mail.build_results_email(business_name="  Fish &  <Chips>  ", projection=sample_projection(),
                                       site_url="https://example.org")
    assert message["subject"] == "Your AI visibility check for Fish & <Chips> is ready"
    assert "Fish & <Chips> was recommended in 4 of 15 answers." in message["text"]
    assert "Fish &amp; &lt;Chips&gt; was recommended in 4 of 15 answers." in message["html"]
    assert "<Chips>" not in message["html"], "owner text is escaped in the HTML"
    assert 'href="https://example.org/visibility-check"' in message["html"]
    assert "could not be collected" not in message["text"] and "do not send marketing" in message["text"]
    none = mail.build_results_email(business_name="Quiet Cafe", projection=sample_projection(0, 12),
                                    site_url="https://example.org")
    assert "Quiet Cafe was not recommended in the 12 completed answers." in none["text"]
    assert "3 of 15 answers could not be collected and are left out." in none["text"]


def test_results_email_names_the_number_of_questions_the_check_asked():
    def text(questions):
        projection = {**sample_projection(), "questions": [{"order": n} for n in range(1, questions + 1)]}
        return mail.build_results_email(business_name="Quiet Cafe", projection=projection,
                                        site_url="https://example.org")["text"]
    assert "a snapshot of three customer questions put to three AI providers" in text(3)
    assert "a snapshot of five customer questions put to three AI providers" in text(5)
    assert "a snapshot of customer questions put to three AI providers" in text(0)


def test_a_three_question_check_expects_nine_answers():
    results = [result(q["id"], p) for q in QUERIES[:3] for p in PROVIDERS]
    out = build_projection(business_name="Synthetic Bistro", questions=QUESTIONS[:3], providers=PROVIDERS,
                           queries=QUERIES[:3], results=results, recommendations=[], target_id=TARGET,
                           measured_at="2026-10-07T12:00:00+00:00", benchmark_mode="search_grounded")
    assert (out["expected_answers"], len(out["cells"]), len(out["questions"])) == (9, 9, 3)
    assert all(p["expected"] == 3 for p in out["providers"])


def test_email_is_off_unless_both_the_key_and_the_sender_are_set():
    assert mail.email_settings({}) is None
    assert mail.email_settings({"RESEND_API_KEY": "k"}) is None
    assert mail.email_settings({"FREE_CHECK_EMAIL_FROM": "a@b.co"}) is None
    assert mail.email_settings({"RESEND_API_KEY": "k", "FREE_CHECK_EMAIL_FROM": "a@b.co",
                                "FREE_CHECK_SITE_URL": "https://site.example/"}) == {
        "api_key": "k", "sender": "a@b.co", "site_url": "https://site.example"}
    settings = worker.load_settings({"OPENAI_API_KEY": "a", "ANTHROPIC_API_KEY": "b", "GEMINI_API_KEY": "c"})
    assert settings["email"] is None


def test_send_posts_once_to_resend_and_never_raises():
    import io
    import json
    import urllib.error
    sent = []

    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def opener(request, timeout):
        sent.append(request)
        return Response()

    assert mail.send_results_email(to="owner@example.org", business_name="Cafe", projection=sample_projection(),
                                   settings=EMAIL, opener=opener) is True
    request = sent[0]
    body = json.loads(request.data)
    assert request.full_url == mail.RESEND_URL and request.get_header("Authorization") == "Bearer synthetic-key"
    assert body["to"] == ["owner@example.org"] and body["from"] == EMAIL["sender"] and len(sent) == 1

    def rejected(request, timeout):
        raise urllib.error.HTTPError(mail.RESEND_URL, 422, "bad", {}, io.BytesIO(b"{}"))

    def broken(request, timeout):
        raise TimeoutError("slow")

    for failing in (rejected, broken):
        assert mail.send_results_email(to="owner@example.org", business_name="Cafe", projection=sample_projection(),
                                       settings=EMAIL, opener=failing) is False


def test_owner_is_emailed_once_after_delivery_and_a_failed_email_does_not_fail_the_check():
    with harness("completed") as calls:
        assert worker.run_job(job(), settings={**SETTINGS, "email": EMAIL}, worker_id="w", engine=Engine()) == "completed"
    assert len(calls["emails"]) == 1 and len(calls["complete"]) == 1
    email = calls["emails"][0]
    assert email["to"] == "owner@example.org" and email["settings"] == EMAIL
    assert email["projection"] is calls["complete"][0]["projection"]

    with harness("completed") as calls:  # email switched off
        worker.run_job(job(), settings=SETTINGS, worker_id="w", engine=Engine())
    assert calls["emails"] == [] and len(calls["complete"]) == 1

    with harness("partial") as calls:  # not delivered yet, so nothing to announce
        assert worker.run_job(job(attempt_count=1), settings={**SETTINGS, "email": EMAIL}, worker_id="w", engine=Engine()) == "retry"
    assert calls["emails"] == []

    with harness("completed") as calls, patch.object(worker, "send_results_email", side_effect=RuntimeError("boom")):
        assert worker.run_job(job(), settings={**SETTINGS, "email": EMAIL}, worker_id="w", engine=Engine()) == "completed"
    assert len(calls["complete"]) == 1


def test_reprojecting_a_summary_never_emails_the_owner():
    delivered = {**CHECK, "status": "completed", "run_id": "run-1"}
    with harness("completed") as calls, \
         patch.object(worker.jobs, "load_check", lambda connection, check_id: dict(delivered)), \
         patch.object(worker.jobs, "replace_projection", lambda connection, **k: None):
        worker.reproject_check("check-1", engine=Engine())
    assert calls["emails"] == []
