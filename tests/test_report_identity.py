import pandas as pd
import pytest

from src.ai_recommendation_intelligence import build_recommendation_records
from src.poc_audit_assembler import _recommendation_evidence
from src.report_identity import (
    UndecidedTargetNamesError,
    assert_target_names_decided,
    brand_core_variants,
    confirmed_alias_frame,
    find_possible_target_names,
    target_name_adjudications,
    undecided_target_names,
)

TARGET_NAME = "WRAP- Coworking, Meeting Rooms & Offices"
TARGET_ID = "place-wrap"


def unresolved(*pairs):
    return [{"business_name": name, "recommendations": count} for name, count in pairs]


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        (TARGET_NAME, ["wrap"]),
        ("Runway East Brighton | Office Space", ["runway east brighton"]),
        ("Freedom Works - The Palace Workspace", ["freedom works"]),
        # Not split: hyphen without surrounding space, too short, generic, or no descriptor.
        ("Coca-Cola Cafe", []),
        ("AB - Cafe", []),
        ("Brighton - Best Cafe", []),
        ("The Skiff", []),
    ],
)
def test_brand_core_variants(name, expected):
    assert brand_core_variants(name) == expected


def test_shorter_brand_name_is_flagged_and_unrelated_names_are_not():
    found = find_possible_target_names(
        TARGET_NAME,
        unresolved(
            ("WRAP", 12), ("WRAP Coworking (Hove)", 2), ("PLATF9RM", 20),
            ("Wrapped Gifts", 1), ("Hotel Pelirocco", 5),
        ),
    )
    assert [item["name"] for item in found] == ["WRAP", "WRAP Coworking (Hove)"]
    assert found[0]["recommendations"] == 12


def test_a_business_is_not_flagged_against_itself():
    assert find_possible_target_names(TARGET_NAME, unresolved((TARGET_NAME, 3))) == []


def test_listing_name_shortened_by_the_ai_is_flagged():
    found = find_possible_target_names(
        "The Garden Bar Hove", unresolved(("Garden Bar", 3), ("Garden Room", 1))
    )
    assert [item["name"] for item in found] == ["Garden Bar"]


def test_decisions_clear_the_guard_but_undecided_names_block_it():
    names = unresolved(("WRAP", 12))
    with pytest.raises(UndecidedTargetNamesError) as raised:
        assert_target_names_decided(TARGET_NAME, names, [], [])
    assert "WRAP" in str(raised.value) and "12 answer(s)" in str(raised.value)
    assert_target_names_decided(TARGET_NAME, names, ["WRAP"], [])
    assert_target_names_decided(TARGET_NAME, names, [], ["WRAP"])
    assert undecided_target_names(TARGET_NAME, names, [], []) != []


def test_adjudications_credit_only_confirmed_names_to_the_target():
    result = target_name_adjudications(
        target_google_place_id=TARGET_ID, target_business_name=TARGET_NAME,
        confirmed=["WRAP", " "],
    )
    assert result == {
        "WRAP": {
            "google_place_id": TARGET_ID,
            "business_name": TARGET_NAME,
            "resolution_method": "reviewer_confirmed_target_name",
        }
    }


ANSWERS = [
    "1. **Plus X Innovation Brighton** – big hub.\n2. **WRAP** – friendly co-working space.",
    "1. **WRAP** – meeting rooms.\n2. **The Skiff** – desks.\n3. **WRAP** – repeated.",
    "1. **The Skiff** – desks.",
]
BUSINESSES = pd.DataFrame(
    [
        {"google_place_id": TARGET_ID, "business_name": TARGET_NAME, "primary_group": "coworking", "business_format": ""},
        {"google_place_id": "place-plusx", "business_name": "Plus X Innovation Brighton", "primary_group": "coworking", "business_format": ""},
        {"google_place_id": "place-skiff", "business_name": "The Skiff", "primary_group": "coworking", "business_format": ""},
    ]
)


def results_frame():
    return pd.DataFrame(
        [
            {
                "query_id": f"q{index}", "base_prompt_order": index, "repeat_index": 1,
                "prompt_category": "Owner priority", "prompt_text": "Best co working hub in Brighton",
                "provider": "openai", "model": "m", "status": "completed",
                "response_complete": True, "raw_response": answer,
            }
            for index, answer in enumerate(ANSWERS, 1)
        ]
    )


def config(adjudications=None):
    return {
        "target_google_place_id": TARGET_ID,
        "target_business_name": TARGET_NAME,
        "primary_group": "coworking",
        "slot_adjudications": adjudications or {},
        "non_business_prefixes": (),
    }


def target_slot_answers(slots):
    return {slot["query_id"] for slot in slots if slot["google_place_id"] == TARGET_ID}


def test_without_confirmation_the_short_name_is_lost_which_is_the_reported_defect():
    slots, _ = _recommendation_evidence(results_frame(), BUSINESSES, pd.DataFrame(), config=config())
    assert target_slot_answers(slots) == set()
    assert any(slot["raw_business_name"] == "WRAP" and not slot["google_place_id"] for slot in slots)


def test_confirmed_name_is_credited_once_per_answer_through_the_assembler():
    adjudications = target_name_adjudications(
        target_google_place_id=TARGET_ID, target_business_name=TARGET_NAME, confirmed=["WRAP"]
    )
    slots, market = _recommendation_evidence(
        results_frame(), BUSINESSES, pd.DataFrame(), config=config(adjudications)
    )
    assert target_slot_answers(slots) == {"q1", "q2"}
    target_slots = [slot for slot in slots if slot["google_place_id"] == TARGET_ID]
    assert {slot["resolution_method"] for slot in target_slots} == {"reviewer_confirmed_target_name"}
    assert all(slot["business_name"] == TARGET_NAME for slot in target_slots)
    assert any(row["google_place_id"] == TARGET_ID and row["recommendations"] > 0 for row in market)


def test_confirmed_alias_frame_resolves_through_the_directory():
    aliases = confirmed_alias_frame(
        target_google_place_id=TARGET_ID, target_business_name=TARGET_NAME, confirmed=["WRAP"]
    )
    records = build_recommendation_records(
        results=results_frame(), businesses=BUSINESSES, aliases=aliases,
        target_google_place_id=TARGET_ID, commercial_competitor_ids=set(), primary_group="coworking",
    )
    target_rows = records[records["classification"] == "Target"]
    assert set(target_rows["query_id"]) == {"q1", "q2"}
    assert (target_rows["alias_type"] == "reviewer_confirmed").all()


def test_alias_frame_with_no_confirmed_names_is_empty_with_expected_columns():
    frame = confirmed_alias_frame(
        target_google_place_id=TARGET_ID, target_business_name=TARGET_NAME, confirmed=[]
    )
    assert frame.empty and "alias_name" in frame.columns
