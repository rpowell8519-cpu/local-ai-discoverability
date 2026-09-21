"""Reconciling the owner's competitors, and other businesses, with the names the AI used."""
import pytest

from src.business_matching import (
    CONFIRMED_METHOD, ConflictingNameLinksError, NOT_IN_SYSTEM, TARGET_KEY, UndecidedNamesError,
    confirmed_names_by_place, decisions_for, default_owner_match, name_adjudications, owner_competitor_candidates,
    owner_competitor_entries, owner_key, plan_subjects, undecided_items,
)

TARGET_ID = "ChIJwrap"
RECORDS = [
    {"google_place_id": TARGET_ID, "business_name": "WRAP- Coworking, Meeting Rooms & Offices", "city": "Brighton", "address": None},
    {"google_place_id": "plusx", "business_name": "Plus X Innovation Brighton", "city": "Brighton", "address": None},
    {"google_place_id": "runway", "business_name": "Runway East Brighton | Office Space", "city": "Brighton", "address": None},
    {"google_place_id": "platf9rm", "business_name": "PLATF9RM Brighton - Coworking, Offices & Events", "city": "Brighton", "address": None},
    {"google_place_id": "freedom", "business_name": "Freedom Works - The Palace Workspace", "city": "Brighton", "address": None},
    {"google_place_id": "nile", "business_name": "Projects Nile House", "city": "Brighton", "address": None},
    {"google_place_id": "foundry", "business_name": "FOUNDRY Hove", "city": "Hove", "address": None},
]
NAMES = {r["google_place_id"]: r["business_name"] for r in RECORDS}
# The kinds of names the first real WRAP run left unresolved
UNRESOLVED = [
    {"business_name": "PLATF9RM", "recommendations": 25}, {"business_name": "WRAP", "recommendations": 12},
    {"business_name": "Projects", "recommendations": 8}, {"business_name": "Plus X Innovation Hub", "recommendations": 7},
    {"business_name": "Projects Brighton", "recommendations": 7}, {"business_name": "Brighton i360", "recommendations": 7},
    {"business_name": "Hotel Pelirocco", "recommendations": 5},
]
OWNERS = ["PLATF9RM", "Freedom Works", "PROJECTS", "FOUNDRY", "PLUS X"]


def names(found):
    return [r["business_name"] for r in found]


def test_the_owners_words_find_the_database_business_despite_a_different_name():
    assert "PLATF9RM Brighton - Coworking, Offices & Events" in names(owner_competitor_candidates("PLATF9RM", RECORDS))
    assert names(owner_competitor_candidates("PLUS X", RECORDS))[0] == "Plus X Innovation Brighton"
    assert "Freedom Works - The Palace Workspace" in names(owner_competitor_candidates("Freedom Works", RECORDS))


def test_a_match_is_preselected_only_when_one_business_is_clearly_meant():
    assert default_owner_match("PLATF9RM", owner_competitor_candidates("PLATF9RM", RECORDS)) == "platf9rm"
    assert default_owner_match("PLUS X", owner_competitor_candidates("PLUS X", RECORDS)) == "plusx"
    two_branches = RECORDS + [{"google_place_id": "p2", "business_name": "Projects Brighton Station", "city": "Brighton", "address": None}]
    assert default_owner_match("PROJECTS", owner_competitor_candidates("PROJECTS", two_branches)) is None  # ambiguous: a person decides


def subjects(owner_places=None, cohort=("plusx", "runway")):
    return plan_subjects(
        target_id=TARGET_ID, target_name=NAMES[TARGET_ID], unresolved=UNRESOLVED, owner_names=OWNERS,
        owner_places=owner_places or {}, cohort_ids=cohort, names_by_id=NAMES,
    )


def flagged(subject_list, key):
    return [n["name"] for s in subject_list if s.key == key for n in s.names]


def test_the_owners_short_name_is_flagged_even_though_it_equals_what_the_owner_typed():
    # Regression: "PLATF9RM" (25 answers) sat unresolved beside a resolved "PLATF9RM Brighton ..." counted at 8.
    plan = subjects({"PLATF9RM": "platf9rm", "PLUS X": "plusx"})
    assert flagged(plan, "platf9rm") == ["PLATF9RM"]
    assert "Plus X Innovation Hub" in flagged(plan, "plusx")


def test_the_target_short_name_is_still_flagged_first():
    assert flagged(subjects(), TARGET_KEY) == ["WRAP"]


def test_an_owner_competitor_with_no_database_record_still_gets_its_names_flagged():
    plan = subjects({"PLATF9RM": NOT_IN_SYSTEM})
    entry = next(s for s in plan if s.key == owner_key("PLATF9RM"))
    assert entry.place_id is None and [n["name"] for n in entry.names] == ["PLATF9RM"]


def test_a_name_is_offered_to_only_one_business():
    plan = subjects({"PLATF9RM": "platf9rm"})
    all_names = [n["name"] for s in plan for n in s.names]
    assert len(all_names) == len(set(all_names))


def test_unrelated_names_are_never_flagged():
    plan = subjects({"PLATF9RM": "platf9rm", "PLUS X": "plusx"})
    assert not {"Hotel Pelirocco", "Brighton i360"} & {n["name"] for s in plan for n in s.names}


def test_nothing_is_decided_until_a_person_decides():
    plan = subjects({"PLATF9RM": "platf9rm"})
    items = undecided_items(plan, {"owner_competitor_places": {"PLATF9RM": "platf9rm"}}, OWNERS)
    assert {i["subject"] for i in items if i["name"] is None} == set(OWNERS) - {"PLATF9RM"}   # unchosen owner competitors
    assert any(i["name"] == "WRAP" for i in items) and any(i["name"] == "PLATF9RM" for i in items)


def test_every_decision_clears_its_item():
    places = {o: "" for o in OWNERS}
    plan = subjects(places)
    decisions = {"owner_competitor_places": places, "confirmed_target_names": ["WRAP"],
                 "name_links": {s.key: {"rejected": [n["name"] for n in s.names]} for s in plan if s.key != TARGET_KEY}}
    assert undecided_items(plan, decisions, OWNERS) == []


def test_confirmed_names_are_credited_to_the_database_business_by_place_id():
    plan = subjects({"PLATF9RM": "platf9rm"})
    decisions = {"name_links": {"platf9rm": {"confirmed": ["PLATF9RM"]}}}
    result = name_adjudications(plan, decisions, {})
    assert result["PLATF9RM"] == {"google_place_id": "platf9rm", "business_name": NAMES["platf9rm"], "resolution_method": CONFIRMED_METHOD}
    assert confirmed_names_by_place(plan, decisions) == {"platf9rm": ["PLATF9RM"]}


def test_an_owner_competitor_not_in_the_database_gets_one_named_unverified_group():
    plan = subjects({"PLATF9RM": NOT_IN_SYSTEM})
    decisions = {"name_links": {owner_key("PLATF9RM"): {"confirmed": ["PLATF9RM"]}}}
    entry = name_adjudications(plan, decisions, {})["PLATF9RM"]
    assert entry["google_place_id"] is None and entry["business_name"] == "PLATF9RM"


def test_the_target_keeps_its_own_resolution_method():
    plan = subjects()
    assert name_adjudications(plan, {"confirmed_target_names": ["WRAP"]}, {})["WRAP"]["resolution_method"] == "reviewer_confirmed_target_name"


def test_one_name_cannot_be_confirmed_for_two_businesses():
    plan = subjects({"PLUS X": "plusx", "PLATF9RM": "platf9rm"})
    decisions = {"confirmed_target_names": ["WRAP"], "name_links": {"plusx": {"confirmed": ["Shared"]}, "platf9rm": {"confirmed": ["Shared"]}}}
    with pytest.raises(ConflictingNameLinksError):
        name_adjudications(plan, decisions, {})


def test_owner_competitors_are_listed_as_matched_or_not_in_the_system():
    decisions = {"owner_competitor_places": {"PLATF9RM": "platf9rm", "FOUNDRY": ""}}
    entries = owner_competitor_entries(["PLATF9RM", "FOUNDRY"], decisions, NAMES, {"platf9rm": 33})
    assert entries[0]["google_place_id"] == "platf9rm" and entries[0]["visibility_status"] == "Recommended 33 times"
    assert entries[1]["google_place_id"] is None and entries[1]["match_status"] == "not_in_system"


def test_the_error_names_exactly_what_is_undecided():
    message = str(UndecidedNamesError([{"subject": "PLATF9RM", "name": None}, {"subject": "WRAP- Coworking", "name": "WRAP", "recommendations": 12}]))
    assert "which business in the database “PLATF9RM” is" in message and "“WRAP” (12 answer(s))" in message


def test_decisions_are_read_from_where_they_are_saved():
    plan = subjects()
    assert decisions_for({"confirmed_target_names": ["WRAP"]}, plan[0]) == (["WRAP"], [])
    assert decisions_for({"name_links": {"plusx": {"confirmed": ["a"], "rejected": ["b"]}}}, next(s for s in subjects({"PLUS X": "plusx"}) if s.key == "plusx")) == (["a"], ["b"])


# ---- a frequently used AI name that is really a listed business outside this report
def outside(unresolved, records=RECORDS, cohort=("plusx",), owners=()):
    return [s for s in plan_subjects(
        target_id=TARGET_ID, target_name=NAMES[TARGET_ID], unresolved=unresolved, owner_names=list(owners),
        owner_places={}, cohort_ids=list(cohort), names_by_id=NAMES, records=records) if s.outside_set]


def test_a_common_ai_name_is_offered_against_the_listed_business_it_resembles():
    found = outside([{"business_name": "FOUNDRY", "recommendations": 9}])
    assert [(s.place_id, s.label, [n["name"] for n in s.names]) for s in found] == [("foundry", "FOUNDRY Hove", ["FOUNDRY"])]
    assert found[0].outside_set and found[0].names[0]["recommendations"] == 9


def test_it_is_a_pending_decision_until_a_person_confirms_or_rejects_it():
    subjects = plan_subjects(target_id=TARGET_ID, target_name=NAMES[TARGET_ID], unresolved=[{"business_name": "FOUNDRY", "recommendations": 9}],
                             owner_names=[], owner_places={}, cohort_ids=["plusx"], names_by_id=NAMES, records=RECORDS)
    assert [i["name"] for i in undecided_items(subjects, {}, [])] == ["FOUNDRY"]
    decisions = {"name_links": {"foundry": {"confirmed": ["FOUNDRY"], "rejected": []}}}
    assert undecided_items(subjects, decisions, []) == []
    assert name_adjudications(subjects, decisions, {})["FOUNDRY"]["google_place_id"] == "foundry"
    assert confirmed_names_by_place(subjects, decisions) == {"foundry": ["FOUNDRY"]}


def test_rarely_used_unrelated_or_already_claimed_names_are_left_alone():
    assert outside([{"business_name": "FOUNDRY", "recommendations": 2}]) == []          # too few answers to bother a reviewer
    assert outside([{"business_name": "Hotel Pelirocco", "recommendations": 9}]) == []  # resembles nothing listed
    # The client's own short name goes to the client, not to some other business.
    assert outside([{"business_name": "WRAP", "recommendations": 12}]) == []


def test_a_business_already_in_the_report_is_not_offered_twice():
    assert outside([{"business_name": "FOUNDRY", "recommendations": 9}], cohort=("plusx", "foundry")) == []


def test_without_the_database_list_nothing_extra_is_offered():
    assert outside([{"business_name": "FOUNDRY", "recommendations": 9}], records=[]) == []
