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


def run_page(audit, *, extra=()):
    """Return an AppTest that has run the page against the stubbed data layer."""
    stack = ExitStack()
    saved = mock.Mock(return_value={"revision": 4})
    patches = [
        mock.patch("src.database.get_engine", return_value=_Engine()),
        mock.patch("src.report_audit_repository.get_latest_report_audit", return_value=audit),
        mock.patch("src.report_audit_candidates.load_report_candidates", return_value=CANDIDATES),
        mock.patch("src.report_audit_repository.save_reviewer_decisions_revision", saved),
        *extra,
    ]
    for patch in patches:
        stack.enter_context(patch)
    at = AppTest.from_file(PAGE, default_timeout=60)
    at.secrets["TEST_ONLY_PLACEHOLDER"] = "unused"  # tests must not depend on a local secrets.toml
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
        assert saved.call_args.kwargs["complete"] is True


def test_a_draft_can_be_saved_with_choices_still_open():
    at, saved, stack = run_page(revision())
    with stack:
        button(at, "Save review draft").click().run()
        assert not at.exception, [e.value for e in at.exception]
        saved.assert_called_once()
        assert saved.call_args.kwargs["complete"] is False


def test_comparison_evidence_panel_lists_every_business_and_offers_missing_website_checks():
    at, _, stack = run_page(revision())
    with stack:
        assert not at.exception, [e.value for e in at.exception]
        labels = [b.label for b in at.button]
        assert "Open review tools for these businesses" in labels
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
    at, _, stack = run_page(revision(), extra=extra)
    with stack:
        button(at, "Review the website of Runway East Brighton | Office Space").click().run()
        assert not at.exception, [e.value for e in at.exception]
        crawler.assert_called_once()
        assert crawler.call_args.kwargs["audit_run_id"] == "run-1"


COMPLETE = {
    "confirmed_target_names": ["WRAP"], "rejected_target_names": [],
    "question_priority_map": {str(i): p for i, p in enumerate(
        ["Co-working", "Private offices", "Meeting rooms", "Event space", "Co-working", "Team away days", "Children’s parties"], 1)},
    "cohort_place_ids": ["place-plusx", "place-runway"],
    "name_links": {"place-plusx": {"rejected": ["Plus X Innovation Hub"]}},
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
        assert "Build: Accessible AI Report Generator v3.2.0" in captions


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


def decide_everything(at):
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
    at, _, stack = run_page(revision())
    with stack:
        assert not at.exception, [e.value for e in at.exception]
        table = next(df for df in at.dataframe if "Google reports" in df.value.columns)
        assert list(table.value["Google reports"]) and "Review text saved" in table.value.columns
        captions = " ".join(c.value for c in at.caption)
        assert "They do not affect the AI visibility counts" in captions
        assert "the AI platforms answer without reading reviews" in captions
