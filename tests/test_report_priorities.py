import pytest

from src.owner_services_report import build_owner_report
from src.owner_services_synthetic import synthetic_owner_services_payload
from src.report_priorities import (
    GENERAL_GROUP_NAME,
    NOT_LINKED,
    build_service_groups,
    suggest_priority,
    suggest_priority_map,
    undecided_questions,
)

PRIORITIES = ["Co-working", "Private offices", "Meeting rooms", "Event space", "Team away days", "Children’s parties"]
QUESTIONS = [
    {"base_prompt_order": 1, "prompt_text": "Best co working hub in Brighton"},
    {"base_prompt_order": 2, "prompt_text": "Recommend private offices in Brighton"},
    {"base_prompt_order": 3, "prompt_text": "Good places to book meeting rooms in Brighton"},
    {"base_prompt_order": 4, "prompt_text": "Places to host corporate events in Brighton"},
    {"base_prompt_order": 5, "prompt_text": "Where can i rent a dedicated working space in Brighton"},
    {"base_prompt_order": 6, "prompt_text": "Where can i arrange a team away day in Brighton?"},
    {"base_prompt_order": 7, "prompt_text": "Where can i host a childrens party in Brighton?"},
]


def test_clear_matches_are_suggested_and_plurals_and_hyphens_do_not_matter():
    suggested = suggest_priority_map(QUESTIONS, PRIORITIES)
    assert suggested["1"] == "Co-working"
    assert suggested["2"] == "Private offices"
    assert suggested["3"] == "Meeting rooms"
    assert suggested["4"] == "Event space"
    assert suggested["6"] == "Team away days"
    assert suggested["7"] == "Children’s parties"


def test_an_ambiguous_question_is_left_for_the_reviewer():
    # "working space" overlaps Co-working and Event space equally.
    assert suggest_priority("Where can i rent a dedicated working space in Brighton", PRIORITIES) is None
    assert "5" not in suggest_priority_map(QUESTIONS, PRIORITIES)


def test_a_question_with_no_shared_wording_gets_no_suggestion():
    assert suggest_priority("Best fish and chips near the pier", PRIORITIES) is None


def test_undecided_questions_need_a_valid_priority_or_not_linked():
    decided = {"1": "Co-working", "2": NOT_LINKED, "3": "Not a real priority"}
    assert undecided_questions(QUESTIONS, PRIORITIES, decided) == [3, 4, 5, 6, 7]


def test_service_groups_list_every_priority_and_never_share_a_question():
    groups = build_service_groups(
        PRIORITIES,
        {"1": "Co-working", "2": "Private offices", "3": "Meeting rooms", "4": "Event space",
         "5": "Co-working", "6": "Team away days", "7": NOT_LINKED},
    )
    by_name = {group["name"]: group["questions"] for group in groups}
    assert by_name["Co-working"] == [1, 5]
    assert by_name["Children’s parties"] == []
    assert by_name[GENERAL_GROUP_NAME] == [7]
    linked = [order for group in groups for order in group["questions"]]
    assert len(linked) == len(set(linked)) == 7


def test_linked_questions_replace_coverage_not_mapped_in_the_owner_report():
    payload = synthetic_owner_services_payload()
    priorities = ["Colour", "Curly cuts", "Bridal", "Extensions"]
    # The four synthetic questions are numbered 1-4; nothing covers Extensions.
    payload["report"]["owner_report"]["services"] = build_service_groups(
        priorities, {"1": "Colour", "2": "Colour", "3": "Curly cuts", "4": "Bridal"}
    )
    report = build_owner_report(payload)
    by_name = {service["name"]: service for service in report["services"]}
    assert by_name["Colour"]["status"] == "Tested" and by_name["Colour"]["answers"] > 0
    # A priority with no question is "Not tested", never a zero.
    assert by_name["Extensions"]["status"] == "Not tested"
    assert by_name["Extensions"]["appearances"] is None
    assert not any("mapping not confirmed" in service["name"] for service in report["services"])


def test_a_question_linked_to_two_priorities_cannot_exist_in_the_groups():
    groups = build_service_groups(PRIORITIES, {"1": "Co-working", "2": "Private offices", "3": NOT_LINKED})
    orders = [order for group in groups for order in group["questions"]]
    assert len(orders) == len(set(orders))
    assert all(isinstance(order, int) for order in orders)


# ---------------------------------------------------------------- the first real WRAP run
WRAP_PRIORITIES = ["Coworking", "Private offices", "Meeting rooms", "Event spaces", "Team away days",
                   "Sustainable working space", "Flexible membership"]
WRAP_QUESTIONS = [
    "Recommend places in Brighton for coworking.", "Recommend places in Brighton for private offices.",
    "Recommend places in Brighton for meeting rooms.", "Recommend places in Brighton for event spaces.",
    "Recommend places in Brighton for team away days.", "Recommend places for co working near Brighton station",
    "Sustainable working offices in Brighton", "Flexible working spaces in Brighton",
]


def wrap_suggestions():
    return suggest_priority_map(
        [{"base_prompt_order": i, "prompt_text": q} for i, q in enumerate(WRAP_QUESTIONS, 1)], WRAP_PRIORITIES
    )


def test_wrap_questions_are_linked_to_the_right_priorities():
    # Regression: Q6 ("co working") and Q8 ("flexible working spaces") were both suggested as
    # "Sustainable working space" because they share the generic word "working", which hid Q6's 9 of 9
    # from Coworking in the first client report.
    got = wrap_suggestions()
    assert [got.get(str(i)) for i in range(1, 8)] == [
        "Coworking", "Private offices", "Meeting rooms", "Event spaces", "Team away days", "Coworking",
        "Sustainable working space",
    ]


def test_an_ambiguous_question_gets_no_suggestion_so_a_person_decides():
    assert "8" not in wrap_suggestions()  # "Flexible working spaces" fits three priorities equally badly


def test_a_word_shared_between_priorities_cannot_decide_on_its_own():
    assert suggest_priority("Best working area in Leeds", ["Coworking hub", "Sustainable working space"]) is None


def test_co_working_and_coworking_are_the_same_word():
    assert suggest_priority("Where is a good co working place", ["Coworking", "Meeting rooms"]) == "Coworking"
    assert suggest_priority("Best coworking near me", ["Co-working", "Meeting rooms"]) == "Co-working"
