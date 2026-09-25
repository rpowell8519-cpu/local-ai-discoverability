"""Runs the real report-generator page with the database layer stubbed.

The page is executed by Streamlit's own test harness, so widget wiring, form gating and the
generate flow are exercised for real. Only data access is replaced, with WRAP-shaped data:
a target whose AI answers used a shorter name, seven questions tied to six owner priorities,
and comparison businesses. No network, no paid calls, no database.
"""
from __future__ import annotations

import datetime as dt
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from src.owner_services_synthetic import synthetic_owner_services_payload  # noqa: E402
from src.site_checks import CrawlerAccess  # noqa: E402
from tests.test_found_brighton_report import measured_report  # noqa: E402

PAGE = str(Path(__file__).resolve().parents[1] / "app" / "pages" / "10_AI_Report_Generator.py")
TARGET_ID = "place-wrap"
RUN_ID = "11111111-1111-1111-1111-111111111111"
TARGET_NAME = "WRAP- Coworking, Meeting Rooms & Offices"
PRIORITIES = ["Co-working", "Private offices", "Meeting rooms", "Event space", "Team away days", "Children’s parties"]
QUESTIONS = [
    "Best co working hub in Brighton",
    "Recommend private offices in Brighton",
    "Good places to book meeting rooms in Brighton",
    "Places to host corporate events in Brighton",
    "Where can i rent a dedicated working space in Brighton",
    "Where can i arrange a team away day in Brighton?",
    "Where can i host a childrens party in Brighton?",
]
BUSINESSES = [
    (TARGET_ID, TARGET_NAME, "https://wrap.example"),
    ("place-plusx", "Plus X Innovation Brighton", ""),
    ("place-runway", "Runway East Brighton | Office Space", "https://runway.example"),
    ("place-skiff", "The Skiff", ""),
    ("place-platf9rm", "PLATF9RM Brighton - Coworking, Offices & Events", ""),
    ("place-freedom", "Freedom Works - The Palace Workspace", ""),
]


class _Result:
    def __init__(self, rows=None, scalar=None):
        self.rows, self.scalar = list(rows or []), scalar

    def mappings(self):
        return self

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None

    def scalar_one(self):
        return self.scalar


class _Connection:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, statement, params=None):
        sql = " ".join(str(statement).lower().split())
        if "from business_features bf" in sql and "lateral" in sql:
            return _Result(
                {
                    "google_place_id": pid, "business_name": name, "raw_category": "Coworking space",
                    "raw_type": "Coworking space", "primary_group": "coworking", "business_format": "",
                    "city": "Brighton", "address": "1 Test Street, Brighton",
                    "latitude": 50.8225, "longitude": -0.1372, "source_website_url": site,
                }
                for pid, name, site in BUSINESSES
            )
        if "from ai_visibility_runs" in sql:
            return _Result(
                [{"id": RUN_ID, "started_at": dt.datetime(2026, 9, 21), "completed_at": dt.datetime(2026, 9, 21),
                  "prompt_count": 7, "repeat_count": 3}]
            )
        if "from website_audit_runs" in sql:
            return _Result([])
        if "from business_reviews" in sql and "count(*)" in sql:
            return _Result(scalar=100 if (params or {}).get("google_place_id") == TARGET_ID else 0)
        if "from business_reviews" in sql:
            return _Result([])
        if "from ai_visibility_queries" in sql:
            return _Result(
                {"base_prompt_order": i, "prompt_category": "Owner priority", "prompt_source": "owner_brief", "prompt_text": q}
                for i, q in enumerate(QUESTIONS, 1)
            )
        if "report_audit_revisions" in sql:
            return _Result(scalar=False)
        raise AssertionError(f"Unexpected query in the page under test: {sql[:120]}")


class _Engine:
    def connect(self):
        return _Connection()


def revision(decisions=None, complete=False, owners=()):
    return {
        "id": "rev-uuid", "revision": 3, "target_google_place_id": TARGET_ID, "target_business_name": TARGET_NAME,
        "known_for": "A friendly co-working space in Brighton for freelancers and teams",
        "desired_searches": QUESTIONS, "owner_competitors": list(owners), "benchmark_run_id": RUN_ID,
        "website_evidence_state": "not_checked", "review_evidence_state": "not_checked",
        "reviewer_decisions": decisions or {}, "reviewer_decisions_complete": complete,
        "owner_context": {"priority_services": PRIORITIES, "service_areas": ["Brighton and Hove"]},
        "manual_website_url": "https://wrap.example",
    }


CANDIDATES = {
    "target": [],
    "verified": [
        {"google_place_id": pid, "business_name": name, "recommendations": count, "city": "Brighton",
         "address": "x", "latitude": 50.83, "longitude": -0.14, "primary_group": "coworking", "business_format": ""}
        for pid, name, count in (("place-plusx", "Plus X Innovation Brighton", 23),
                                 ("place-runway", "Runway East Brighton | Office Space", 14),
                                 ("place-skiff", "The Skiff", 8))
    ],
    "unresolved": [
        {"business_name": "PLATF9RM", "recommendations": 20},
        {"business_name": "WRAP", "recommendations": 12},
        {"business_name": "Plus X Innovation Hub", "recommendations": 7},
        {"business_name": "Hotel Pelirocco", "recommendations": 5},
    ],
}


def run_page(audit, *, extra=(), secrets=None):
    """Return an AppTest that has run the page against the stubbed data layer."""
    import streamlit as st
    st.cache_data.clear()  # @st.cache_data persists across AppTest runs in one process; each test starts clean
    stack = ExitStack()
    saved = mock.Mock(return_value={"revision": 4})
    patches = [
        mock.patch("src.database.get_engine", return_value=_Engine()),
        mock.patch("src.report_audit_repository.get_latest_report_audit", return_value=audit),
        mock.patch("src.report_audit_repository.list_report_audit_revisions", return_value=[audit] if audit else []),
        mock.patch("src.report_audit_candidates.load_report_candidates", return_value=CANDIDATES),
        mock.patch("src.report_audit_repository.save_reviewer_decisions_revision", saved),
        *extra,
    ]
    for patch in patches:
        stack.enter_context(patch)
    at = AppTest.from_file(PAGE, default_timeout=60)
    at.secrets["TEST_ONLY_PLACEHOLDER"] = "unused"  # tests must not depend on a local secrets.toml
    for key, value in (secrets or {}).items():
        at.secrets[key] = value
    at.session_state["active_report_project_place_id"] = TARGET_ID
    at.run()
    return at, saved, stack


def button(at, label):
    return next(b for b in at.button if b.label == label)


def test_review_step_flags_the_short_name_and_pre_links_questions():
    at, _, stack = run_page(revision())
    with stack:
        assert not at.exception, [e.value for e in at.exception]
        radios = {r.key: r for r in at.radio if str(r.key).startswith("target_name_choice_")}
        assert len(radios) == 1  # only WRAP looks like the target; PLATF9RM and the hotel do not
        only = next(iter(radios.values()))
        assert "“WRAP” — named in 12 answer(s)" in only.label and only.value == "undecided"
        boxes = {s.key: s for s in at.selectbox if str(s.key).startswith("question_priority_")}
        assert len(boxes) == 7
        assert boxes[f"question_priority_{TARGET_ID}_1"].value == "Co-working"
        assert boxes[f"question_priority_{TARGET_ID}_7"].value == "Children’s parties"
        assert boxes[f"question_priority_{TARGET_ID}_5"].value == ""  # ambiguous, left for the reviewer


def test_the_review_cannot_be_completed_with_undecided_names_or_unlinked_questions():
    at, saved, stack = run_page(revision())
    with stack:
        button(at, "Complete report review").click().run()
        assert not at.exception, [e.value for e in at.exception]
        message = " ".join(e.value for e in at.error)
        assert "“WRAP”" in message and "Q5" in message and "have not been saved" in message
        saved.assert_not_called()


def test_decisions_are_saved_once_every_choice_is_made():
    at, saved, stack = run_page(revision())
    with stack:
        waive_missing_evidence(at)
        next(r for r in at.radio if str(r.key).startswith("target_name_choice_")).set_value("yes")
        for other in at.radio:
            if "name_choice" in str(other.key) and not str(other.key).startswith("target_"):
                other.set_value("no")
        next(s for s in at.selectbox if s.key == f"question_priority_{TARGET_ID}_5").set_value("Private offices")
        at.run()
        button(at, "Complete report review").click().run()
        assert not at.exception, [e.value for e in at.exception]
        saved.assert_called_once()
        decisions = saved.call_args.kwargs["reviewer_decisions"]
        assert decisions["confirmed_target_names"] == ["WRAP"] and decisions["rejected_target_names"] == []
        assert decisions["question_priority_map"]["1"] == "Co-working"
        assert decisions["question_priority_map"]["5"] == "Private offices"
        assert len(decisions["question_priority_map"]) == 7
        # Names were still open, so this first save cannot complete the review: the most visible businesses are not known yet.
        assert saved.call_args.kwargs["complete"] is False


def test_a_draft_can_be_saved_with_choices_still_open():
    at, saved, stack = run_page(revision())
    with stack:
        button(at, "Save review draft").click().run()
        assert not at.exception, [e.value for e in at.exception]
        saved.assert_called_once()
        assert saved.call_args.kwargs["complete"] is False


def test_comparison_evidence_panel_lists_every_business_and_offers_missing_website_checks():
    at, _, stack = run_page(revision(NAMES_DECIDED))
    with stack:
        assert not at.exception, [e.value for e in at.exception]
        labels = [b.label for b in at.button]
        assert any(str(b.key) == "open_review_tools_for_comparison" for b in at.button)  # the advanced tools stay available
        # Only Runway East has a saved website, so only it gets a crawl button.
        crawl = [label for label in labels if label.startswith("Review the website of")]
        assert crawl == ["Review the website of Runway East Brighton | Office Space"]


def test_a_comparison_website_review_is_started_for_the_right_business():
    crawler = mock.Mock()
    extra = [
        mock.patch("src.website_audit_repository.create_audit_run", return_value="run-1"),
        mock.patch("src.website_audit.audit_website", return_value=({"audit_status": "completed"}, [])),
        mock.patch("src.website_audit_repository.finish_audit_run", crawler),
    ]
    at, _, stack = run_page(revision(NAMES_DECIDED), extra=extra)
    with stack:
        button(at, "Review the website of Runway East Brighton | Office Space").click().run()
        assert not at.exception, [e.value for e in at.exception]
        crawler.assert_called_once()
        assert crawler.call_args.kwargs["audit_run_id"] == "run-1"


# Names and competitors decided, which is what makes the most visible businesses (and their evidence) known.
NAMES_DECIDED = {
    "confirmed_target_names": ["WRAP"], "rejected_target_names": [],
    "name_links": {"place-plusx": {"rejected": ["Plus X Innovation Hub"]}, "place-platf9rm": {"confirmed": ["PLATF9RM"]}},
}
COMPLETE = {
    "confirmed_target_names": ["WRAP"], "rejected_target_names": [],
    "question_priority_map": {str(i): p for i, p in enumerate(
        ["Co-working", "Private offices", "Meeting rooms", "Event space", "Co-working", "Team away days", "Children’s parties"], 1)},
    "cohort_place_ids": ["place-plusx", "place-runway"],
    "name_links": {"place-plusx": {"rejected": ["Plus X Innovation Hub"]}, "place-platf9rm": {"confirmed": ["PLATF9RM"]}},
    "evidence_waivers": {"website": "The client's website has no usable saved audit.", "reviews": "No review text saved."},
}


def _closed(observation_status):
    return CrawlerAccess(observation_status, (("OAI-SearchBot", "ChatGPT search"),) if observation_status == "blocked" else (),
                         "https://wrap.example/robots.txt", "2026-09-21", True)


def generate_summary(access):
    payload = synthetic_owner_services_payload()
    extra = [
        mock.patch("src.poc_audit_generic.assemble_generic_report_payload", return_value=payload),
        mock.patch("src.site_checks.check_ai_crawler_access", return_value=access),
    ]
    at, saved, stack = run_page(revision(COMPLETE, complete=True), extra=extra)
    return at, stack


def choose_summary(at):
    next(r for r in at.radio if str(r.key).startswith("report_kind_")).set_value("summary")
    at.run()


def test_the_client_summary_is_generated_and_offered_for_download():
    at, stack = generate_summary(_closed("open"))
    with stack:
        assert not at.exception, [e.value for e in at.exception]
        choose_summary(at)
        button(at, "Generate client summary from saved evidence").click().run()
        assert not at.exception, [e.value for e in at.exception]
        assert any("The client summary is ready." in s.value for s in at.success), [e.value for e in at.error]


def test_a_blocked_crawler_reaches_the_summary_without_breaking_the_page():
    at, stack = generate_summary(_closed("blocked"))
    with stack:
        choose_summary(at)
        button(at, "Generate client summary from saved evidence").click().run()
        assert not at.exception, [e.value for e in at.exception]
        assert any("The client summary is ready." in s.value for s in at.success), [e.value for e in at.error]


def test_the_full_report_option_is_still_the_default():
    at, stack = generate_summary(None)
    with stack:
        assert not at.exception, [e.value for e in at.exception]
        radio = next(r for r in at.radio if str(r.key).startswith("report_kind_"))
        assert radio.value == "full"
        assert "Generate report from saved evidence" in [b.label for b in at.button]


# ---------------------------------------------------------------- finding the business
SEARCH_BOX = "report_business_search_box"


def search(at, text):
    at.text_input(key=SEARCH_BOX).set_value(text).run()


def picker(at):
    return next(s for s in at.selectbox if str(s.label).startswith("Business"))


def test_with_no_search_every_business_is_offered_as_before():
    at, _, stack = run_page(revision())
    with stack:
        assert not at.exception, [e.value for e in at.exception]
        assert picker(at).label == "Business" and len(picker(at).options) == len(BUSINESSES)


def test_searching_narrows_the_picker_to_matching_businesses():
    at, _, stack = run_page(revision())
    with stack:
        search(at, "wrap")
        assert not at.exception, [e.value for e in at.exception]
        assert picker(at).label == "Business (1 found)" and len(picker(at).options) == 1
        assert any(s.value.startswith("1. Owner context") for s in at.subheader)  # the report is shown


def test_a_business_that_is_not_in_the_database_is_said_so_and_the_report_is_not_shown():
    at, _, stack = run_page(revision())
    with stack:
        search(at, "Definitely Not A Real Place")
        assert not at.exception, [e.value for e in at.exception]
        assert any("“Definitely Not A Real Place” is not in the business database yet." in w.value for w in at.warning)
        assert not any(s.value.startswith("1. Owner context") for s in at.subheader)
        labels = [b.label for b in at.button]
        assert "Open Data Admin to import it" in labels and "I've imported it: search again" in labels
        text = " ".join(m.value for m in at.markdown)
        assert "place_id" in text and "You do not need the full rebuild" in text
        assert at.session_state["report_business_search_memo"] == "Definitely Not A Real Place"


def test_a_typo_gets_a_suggestion_that_can_be_used():
    at, _, stack = run_page(revision())
    with stack:
        search(at, "Wrapp")
        assert not at.exception, [e.value for e in at.exception]
        suggestion = next(b for b in at.button if b.label.startswith("WRAP- Coworking"))
        suggestion.click().run()
        assert not at.exception, [e.value for e in at.exception]
        assert at.text_input(key=SEARCH_BOX).value == TARGET_NAME
        assert picker(at).label == "Business (1 found)"


def test_a_search_kept_while_in_data_admin_is_restored_on_return():
    stack = ExitStack()
    for patch in (
        mock.patch("src.database.get_engine", return_value=_Engine()),
        mock.patch("src.report_audit_repository.get_latest_report_audit", return_value=revision()),
        mock.patch("src.report_audit_repository.list_report_audit_revisions", return_value=[revision()]),
        mock.patch("src.report_audit_candidates.load_report_candidates", return_value=CANDIDATES),
    ):
        stack.enter_context(patch)
    with stack:
        at = AppTest.from_file(PAGE, default_timeout=60)
        at.secrets["TEST_ONLY_PLACEHOLDER"] = "unused"  # tests must not depend on a local secrets.toml
        at.session_state["report_business_search_memo"] = "The Skiff"
        at.run()
        assert not at.exception, [e.value for e in at.exception]
        assert at.text_input(key=SEARCH_BOX).value == "The Skiff"
        assert picker(at).label == "Business (1 found)"


def test_data_admin_offers_the_way_back_when_a_search_is_waiting():
    source = (Path(PAGE).parents[1] / "pages" / "4_Data_Admin.py").read_text()
    assert "st.session_state.get(REPORT_SEARCH_KEY)" in source


def test_the_console_clears_a_leftover_search_when_a_report_is_opened_or_started():
    source = (Path(PAGE).parents[1] / "streamlit_app.py").read_text()
    assert source.count("clear_business_search()") == 3  # definition call sites: open_report and the new-report button
    assert '"report_business_search_box"' in source


def test_the_full_report_is_given_the_same_robots_finding_as_the_summary():
    from types import SimpleNamespace

    reviewable = SimpleNamespace(
        definition=SimpleNamespace(key="generic_rev-uuid", pdf_filename="wrap.pdf"),
        pdf_bytes=b"%PDF-1.4", payload={"report": {}},
    )
    builder = mock.Mock(return_value=reviewable)
    extra = [
        mock.patch("src.poc_audit_generic.build_reviewable_generic_audit", builder),
        mock.patch("src.site_checks.check_ai_crawler_access", return_value=_closed("blocked")),
    ]
    at, _, stack = run_page(revision(COMPLETE, complete=True), extra=extra)
    with stack:
        button(at, "Generate report from saved evidence").click().run()
        assert not at.exception, [e.value for e in at.exception]
        builder.assert_called_once()
        findings = builder.call_args.kwargs["site_findings"]
        assert [f["kind"] for f in findings] == ["crawler_access"] and findings[0]["gap"] is True
        assert any("The reviewable PDF is ready." in s.value for s in at.success)


def test_the_summary_is_marked_draft_by_default_and_the_switch_is_passed_through():
    captured = {}
    real = __import__("src.client_summary.adapter", fromlist=["build_client_summary_report"]).build_client_summary_report

    def spy(payload, **kwargs):
        captured.update(kwargs)
        return real(payload, **kwargs)

    at, stack = generate_summary(_closed("open"))
    with stack, mock.patch("src.client_summary.adapter.build_client_summary_report", spy):
        choose_summary(at)
        box = next(c for c in at.checkbox if str(c.key).startswith("summary_draft_"))
        assert box.value is True
        button(at, "Generate client summary from saved evidence").click().run()
        assert not at.exception, [e.value for e in at.exception]
        assert captured["draft"] is True
        box.uncheck().run()
        button(at, "Generate client summary from saved evidence").click().run()
        assert captured["draft"] is False


def test_the_build_label_changes_so_the_team_can_tell_which_version_is_live():
    at, _, stack = run_page(revision())
    with stack:
        captions = " ".join(c.value for c in at.caption)
        assert "Build: Accessible AI Report Generator v3.11.0" in captions


# ---------------------------------------------------------------- reviews saved before the new checks
OLD_REVIEW = {"cohort_place_ids": ["place-plusx", "place-runway"], "headline": "", "summary": ""}


def warnings_text(at):
    return " ".join(w.value for w in at.warning)


def test_a_review_completed_before_the_new_checks_is_flagged_up_front_and_generate_is_paused():
    at, _, stack = run_page(revision(OLD_REVIEW, complete=True))
    with stack:
        assert not at.exception, [e.value for e in at.exception]
        text = warnings_text(at)
        assert "completed before some checks existed" in text
        assert "“WRAP” (named in 12 answers)" in text and "Q1, Q2, Q3, Q4, Q5, Q6, Q7" in text
        assert "Generating is paused until the review in step 5 is updated" in text
        labels = [b.label for b in at.button]
        assert "Generate report from saved evidence" not in labels
        assert "Generate client summary from saved evidence" not in labels
        assert "Complete report review" in labels  # the way forward is right there


def test_completing_the_review_lifts_the_pause_without_reloading_anything_else():
    at, saved, stack = run_page(revision(OLD_REVIEW, complete=True))
    with stack:
        waive_missing_evidence(at)
        next(r for r in at.radio if str(r.key).startswith("target_name_choice_")).set_value("yes")
        for other in at.radio:
            if "name_choice" in str(other.key) and not str(other.key).startswith("target_"):
                other.set_value("no")
        for box in at.selectbox:
            if str(box.key).startswith("question_priority_") and box.value == "":
                box.set_value("Private offices")
        at.run()
        button(at, "Complete report review").click().run()
        assert not at.exception, [e.value for e in at.exception]
        saved.assert_called_once()  # the decisions were accepted and saved


def test_a_fully_decided_review_shows_no_notice_and_offers_generate():
    at, stack = generate_summary(_closed("open"))
    with stack:
        assert not at.exception, [e.value for e in at.exception]
        text = warnings_text(at)
        assert "completed before some checks existed" not in text and "Generating is paused" not in text
        assert "Generate report from saved evidence" in [b.label for b in at.button]


def test_rejecting_a_name_counts_as_a_decision():
    decisions = {**COMPLETE, "confirmed_target_names": [], "rejected_target_names": ["WRAP"]}
    at, _, stack = run_page(revision(decisions, complete=True))
    with stack:
        assert "Generating is paused" not in warnings_text(at)


def test_a_business_with_no_owner_priorities_is_never_asked_to_link_questions():
    audit = revision({**COMPLETE, "question_priority_map": {}}, complete=True)
    audit["owner_context"] = {"priority_services": [], "service_areas": ["Brighton and Hove"]}
    at, _, stack = run_page(audit)
    with stack:
        assert "link Q" not in warnings_text(at) and "Generating is paused" not in warnings_text(at)


def test_a_review_that_slips_through_gives_a_plain_message_not_a_traceback():
    from src.report_identity import UndecidedTargetNamesError

    boom = mock.Mock(side_effect=UndecidedTargetNamesError([{"name": "WRAP", "recommendations": 12}]))
    at, _, stack = run_page(
        revision(COMPLETE, complete=True),
        extra=[mock.patch("src.poc_audit_generic.build_reviewable_generic_audit", boom),
               mock.patch("src.site_checks.check_ai_crawler_access", return_value=None)],
    )
    with stack:
        button(at, "Generate report from saved evidence").click().run()
        assert not at.exception, [e.value for e in at.exception]
        assert "“WRAP” (12 answer(s))" in warnings_text(at)
        assert not at.error


def test_suggested_links_are_labelled_as_suggestions_and_saved_ones_are_not():
    at, _, stack = run_page(revision())
    with stack:
        box = next(s for s in at.selectbox if s.key == f"question_priority_{TARGET_ID}_1")
        assert "(suggested from the wording: please check)" in box.label
        unsuggested = next(s for s in at.selectbox if s.key == f"question_priority_{TARGET_ID}_5")
        assert "suggested" not in unsuggested.label  # nothing was suggested for the ambiguous question
    at, _, stack = run_page(revision({"question_priority_map": {"1": "Co-working"}}))
    with stack:
        box = next(s for s in at.selectbox if s.key == f"question_priority_{TARGET_ID}_1")
        assert "suggested" not in box.label  # a reviewer's saved choice is not a suggestion


def test_a_saved_link_the_wording_contradicts_is_flagged_for_a_second_look():
    # WRAP's saved review linked "co working" to the wrong priority; a saved choice must not hide that.
    saved = {"question_priority_map": {"1": "Meeting rooms", "2": "Private offices"}}
    at, _, stack = run_page(revision(saved))
    with stack:
        assert not at.exception, [e.value for e in at.exception]
        notes = " ".join(c.value for c in at.caption)
        assert "Check Q1: it is linked to “Meeting rooms”, but its wording fits “Co-working” better." in notes
        assert "Check Q2" not in notes  # a link that agrees with the wording is left alone


def test_a_saved_link_with_no_clear_better_suggestion_is_not_second_guessed():
    at, _, stack = run_page(revision({"question_priority_map": {"5": "Co-working"}}))
    with stack:  # Q5 is ambiguous, so nothing is suggested and the reviewer's choice stands
        assert "Check Q5" not in " ".join(c.value for c in at.caption)



# ---------------------------------------------------------------- the owner's competitors and other names
OWNERS = ("PLATF9RM", "Freedom Works", "PLUS X")


def owner_boxes(at):
    return {b.label.split("  (")[0]: b for b in at.selectbox if str(b.key).startswith("owner_place_")}


def test_each_owner_competitor_gets_a_database_match_choice_with_a_labelled_suggestion():
    at, _, stack = run_page(revision(owners=OWNERS))
    with stack:
        assert not at.exception, [e.value for e in at.exception]
        boxes = [b for b in at.selectbox if str(b.key).startswith("owner_place_")]
        assert len(boxes) == 3
        assert all("(suggested from the name: please check)" in b.label for b in boxes)
        chosen = sorted(b.value for b in boxes)
        assert chosen == ["place-freedom", "place-platf9rm", "place-plusx"]  # each owner name found its one clear match


def test_an_ai_name_identical_to_what_the_owner_typed_is_offered_for_a_decision():
    at, _, stack = run_page(revision(owners=OWNERS))
    with stack:
        labels = [r.label for r in at.radio if "name_choice" in str(r.key)]
        assert any("“PLATF9RM” — named in 20 answer(s). Same as the name the owner gave." in label for label in labels)
        assert any("“Plus X Innovation Hub” — named in 7 answer(s)" in label for label in labels)   # shares most words with Plus X


def test_the_review_cannot_be_completed_while_a_competitor_name_is_undecided():
    at, saved, stack = run_page(revision(owners=OWNERS))
    with stack:
        next(r for r in at.radio if str(r.key).startswith("target_name_choice_")).set_value("yes")
        for box in at.selectbox:
            if str(box.key).startswith("question_priority_") and box.value == "":
                box.set_value("Private offices")
        at.run()
        button(at, "Complete report review").click().run()
        assert not at.exception, [e.value for e in at.exception]
        assert "whether these AI answer names are the same business" in " ".join(e.value for e in at.error)
        saved.assert_not_called()


def waive_missing_evidence(at):
    for box in at.checkbox:
        if str(box.key).startswith("waive_"):
            box.set_value(True)


def decide_everything(at):
    waive_missing_evidence(at)
    for radio in at.radio:
        if str(radio.key).startswith("target_name_choice_") or "name_choice" in str(radio.key):
            radio.set_value("yes" if "PLATF9RM" in radio.label or "WRAP" in radio.label else "no")
    for box in at.selectbox:
        if str(box.key).startswith("question_priority_") and box.value == "":
            box.set_value("Private offices")
    at.run()


def test_the_matches_are_saved_against_the_right_businesses():
    at, saved, stack = run_page(revision(owners=OWNERS))
    with stack:
        decide_everything(at)
        button(at, "Complete report review").click().run()
        assert not at.exception, [e.value for e in at.exception]
        saved.assert_called_once()
        decisions = saved.call_args.kwargs["reviewer_decisions"]
        assert decisions["owner_competitor_places"] == {"PLATF9RM": "place-platf9rm", "Freedom Works": "place-freedom", "PLUS X": "place-plusx"}
        assert decisions["name_links"]["place-platf9rm"]["confirmed"] == ["PLATF9RM"]
        assert decisions["name_links"]["place-plusx"]["rejected"] == ["Plus X Innovation Hub"]
        assert decisions["confirmed_target_names"] == ["WRAP"]


def test_an_owner_competitor_can_be_marked_as_not_in_the_database():
    at, saved, stack = run_page(revision(owners=("Some Unlisted Rival",)))
    with stack:
        box = next(b for b in at.selectbox if str(b.key).startswith("owner_place_"))
        assert box.value == ""            # nothing similar, so nothing is suggested
        box.set_value("__none__")
        at.run()
        decide_everything(at)
        button(at, "Complete report review").click().run()
        decisions = saved.call_args.kwargs["reviewer_decisions"]
        assert decisions["owner_competitor_places"] == {"Some Unlisted Rival": ""}   # "" records: not in the database


def test_an_owner_competitor_left_unchosen_blocks_completion_and_names_it():
    at, saved, stack = run_page(revision(owners=("Some Unlisted Rival",)))
    with stack:
        decide_everything(at)
        button(at, "Complete report review").click().run()
        assert "which business in the database these owner competitors are: “Some Unlisted Rival”" in " ".join(e.value for e in at.error)
        saved.assert_not_called()


def test_an_owner_named_business_the_ai_never_recommended_is_offered_and_chosen_by_default():
    at, _, stack = run_page(revision(owners=OWNERS))
    with stack:
        multiselect = next(m for m in at.multiselect)
        offered = " | ".join(multiselect.options)
        assert "Freedom Works - The Palace Workspace — 0 recommendation(s)" in offered   # never recommended, but the owner named it
        chosen = list(multiselect.value)
        assert chosen[:3] == ["place-platf9rm", "place-freedom", "place-plusx"]   # the owner's businesses come first
        assert set(chosen[3:]) == {"place-runway", "place-skiff"}                  # then the most visible


def test_the_comparison_table_says_why_each_business_is_included():
    at, _, stack = run_page(revision(owners=OWNERS))
    with stack:
        table = next(df for df in at.dataframe if "Chosen because" in df.value.columns)
        reasons = dict(zip(table.value["Comparison business"], table.value["Chosen because"]))
        assert reasons["Freedom Works - The Palace Workspace"] == "Named by the owner"
        assert reasons["Runway East Brighton | Office Space"] == "Most visible in the AI answers"


def test_an_older_review_is_told_to_match_the_owners_competitors():
    at, _, stack = run_page(revision(OLD_REVIEW, complete=True, owners=OWNERS))
    with stack:
        assert not at.exception, [e.value for e in at.exception]
        text = warnings_text(at)
        assert "match the owner's competitor “PLATF9RM” to a business in the database" in text
        assert "Generating is paused" in text


# ---------------------------------------------------------------- reviews on the page
def test_the_evidence_panel_shows_googles_count_beside_what_was_saved_and_explains_what_reviews_do():
    at, _, stack = run_page(revision(NAMES_DECIDED))
    with stack:
        assert not at.exception, [e.value for e in at.exception]
        table = next(df for df in at.dataframe if "Google reports" in df.value.columns)
        assert list(table.value["Google reports"]) and "Review text saved" in table.value.columns
        captions = " ".join(c.value for c in at.caption)
        assert "They do not affect the AI visibility counts" in captions
        assert "the AI platforms answer without reading reviews" in captions


# ------------------------------------------------------------ recommendations from the evidence
def _real_fixture_analysis():
    from tests.test_evidence_recommendations_in_reports import analysis
    return analysis()


_FIXTURE_ANALYSIS = _real_fixture_analysis()  # computed with the real engine, before it is patched out


def _fixture_analysis(**_):
    return _FIXTURE_ANALYSIS


def rec_radios(at):
    return [r for r in at.radio if str(r.key).startswith("rec_choice_")]


def test_each_recommendation_is_offered_for_a_decision_with_editable_client_wording():
    at, saved, stack = run_page(revision({**OLD_REVIEW, **NAMES_DECIDED}, complete=True), extra=[mock.patch("src.evidence_analysis.analyse_evidence", _fixture_analysis)])
    with stack:
        assert not at.exception, [e.value for e in at.exception]
        radios = rec_radios(at)
        assert radios and all(r.value == "undecided" for r in radios)
        wording = [t for t in at.text_area if str(t.key).startswith("rec_wording_")]
        assert wording and all(len(t.value) <= 380 for t in wording)
        assert any("recommendation(s) from the evidence" in w.value for w in at.warning)


def test_the_review_cannot_be_completed_while_a_recommendation_is_undecided():
    at, saved, stack = run_page(revision(NAMES_DECIDED), extra=[mock.patch("src.evidence_analysis.analyse_evidence", _fixture_analysis)])
    with stack:
        decide_everything(at)
        button(at, "Complete report review").click().run()
        saved.assert_not_called()
        assert any("which recommendations from the evidence to include" in e.value for e in at.error)


def test_included_recommendations_are_saved_with_the_reviewers_wording_and_the_basis():
    at, saved, stack = run_page(revision(NAMES_DECIDED), extra=[mock.patch("src.evidence_analysis.analyse_evidence", _fixture_analysis)])
    with stack:
        decide_everything(at)
        radios = rec_radios(at)
        for radio in radios:
            radio.set_value("leave_out")
        radios[0].set_value("include")
        at.run()
        first_wording = next(t for t in at.text_area if str(t.key).startswith("rec_wording_"))
        first_wording.set_value("Our own wording for the client.")
        at.run()
        button(at, "Complete report review").click().run()
        assert not at.exception, [e.value for e in at.exception]
        decisions = saved.call_args.kwargs["reviewer_decisions"]
        assert set(decisions["recommendation_decisions"].values()) == {"include", "leave_out"}
        assert len(decisions["approved_recommendations"]) == 1
        assert decisions["approved_recommendations"][0]["action"] == "Our own wording for the client."
        assert decisions["recommendation_basis"]["layers"] and decisions["recommendation_basis"]["leaders"] is not None


def test_a_failed_comparison_is_said_plainly_and_does_not_break_the_page():
    def broken(**_):
        raise RuntimeError("boom")

    at, saved, stack = run_page(revision(NAMES_DECIDED), extra=[mock.patch("src.evidence_analysis.analyse_evidence", broken)])
    with stack:
        assert not at.exception, [e.value for e in at.exception]
        assert any("could not be run" in w.value for w in at.warning) and not rec_radios(at)


# ------------------------------------------------------------ collecting reviews in place
def test_without_an_outscraper_key_the_review_collection_says_so_and_offers_no_request():
    at, _, stack = run_page(revision())
    with stack:
        assert not at.exception, [e.value for e in at.exception]
        assert any("Outscraper is not connected" in i.value for i in at.info)
        assert not [b for b in at.button if str(b.key).startswith("collect_reviews_go_")]


def test_businesses_with_no_review_text_can_be_collected_in_one_request_with_the_cost_shown():
    submit = mock.Mock(return_value={"id": "req-1"})
    at, _, stack = run_page(revision(NAMES_DECIDED), secrets={"OUTSCRAPER_API_KEY": "test-key"},
                            extra=[mock.patch("src.outscraper_reviews.submit_google_reviews", submit)])
    with stack:
        assert not at.exception, [e.value for e in at.exception]
        box = next(m for m in at.multiselect if str(m.key).startswith("collect_review_places_"))
        assert TARGET_ID not in box.value and len(box.value) == 3  # the client already has reviews; the three most visible are offered
        assert "conservative estimated maximum cost" in " ".join(c.value for c in at.caption)
        next(b for b in at.button if str(b.key).startswith("collect_reviews_go_")).click().run()
        assert not at.exception, [e.value for e in at.exception]
        submit.assert_called_once()
        assert set(submit.call_args.kwargs["place_ids"]) == set(box.value) and submit.call_args.kwargs["api_key"] == "test-key"
        assert any("Review collection started" in s.value for s in at.success)


def test_a_finished_request_with_no_reviewable_text_says_so_plainly_and_stops_offering_to_check():
    # Regression: a business with a single star-only Google review (no text) never has anything to
    # import, but the check kept saying "not ready yet" as if it were still running.
    submit = mock.Mock(return_value={"id": "req-1"})
    checked = mock.Mock(return_value={"status": "Success", "data": []})
    at, _, stack = run_page(revision(NAMES_DECIDED), secrets={"OUTSCRAPER_API_KEY": "test-key"},
                            extra=[mock.patch("src.outscraper_reviews.submit_google_reviews", submit),
                                   mock.patch("src.outscraper_reviews.get_request_result", checked)])
    with stack:
        next(b for b in at.button if str(b.key).startswith("collect_reviews_go_")).click().run()
        next(b for b in at.button if str(b.key).startswith("collect_reviews_check_")).click().run()
        assert not at.exception, [e.value for e in at.exception]
        assert any("Outscraper finished, but returned no reviews with text" in w.value for w in at.warning)
        at.run()  # a fresh rerun, not another click: the popped session state should now stay popped
        assert not [b for b in at.button if str(b.key).startswith("collect_reviews_check_")]  # nothing left to check


def test_a_request_still_running_says_to_check_again_and_keeps_the_check_button():
    submit = mock.Mock(return_value={"id": "req-1"})
    checked = mock.Mock(return_value={"status": "Pending", "data": []})
    at, _, stack = run_page(revision(NAMES_DECIDED), secrets={"OUTSCRAPER_API_KEY": "test-key"},
                            extra=[mock.patch("src.outscraper_reviews.submit_google_reviews", submit),
                                   mock.patch("src.outscraper_reviews.get_request_result", checked)])
    with stack:
        next(b for b in at.button if str(b.key).startswith("collect_reviews_go_")).click().run()
        next(b for b in at.button if str(b.key).startswith("collect_reviews_check_")).click().run()
        assert not at.exception, [e.value for e in at.exception]
        assert any("check again in a moment" in i.value for i in at.info)
        assert [b for b in at.button if str(b.key).startswith("collect_reviews_check_")]  # still there to press again


def test_a_request_over_the_cost_ceiling_cannot_be_sent():
    at, _, stack = run_page(revision(NAMES_DECIDED), secrets={"OUTSCRAPER_API_KEY": "test-key"},
                            extra=[mock.patch("src.outscraper_reviews.review_pull_within_cost_ceiling", lambda **_: (False, 99.0))])
    with stack:
        assert next(b for b in at.button if str(b.key).startswith("collect_reviews_go_")).disabled
        assert "over the ceiling" in " ".join(c.value for c in at.caption)


def test_a_common_ai_name_that_is_a_listed_business_outside_the_comparison_is_put_to_the_reviewer():
    decisions = {**COMPLETE, "name_links": {"place-plusx": {"rejected": ["Plus X Innovation Hub"]}}}  # saved before this check existed
    at, saved, stack = run_page(revision(decisions, complete=True))
    with stack:
        assert not at.exception, [e.value for e in at.exception]
        text = warnings_text(at)
        assert "“PLATF9RM” (named in 20 answers)" in text and "Generating is paused" in text
        assert any("Is a name in the answers really PLATF9RM Brighton" in m.value for m in at.markdown)
        assert any("is in the database but is not in this comparison" in c.value for c in at.caption)


# ------------------------------------------------------------ wording for a kind of business with none of its own
SAUNA_WORDING = {
    "label": "sauna", "booking": "book a session or a private hire", "pricing": "session and group prices",
    "questions": "what to bring and age limits", "details": "opening times, session types and capacity",
    "review_themes": [{"label": "Heat", "category": "Experience", "terms": ["too hot", "lovely heat", "steam"]}],
    "site_checks": [{"label": "Gift vouchers", "page_terms": ["gift voucher", "gift card"], "url_terms": ["gift"]}],
}


def test_a_business_type_with_no_built_in_wording_offers_a_draft_and_never_calls_the_ai_unprompted():
    call = mock.Mock()
    at, _, stack = run_page(revision(), secrets={"ANTHROPIC_API_KEY": "k"}, extra=[mock.patch("src.type_wording.call_claude", call)])
    with stack:
        assert not at.exception, [e.value for e in at.exception]
        # The stub business is coworking, which has its own wording, so nothing is offered.
        assert not [b for b in at.button if str(b.key).startswith("type_wording_go_")]
        call.assert_not_called()


def test_a_reviewer_can_draft_check_and_save_wording_for_an_unknown_type():
    fake = mock.Mock(return_value=lambda system, prompt: __import__("json").dumps(SAUNA_WORDING))
    with mock.patch("src.client_summary.actions._GROUPS", {}):  # no type has built-in wording
        at, saved, stack = run_page(revision(), secrets={"ANTHROPIC_API_KEY": "k"}, extra=[mock.patch("src.type_wording.call_claude", fake)])
        with stack:
            assert not at.exception, [e.value for e in at.exception]
            next(b for b in at.button if str(b.key).startswith("type_wording_go_")).click().run()
            assert not at.exception, [e.value for e in at.exception]
            fake.assert_called_once()
            assert next(t for t in at.text_input if str(t.key).startswith("tw_booking_")).value == "book a session or a private hire"
            # The raw draft is saved right away, so a reload does not lose a paid call, but it is not "type_wording"
            # (what the report reads) until the reviewer actually saves it below.
            draft_save = saved.call_args.kwargs["reviewer_decisions"]
            assert "type_wording" not in draft_save and draft_save["type_wording_draft"]["booking"] == "book a session or a private hire"
            saved.reset_mock()
            next(b for b in at.button if str(b.key).startswith("type_wording_save_")).click().run()
            assert not at.exception, [e.value for e in at.exception]
            decisions = saved.call_args.kwargs["reviewer_decisions"]
            assert decisions["type_wording"]["booking"] == "book a session or a private hire" and saved.call_args.kwargs["complete"] is False
            assert decisions["type_wording"]["site_checks"][0]["page_terms"] == ["gift voucher", "gift card"]
            assert "type_wording_draft" not in decisions  # approved, so the pending copy is cleared


def test_a_reload_before_saving_does_not_lose_the_paid_draft():
    # The reviewer drafted with AI, then reloaded the browser before pressing "Save" (a fresh session:
    # st.session_state is gone, only what was persisted to the revision survives).
    with mock.patch("src.client_summary.actions._GROUPS", {}):
        at, saved, stack = run_page(revision({"type_wording_draft": SAUNA_WORDING}))
        with stack:
            assert not at.exception, [e.value for e in at.exception]
            assert any("A draft from before is shown below" in c.value for c in at.caption)
            assert next(t for t in at.text_input if str(t.key).startswith("tw_booking_")).value == "book a session or a private hire"
            next(b for b in at.button if str(b.key).startswith("type_wording_save_")).click().run()
            decisions = saved.call_args.kwargs["reviewer_decisions"]
            assert decisions["type_wording"]["booking"] == "book a session or a private hire" and "type_wording_draft" not in decisions


def test_going_back_to_general_wording_clears_a_pending_draft_too():
    with mock.patch("src.client_summary.actions._GROUPS", {}):
        at, saved, stack = run_page(revision({"type_wording": SAUNA_WORDING, "type_wording_draft": SAUNA_WORDING}))
        with stack:
            next(b for b in at.button if str(b.key).startswith("type_wording_clear_")).click().run()
            decisions = saved.call_args.kwargs["reviewer_decisions"]
            assert "type_wording" not in decisions and "type_wording_draft" not in decisions


def test_wording_that_breaks_the_rules_is_not_saved_and_the_reason_is_shown():
    with mock.patch("src.client_summary.actions._GROUPS", {}):
        at, saved, stack = run_page(revision(), secrets={"ANTHROPIC_API_KEY": "k"})
        with stack:
            next(t for t in at.text_input if str(t.key).startswith("tw_label_")).set_value("sauna")
            for prefix, value in (("tw_booking_", "book for £15"), ("tw_pricing_", "prices"), ("tw_questions_", "what to bring"), ("tw_details_", "opening times")):
                next(t for t in at.text_input if str(t.key).startswith(prefix)).set_value(value)
            next(b for b in at.button if str(b.key).startswith("type_wording_save_")).click().run()
            saved.assert_not_called()
            assert any("Not saved" in e.value and "£" in e.value for e in at.error)


def test_completing_the_review_keeps_saved_wording():
    with mock.patch("src.client_summary.actions._GROUPS", {}):
        at, saved, stack = run_page(revision({**COMPLETE, "type_wording": SAUNA_WORDING}, complete=False))
        with stack:
            decide_everything(at)
            button(at, "Complete report review").click().run()
            for radio in [r for r in at.radio if str(r.key).startswith("rec_choice_")]:
                radio.set_value("leave_out")
            at.run()
            button(at, "Complete report review").click().run()
            assert saved.call_args.kwargs["reviewer_decisions"]["type_wording"]["label"] == "sauna"


def test_the_report_types_offered_come_from_one_list_and_each_has_its_own_button():
    at, _, stack = run_page(revision(COMPLETE, complete=True))
    with stack:
        radio = next(r for r in at.radio if str(r.key).startswith("report_kind_"))
        assert list(radio.options) == [
            "Full evidence report (RP)",
            "Client summary (LS)",
            "AI Visibility Report (GSO)",
            "Found in Brighton AI Report",
        ] and radio.value == "full"
        assert "Generate report from saved evidence" in [b.label for b in at.button]
        radio.set_value("summary").run()
        assert "Generate client summary from saved evidence" in [b.label for b in at.button]
        assert "Generate report from saved evidence" not in [b.label for b in at.button]
        radio.set_value("gso").run()
        assert "Generate AI Visibility Report from saved scan" in [b.label for b in at.button]
        assert "Generate client summary from saved evidence" not in [b.label for b in at.button]
        radio.set_value("found_brighton").run()
        assert "Generate Found in Brighton report from saved scan" in [b.label for b in at.button]
        assert "Generate AI Visibility Report from saved scan" not in [b.label for b in at.button]


def test_found_brighton_report_is_built_from_the_selected_saved_run_without_rerunning_it():
    report = measured_report()
    builder = mock.Mock(return_value=report)
    renderer = mock.Mock(return_value=b"word document")
    extra = [
        mock.patch("src.ai_visibility_repository.get_visibility_run", return_value={"id": RUN_ID, "status": "completed"}),
        mock.patch("src.ai_visibility_repository.get_run_queries", return_value=[{"id": "query"}]),
        mock.patch("src.ai_visibility_repository.get_run_results", return_value=[{"id": "answer"}]),
        mock.patch("src.gso_report_adapter.build_gso_report_from_saved_run", builder),
        mock.patch("src.found_brighton_report.generate_filled_report", renderer),
    ]
    at, _, stack = run_page(revision(COMPLETE, complete=True), extra=extra)
    with stack:
        next(r for r in at.radio if str(r.key).startswith("report_kind_")).set_value("found_brighton")
        at.run()
        button(at, "Generate Found in Brighton report from saved scan").click().run()
        assert not at.exception, [e.value for e in at.exception]
        assert any("The Found in Brighton report is ready." in message.value for message in at.success)
        builder.assert_called_once()
        assert builder.call_args.kwargs["target_google_place_id"] == TARGET_ID
        renderer.assert_called_once_with(report, agency="Found in Brighton AI", website="https://wrap.example")


# ------------------------------------------------------------ website and review evidence are required, or knowingly waived
def test_a_review_cannot_be_completed_while_the_evidence_is_missing_and_not_waived():
    at, saved, stack = run_page(revision(NAMES_DECIDED))
    with stack:
        boxes = [b for b in at.checkbox if str(b.key).startswith("waive_")]
        assert {str(b.key).split("_")[1] for b in boxes} == {"website", "reviews"} and not any(b.value for b in boxes)
        decide_everything(at)
        for b in [b for b in at.checkbox if str(b.key).startswith("waive_")]:
            b.set_value(False)
        at.run()
        button(at, "Complete report review").click().run()
        saved.assert_not_called()
        assert any("the missing evidence" in e.value for e in at.error)


def test_waiving_the_missing_evidence_is_saved_with_the_reason_and_disclosed_later():
    at, saved, stack = run_page(revision(NAMES_DECIDED))
    with stack:
        decide_everything(at)
        button(at, "Complete report review").click().run()
        waivers = saved.call_args.kwargs["reviewer_decisions"]["evidence_waivers"]
        assert set(waivers) == {"website", "reviews"} and all(waivers.values())


def test_a_completed_review_with_no_waiver_and_no_evidence_is_paused_with_the_reason():
    decisions = {k: v for k, v in COMPLETE.items() if k != "evidence_waivers"}
    at, _, stack = run_page(revision(decisions, complete=True))
    with stack:
        text = warnings_text(at)
        assert "add the evidence for the website comparison (step 5, below the name matching), or accept going ahead without it" in text
        assert "Generating is paused" in text


def test_a_layer_that_has_its_evidence_is_never_asked_about():
    result = {"layers": {"website": {"status": "used", "note": "ok"}, "propositions": {"status": "used", "note": "ok"},
                         "reviews": {"status": "used", "note": "ok"}}, "leaders": [], "candidates": [], "strengths": [], "basis": ""}
    at, _, stack = run_page(revision(), extra=[mock.patch("src.evidence_analysis.analyse_evidence", lambda **_: result)])
    with stack:
        assert not [b for b in at.checkbox if str(b.key).startswith("waive_")]


# ------------------------------------------------------------ evidence only for the most visible businesses
MANY = {**CANDIDATES, "verified": [
    {"google_place_id": pid, "business_name": name, "recommendations": count, "city": "Brighton",
     "address": "x", "latitude": 50.83, "longitude": -0.14, "primary_group": "coworking", "business_format": ""}
    for pid, name, count in (("place-plusx", "Plus X Innovation Brighton", 23),
                             ("place-platf9rm", "PLATF9RM Brighton - Coworking, Offices & Events", 20),
                             ("place-runway", "Runway East Brighton | Office Space", 14),
                             ("place-skiff", "The Skiff", 8), ("place-freedom", "Freedom Works - The Palace Workspace", 5))]}
MANY_PATCH = lambda: mock.patch("src.report_audit_candidates.load_report_candidates", return_value=MANY)  # noqa: E731


def collect_options(at):
    return [m for m in at.multiselect if str(m.key).startswith("collect_review_places_")]


def test_until_the_names_are_matched_no_evidence_is_offered_because_the_most_visible_are_not_yet_known():
    at, saved, stack = run_page(revision(), secrets={"OUTSCRAPER_API_KEY": "k"})
    with stack:
        assert not at.exception, [e.value for e in at.exception]
        assert not collect_options(at) and not [s for s in at.slider if str(s.key).startswith("leader_count_")]
        assert any("Match the AI answer names" in i.value and "depends on those matches" in i.value for i in at.info)
        assert not [w for w in at.warning if "recommendation(s) from the evidence" in w.value]


def test_a_first_save_with_names_decided_saves_as_a_draft_and_says_what_comes_next():
    at, saved, stack = run_page(revision())
    with stack:
        decide_everything(at)
        button(at, "Complete report review").click().run()
        assert saved.call_args.kwargs["complete"] is False
        assert any("most visible businesses are now known" in i.value for i in at.info)


def test_once_names_are_decided_completing_the_review_completes_it():
    at, saved, stack = run_page(revision(NAMES_DECIDED))
    with stack:
        decide_everything(at)
        button(at, "Complete report review").click().run()
        assert saved.call_args.kwargs["complete"] is True


def test_only_the_most_visible_businesses_are_studied_and_the_reviewer_can_study_fewer():
    at, saved, stack = run_page(revision(NAMES_DECIDED), secrets={"OUTSCRAPER_API_KEY": "k"}, extra=[MANY_PATCH()])
    with stack:
        assert not at.exception, [e.value for e in at.exception]
        slider = next(s for s in at.slider if str(s.key).startswith("leader_count_"))
        assert (slider.min, slider.max, slider.value) == (3, 5, 5)
        assert len(collect_options(at)[0].value) == 5
        slider.set_value(3).run()
        assert not at.exception, [e.value for e in at.exception]
        assert collect_options(at)[0].value == ["place-plusx", "place-platf9rm", "place-runway"]   # not The Skiff, not Freedom Works
        table = next(df for df in at.dataframe if "Review text saved" in df.value.columns)
        assert len(table.value) == 4 and not any("Freedom" in b or "Skiff" in b for b in table.value["Business"])   # the client and three
        decide_everything(at)
        button(at, "Complete report review").click().run()
        assert saved.call_args.kwargs["reviewer_decisions"]["leader_count"] == 3


def test_a_business_the_ai_never_recommended_is_never_studied_however_the_owner_ranked_it():
    at, _, stack = run_page(revision({**NAMES_DECIDED, "owner_competitor_places": {"Freedom Works": "place-freedom"}}, owners=("Freedom Works",)))
    with stack:
        assert not at.exception, [e.value for e in at.exception]
        ids = [str(o) for o in collect_options(at)[0].options] if collect_options(at) else []
        assert not any("Freedom" in o for o in ids)


# ------------------------------------------------------------ a name that could be either of two businesses
WERKS_BUSINESSES = [*BUSINESSES, ("place-pierwerks", "Pier Werks", ""), ("place-werkscentral", "Werks Central", "")]


class _WerksConnection(_Connection):
    def execute(self, statement, params=None):
        sql = " ".join(str(statement).lower().split())
        if "from business_features bf" in sql and "lateral" in sql:
            return _Result(
                {
                    "google_place_id": pid, "business_name": name, "raw_category": "Coworking space",
                    "raw_type": "Coworking space", "primary_group": "coworking", "business_format": "",
                    "city": "Brighton", "address": "1 Test Street, Brighton",
                    "latitude": 50.8225, "longitude": -0.1372, "source_website_url": site,
                }
                for pid, name, site in WERKS_BUSINESSES
            )
        return super().execute(statement, params)


class _WerksEngine:
    def connect(self):
        return _WerksConnection()


WERKS_CANDIDATES = {**CANDIDATES, "unresolved": [{"business_name": "WERKS", "recommendations": 4}]}


def test_a_name_that_could_be_either_of_two_businesses_cannot_be_confirmed_for_both():
    # Regression: confirming "WERKS" for both Pier Werks and Werks Central only failed much later,
    # confusingly, when the PDF was generated ("WERKS is confirmed for two different businesses").
    at, saved, stack = run_page(revision(), extra=[
        mock.patch("src.database.get_engine", return_value=_WerksEngine()),
        mock.patch("src.report_audit_candidates.load_report_candidates", return_value=WERKS_CANDIDATES),
    ])
    with stack:
        assert not at.exception, [e.value for e in at.exception]
        waive_missing_evidence(at)
        for box in at.selectbox:
            if str(box.key).startswith("question_priority_") and box.value == "":
                box.set_value("Private offices")
        werks_radios = [r for r in at.radio if "name_choice" in str(r.key) and "WERKS" in r.label]
        assert len(werks_radios) == 2  # offered against both Pier Werks and Werks Central
        for radio in werks_radios:
            radio.set_value("yes")
        at.run()
        button(at, "Complete report review").click().run()
        assert not at.exception, [e.value for e in at.exception]
        saved.assert_not_called()
        message = next(e.value for e in at.error)
        assert "“WERKS” for Pier Werks and Werks Central" in message and "confirm at most one" in message


def test_confirming_it_for_only_one_of_the_two_completes_normally():
    at, saved, stack = run_page(revision(), extra=[
        mock.patch("src.database.get_engine", return_value=_WerksEngine()),
        mock.patch("src.report_audit_candidates.load_report_candidates", return_value=WERKS_CANDIDATES),
    ])
    with stack:
        waive_missing_evidence(at)
        for box in at.selectbox:
            if str(box.key).startswith("question_priority_") and box.value == "":
                box.set_value("Private offices")
        werks_radios = [r for r in at.radio if "name_choice" in str(r.key) and "WERKS" in r.label]
        werks_radios[0].set_value("yes")
        werks_radios[1].set_value("no")
        at.run()
        button(at, "Complete report review").click().run()
        assert not at.exception, [e.value for e in at.exception]
        saved.assert_called_once()
        links = saved.call_args.kwargs["reviewer_decisions"]["name_links"]
        confirmed = [key for key, entry in links.items() if "WERKS" in entry.get("confirmed", [])]
        assert confirmed == ["place-pierwerks"]


# ------------------------------------------------------------ switching between saved versions of a business
def test_with_only_one_saved_version_nothing_extra_is_offered():
    at, _, stack = run_page(revision(), extra=[
        mock.patch("src.report_audit_repository.list_report_audit_revisions", return_value=[revision()]),
    ])
    with stack:
        assert not at.exception, [e.value for e in at.exception]
        assert not any("Switch to a different saved version" in str(getattr(e, "label", "")) for e in at.expander)


NURSERY_HISTORY_ROW = {
    "id": "audit-nursery", "revision": 5, "target_google_place_id": TARGET_ID, "target_business_name": TARGET_NAME,
    "known_for": "On-site childcare and nursery places in Brighton", "revision_reason": "Owner brief updated",
    "reviewer_decisions_complete": False,
}


def test_an_earlier_saved_version_can_be_switched_to_and_back():
    current = revision()
    restore = mock.Mock(return_value={"revision": 6})
    at, saved, stack = run_page(current, extra=[
        mock.patch("src.report_audit_repository.list_report_audit_revisions", return_value=[current, NURSERY_HISTORY_ROW]),
        mock.patch("src.report_audit_repository.restore_report_audit_revision", restore),
    ])
    with stack:
        assert not at.exception, [e.value for e in at.exception]
        box = next(s for s in at.selectbox if str(s.key).startswith("revision_pick_"))
        assert box.value == 5
        [label] = box.options
        assert "On-site childcare and nursery places in Brighton" in label and "review not complete" in label
        next(b for b in at.button if str(b.key).startswith("revision_restore_")).click().run()
        assert not at.exception, [e.value for e in at.exception]
        restore.assert_called_once_with(TARGET_ID, 5)


def test_a_failed_switch_is_reported_plainly_and_nothing_else_changes():
    current = revision()
    restore = mock.Mock(side_effect=ValueError("Revision 5 was not found for this business."))
    at, saved, stack = run_page(current, extra=[
        mock.patch("src.report_audit_repository.list_report_audit_revisions", return_value=[current, NURSERY_HISTORY_ROW]),
        mock.patch("src.report_audit_repository.restore_report_audit_revision", restore),
    ])
    with stack:
        next(b for b in at.button if str(b.key).startswith("revision_restore_")).click().run()
        assert any("could not be restored" in e.value for e in at.error)  # st.exception(exc) also shows, deliberately
        saved.assert_not_called()


# ------------------------------------------------------------ reusing an already-completed AI Visibility run
EXTRA_RUN_ID = "22222222-2222-2222-2222-222222222222"


class _ExtraRunConnection(_Connection):
    def execute(self, statement, params=None):
        sql = " ".join(str(statement).lower().split())
        if "from ai_visibility_runs" in sql:
            return _Result([
                {"id": RUN_ID, "started_at": dt.datetime(2026, 9, 21), "completed_at": dt.datetime(2026, 9, 21),
                 "prompt_count": 7, "repeat_count": 3},
                {"id": EXTRA_RUN_ID, "started_at": dt.datetime(2026, 9, 22), "completed_at": dt.datetime(2026, 9, 22, 14, 30),
                 "prompt_count": 8, "repeat_count": 3},
            ])
        return super().execute(statement, params)


class _ExtraRunEngine:
    def connect(self):
        return _ExtraRunConnection()


def test_a_completed_run_not_attached_to_the_report_can_be_reused_free_of_charge():
    # The report's benchmark_run_id is None, so step 3 (paid) would normally show; a second, already-completed
    # run exists for this business (e.g. finished on the specialist page after a resume) and can be reused instead.
    attach = mock.Mock(return_value={"revision": 4})
    at, saved, stack = run_page({**revision(), "benchmark_run_id": None},
                                extra=[mock.patch("src.database.get_engine", return_value=_ExtraRunEngine()),
                                       mock.patch("src.report_audit_repository.attach_benchmark_revision", attach)])
    with stack:
        assert not at.exception, [e.value for e in at.exception]
        assert any("Use an already-completed AI Visibility run instead (2 available)" in str(e.label) for e in at.expander)
        box = next(s for s in at.selectbox if str(s.key).startswith("attach_run_pick_"))
        assert box.options == [
            "7 question(s) × 3 repeat(s), completed 21 Sep 2026 00:00",
            "8 question(s) × 3 repeat(s), completed 22 Sep 2026 14:30",
        ]
        box.set_value(EXTRA_RUN_ID)
        at.run()
        next(b for b in at.button if str(b.key).startswith("attach_run_go_")).click().run()
        assert not at.exception, [e.value for e in at.exception]
        attach.assert_called_once_with(target_google_place_id=TARGET_ID, benchmark_run_id=EXTRA_RUN_ID)


def test_with_nothing_else_to_reuse_the_control_is_not_offered():
    at, _, stack = run_page(revision())  # benchmark_run_id already matches the one completed run
    with stack:
        assert not at.exception, [e.value for e in at.exception]
        assert not any("Use an already-completed AI Visibility run instead" in str(e.label) for e in at.expander)


# ------------------------------------------------------------ adding a competitor mid-review, without a reset
def test_named_competitors_can_be_added_from_step_5_without_touching_anything_saved():
    save_competitors = mock.Mock(return_value={"revision": 20})
    at, saved, stack = run_page(revision(NAMES_DECIDED, owners=OWNERS), extra=[
        mock.patch("src.report_audit_repository.save_owner_competitors_revision", save_competitors),
    ])
    with stack:
        assert not at.exception, [e.value for e in at.exception]
        box = next(t for t in at.text_area if str(t.key).startswith("owner_competitors_edit_"))
        assert box.value == "PLATF9RM\nFreedom Works\nPLUS X"
        box.set_value("PLATF9RM\nFreedom Works\nPLUS X\nHopscotch\n\n  ")
        at.run()
        next(b for b in at.button if str(b.key).startswith("owner_competitors_save_")).click().run()
        assert not at.exception, [e.value for e in at.exception]
        save_competitors.assert_called_once_with(
            target_google_place_id=TARGET_ID, owner_competitors=["PLATF9RM", "Freedom Works", "PLUS X", "Hopscotch"],
        )
        saved.assert_not_called()  # this is a separate, smaller save, never the whole review


def test_with_no_owner_competitors_yet_the_box_to_add_them_is_open_by_default():
    at, _, stack = run_page(revision(NAMES_DECIDED))
    with stack:
        assert not at.exception, [e.value for e in at.exception]
        assert any("Competitors the owner named (0)" in str(e.label) for e in at.expander)
        box = next(t for t in at.text_area if str(t.key).startswith("owner_competitors_edit_"))
        assert box.value == ""


def test_a_failed_save_of_the_competitor_list_is_reported_plainly():
    at, saved, stack = run_page(revision(NAMES_DECIDED, owners=OWNERS), extra=[
        mock.patch("src.report_audit_repository.save_owner_competitors_revision",
                   mock.Mock(side_effect=ValueError("Submit the report owner brief before naming competitors."))),
    ])
    with stack:
        next(b for b in at.button if str(b.key).startswith("owner_competitors_save_")).click().run()
        assert any("could not be saved" in e.value for e in at.error)
