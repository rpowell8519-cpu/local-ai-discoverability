from io import BytesIO

import pytest
from pypdf import PdfReader

from src.client_summary import metrics
from src.client_summary.actions import (
    DONE_LIMIT, OWNER_LIMIT, TASK_LIMIT, TITLE_LIMIT, build_actions, profile_for,
)
from src.client_summary.adapter import (
    ClientSummaryError, build_client_summary_report, render_client_summary_pdf,
)
from src.owner_services_report import build_owner_report
from src.owner_services_synthetic import synthetic_owner_services_payload


@pytest.fixture
def payload():
    return synthetic_owner_services_payload()


def summary(payload, **kwargs):
    return build_client_summary_report(payload, business_group="hair_beauty", location="Exampletown", **kwargs)


def test_summary_and_full_report_agree_on_every_count(payload):
    report, data = build_owner_report(payload), summary(payload)
    result = metrics(data)
    assert (result["appearances"], result["complete"]) == (report["appearances"], report["answers"]) == (12, 24)
    assert [(q["appearances"], q["complete"]) for q in data["questions"]] == [
        (q["appearances"], q["answers"]) for q in report["questions"]
    ]
    by_provider = {p["name"]: (p["appearances"], p["complete"]) for p in data["providers"]}
    assert by_provider == {p["name"]: (p["appearances"], p["answers"]) for p in report["provider_counts"]}


def test_renders_six_pages_with_the_measured_result(payload):
    reader = PdfReader(BytesIO(render_client_summary_pdf(summary(payload))))
    assert len(reader.pages) == 6
    assert "12 of 24" in "\n".join(page.extract_text() for page in reader.pages)


def test_question_labels_use_the_owner_priority_they_test(payload):
    labels = [q["label"] for q in summary(payload)["questions"]]
    assert labels == ["Colour / balayage (Q1)", "Colour / balayage (Q2)", "Curly cuts", "Bridal hair"]


def test_unlinked_questions_fall_back_to_their_own_wording(payload):
    payload["report"]["owner_report"]["services"][0]["questions"] = None
    payload["report"]["owner_report"]["services"][1]["questions"] = None
    labels = [q["label"] for q in summary(payload)["questions"]]
    assert all(len(label) <= 65 for label in labels)
    assert not any("mapping not confirmed" in label for label in labels)


def test_incomplete_answers_stop_the_summary_with_a_clear_reason(payload):
    record = payload["baseline_validation"]["responses"][0]
    record.update(response_complete=False, status="failed", raw_response="")
    with pytest.raises(ClientSummaryError, match="incomplete or failed"):
        summary(payload)


def test_reviewer_titles_replace_action_titles_and_are_length_checked(payload):
    data = summary(payload, reviewer_action_titles=["Fix the booking page"])
    assert data["actions"][0]["title"] == "Fix the booking page"
    assert data["actions"][1]["title"].startswith("Make ")


def test_confirmed_target_names_are_disclosed(payload):
    slot = next(s for s in payload["recommendation_market"]["slot_evidence"] if s["google_place_id"] == "synthetic-target")
    slot.update(resolution_method="reviewer_confirmed_target_name", source_raw_business_name="Example")
    assert any("“Example”" in item for item in summary(payload)["limitations"])


def test_owner_review_is_only_claimed_when_questions_are_the_owners(payload):
    assert summary(payload)["owner_reviewed_questions"] is False
    owner = [q["prompt"] for q in build_owner_report(payload)["questions"]]
    assert summary(payload, owner_questions=owner)["owner_reviewed_questions"] is True
    assert summary(payload, owner_questions=owner[:-1])["owner_reviewed_questions"] is False


def test_summary_is_read_only(payload):
    import copy
    before = copy.deepcopy(payload)
    summary(payload)
    assert payload == before


QUESTIONS = [
    {"id": "q1", "label": "L" * 65, "appearances": 0, "answers": 9},
    {"id": "q2", "label": "Group bookings", "appearances": 3, "answers": 9},
    {"id": "q3", "label": "Garden seating", "appearances": 8, "answers": 9},
]


@pytest.mark.parametrize("group", ["pub", "salon", "cleaning_services", "coworking", "something_new", None])
def test_actions_fit_the_contract_for_every_business_type(group):
    actions = build_actions(QUESTIONS, business_group=group)
    assert len(actions) == 3 and {a["status"] for a in actions} == {"suggested_check"}
    for action in actions:
        assert len(action["title"]) <= TITLE_LIMIT and len(action["task"]) <= TASK_LIMIT
        assert len(action["owner"]) <= OWNER_LIMIT and len(action["done_when"]) <= DONE_LIMIT
        assert action["evidence_ids"] == []


def test_weakest_topics_get_checks_and_the_strongest_gets_the_consistency_action():
    actions = build_actions(QUESTIONS, business_group="pub")
    assert [a["question_id"] for a in actions] == ["q1", "q2", "q3"]
    assert "consistent" in actions[2]["title"]
    assert actions[0]["title"] == "Make this topic easy to find and act on"  # label too long for a title


def test_business_type_changes_wording_not_structure():
    assert "TripAdvisor" in profile_for("pubs").platforms
    assert "Checkatrade" in profile_for("cleaning_services").platforms
    assert profile_for("unknown thing") == profile_for(None)


def test_summary_needs_two_questions_to_choose_actions():
    with pytest.raises(ValueError, match="at least two"):
        build_actions(QUESTIONS[:1])


def test_actions_make_no_uplift_promise():
    text = " ".join(a["task"] + a["done_when"] for a in build_actions(QUESTIONS)).casefold()
    assert not any(word in text for word in ("guarantee", "rank higher", "more customers", "increase your"))
