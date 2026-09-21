"""The generic report assembler run against stubbed data, capturing the config it builds.

assemble_poc_audit_payload needs a database, so it is replaced by a function that returns
the config it was given. Everything this repository's own code decides is then visible:
which names are credited to the target, how priorities map to questions, what is disclosed.
"""
import datetime as dt
from unittest import mock

import pytest

from src.poc_audit_generic import assemble_generic_report_payload
from src.business_matching import UndecidedNamesError

TARGET_ID, RUN_ID, NAME = "place-wrap", "11111111-1111-1111-1111-111111111111", "WRAP- Coworking, Meeting Rooms & Offices"
PRIORITIES = ["Co-working", "Private offices", "Meeting rooms"]


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


BUSINESS_ROWS = [
    {"google_place_id": pid, "business_name": name, "primary_group": "coworking", "business_format": "",
     "city": "Brighton", "address": "x", "latitude": "50.83", "longitude": "-0.14",
     "phone": "01273 123456" if pid == TARGET_ID else None, "postal_code": "BN1 4EA" if pid == TARGET_ID else None}
    for pid, name in ((TARGET_ID, NAME), ("place-plusx", "Plus X Innovation Brighton"), ("place-skiff", "The Skiff"))
]


class _Connection:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, statement, params=None):
        sql = " ".join(str(statement).lower().split())
        if "from ai_visibility_runs" in sql:
            return _Result([{
                "id": RUN_ID, "status": "completed", "providers": ["OpenAI", "Claude", "Gemini"],
                "prompt_count": 3, "repeat_count": 3, "location_context": "Brighton and Hove",
                "primary_group": "coworking", "target_category_label": "Coworking",
            }])
        if "from business_features bf" in sql and "lateral" in sql:
            return _Result(BUSINESS_ROWS)
        if "from website_audit_runs" in sql:
            return _Result([])
        if "count(*)" in sql and "business_reviews" in sql:
            return _Result(scalar=100)
        if "from business_reviews" in sql:
            return _Result([])
        if "from business_features where google_place_id is not null" in sql:
            return _Result(BUSINESS_ROWS)
        raise AssertionError(f"Unexpected query: {sql[:120]}")


class _Engine:
    def connect(self):
        return _Connection()


UNRESOLVED = [{"business_name": "WRAP", "recommendations": 12}, {"business_name": "PLATF9RM", "recommendations": 20}]


def revision(decisions):
    return {
        "id": "rev-1", "revision": 4, "target_google_place_id": TARGET_ID, "target_business_name": NAME,
        "known_for": "A friendly co-working space for freelancers and teams", "owner_competitors": [],
        "benchmark_run_id": RUN_ID, "reviewer_decisions_complete": True,
        "reviewer_decisions": {"cohort_place_ids": ["place-plusx", "place-skiff"], **decisions},
        "owner_context": {"priority_services": PRIORITIES, "service_areas": ["Brighton and Hove"]},
    }


def assemble(decisions):
    summary = {
        "target": [{"recommendations": 0}], "unresolved": UNRESOLVED,
        "verified": [
            {"google_place_id": "place-plusx", "business_name": "Plus X Innovation Brighton", "recommendations": 23},
            {"google_place_id": "place-skiff", "business_name": "The Skiff", "recommendations": 8},
        ],
    }
    with mock.patch("src.poc_audit_generic.load_report_candidates", return_value=summary) as loader, \
         mock.patch("src.poc_audit_generic.assemble_poc_audit_payload", side_effect=lambda config, engine=None: config):
        config = assemble_generic_report_payload(revision(decisions), engine=_Engine())
    return config, loader


def test_an_undecided_look_alike_name_stops_generation_with_a_clear_message():
    with pytest.raises(UndecidedNamesError, match="“WRAP”"):
        assemble({})


def test_a_rejected_name_lets_generation_proceed_without_crediting_it():
    config, _ = assemble({"rejected_target_names": ["WRAP"]})
    assert config["slot_adjudications"] == {}


def test_a_confirmed_name_is_credited_to_the_target_and_disclosed():
    config, loader = assemble({"confirmed_target_names": ["WRAP"]})
    assert config["slot_adjudications"]["WRAP"]["google_place_id"] == TARGET_ID
    assert config["slot_adjudications"]["WRAP"]["resolution_method"] == "reviewer_confirmed_target_name"
    assert any("“WRAP”" in line for line in config["methodology_validation"])
    assert loader.call_args.kwargs["confirmed_names"] == {TARGET_ID: ["WRAP"]}


def test_confirmed_links_become_service_groups_that_cover_each_question_once():
    links = {"question_priority_map": {"1": "Co-working", "2": "Private offices", "3": "Co-working"}}
    config, _ = assemble({"confirmed_target_names": ["WRAP"], **links})
    groups = {g["name"]: g["questions"] for g in config["owner_report"]["services"]}
    assert groups == {"Co-working": [1, 3], "Private offices": [2], "Meeting rooms": []}


def test_reviews_saved_before_links_existed_keep_coverage_not_mapped():
    config, _ = assemble({"confirmed_target_names": ["WRAP"]})
    assert config["owner_report"]["services"] == [{"name": p, "questions": None} for p in PRIORITIES]


def test_location_and_business_type_travel_with_the_report_for_the_summary():
    config, _ = assemble({"confirmed_target_names": ["WRAP"]})
    assert config["owner_report"]["location"] == "Brighton and Hove"
    assert config["owner_report"]["primary_group"] == "coworking"
    assert config["report_format"] == "accessible_owner_services_v4"
    assert config["cohort"][0]["google_place_id"] == "place-plusx"


def test_the_google_listings_phone_and_postcode_travel_with_the_report():
    config, _ = assemble({"confirmed_target_names": ["WRAP"]})
    assert config["owner_report"]["listing_contact"] == {"phone": "01273 123456", "postal_code": "BN1 4EA", "address": "x"}


def test_generated_reports_ask_for_findings_and_carry_the_site_check_they_were_given():
    finding = {"id": "E1", "kind": "crawler_access", "gap": True, "observation": "x", "source": "y", "blocked_labels": ["Perplexity"]}
    summary = {"target": [{"recommendations": 0}], "unresolved": UNRESOLVED, "verified": []}
    with mock.patch("src.poc_audit_generic.load_report_candidates", return_value=summary), \
         mock.patch("src.poc_audit_generic.assemble_poc_audit_payload", side_effect=lambda config, engine=None: config):
        config = assemble_generic_report_payload(
            revision({"confirmed_target_names": ["WRAP"]}), engine=_Engine(), site_findings=[finding]
        )
    assert config["owner_report"]["auto_findings"] is True
    assert config["owner_report"]["site_findings"] == [finding]



# ---------------------------------------------------------------- owner competitors and other businesses
OWNER_BUSINESS_ROWS = BUSINESS_ROWS + [
    {"google_place_id": "place-platf9rm", "business_name": "PLATF9RM Brighton - Coworking, Offices & Events", "primary_group": "coworking",
     "business_format": "", "city": "Brighton", "address": "x", "latitude": "50.83", "longitude": "-0.14", "phone": None, "postal_code": None},
]


def assemble_with_owners(decisions, owners=("PLATF9RM",), unresolved=None):
    audit = revision({"cohort_place_ids": ["place-plusx", "place-platf9rm"], **decisions})
    audit["owner_competitors"] = list(owners)
    summary = {"target": [{"recommendations": 0}], "unresolved": unresolved if unresolved is not None else [
        *UNRESOLVED, {"business_name": "Plus X Innovation Hub", "recommendations": 7}],
        "verified": [{"google_place_id": "place-platf9rm", "business_name": OWNER_BUSINESS_ROWS[3]["business_name"], "recommendations": 33}]}

    class Engine(_Engine):
        def connect(self):
            conn = _Connection()
            original = conn.execute

            def execute(statement, params=None):
                sql = " ".join(str(statement).lower().split())
                if "from business_features bf" in sql and "lateral" in sql:
                    return _Result(OWNER_BUSINESS_ROWS)
                if "from business_features where google_place_id is not null" in sql:
                    return _Result(OWNER_BUSINESS_ROWS)
                return original(statement, params)
            conn.execute = execute
            return conn

    with mock.patch("src.poc_audit_generic.load_report_candidates", return_value=summary) as loader, \
         mock.patch("src.poc_audit_generic.assemble_poc_audit_payload", side_effect=lambda config, engine=None: config):
        config = assemble_generic_report_payload(audit, engine=Engine())
    return config, loader


DECIDED = {"confirmed_target_names": ["WRAP"], "owner_competitor_places": {"PLATF9RM": "place-platf9rm"},
           "name_links": {"place-platf9rm": {"confirmed": ["PLATF9RM"]}, "place-plusx": {"rejected": ["Plus X Innovation Hub"]}}}


def test_generation_is_blocked_until_the_owners_competitor_is_matched_to_a_business():
    with pytest.raises(UndecidedNamesError, match="which business in the database “PLATF9RM” is"):
        assemble_with_owners({"confirmed_target_names": ["WRAP"]})


def test_generation_is_blocked_while_an_ai_name_for_a_competitor_is_undecided():
    decisions = {**DECIDED, "name_links": {}}
    with pytest.raises(UndecidedNamesError) as raised:
        assemble_with_owners(decisions)
    assert "“PLATF9RM” (20 answer(s))" in str(raised.value) and "“Plus X Innovation Hub” (7 answer(s))" in str(raised.value)


def test_a_confirmed_competitor_name_is_credited_to_the_competitor_and_disclosed():
    config, loader = assemble_with_owners(DECIDED)
    credited = config["slot_adjudications"]["PLATF9RM"]
    assert credited["google_place_id"] == "place-platf9rm" and credited["resolution_method"] == "reviewer_confirmed_business_name"
    assert "PLATF9RM" not in [n for n in config["slot_adjudications"] if config["slot_adjudications"][n]["google_place_id"] == TARGET_ID]
    assert loader.call_args.kwargs["confirmed_names"] == {TARGET_ID: ["WRAP"], "place-platf9rm": ["PLATF9RM"]}
    assert any("as PLATF9RM Brighton - Coworking, Offices & Events: “PLATF9RM”" in line for line in config["methodology_validation"])


def test_the_owners_competitors_are_listed_as_the_reviewer_matched_them():
    config, _ = assemble_with_owners(DECIDED)
    entries = config["analyst_decisions"]["owner_competitors"]
    assert entries[0]["google_place_id"] == "place-platf9rm" and entries[0]["visibility_status"] == "Recommended 33 times"


def test_an_owner_competitor_not_in_the_database_is_counted_as_one_named_group():
    decisions = {"confirmed_target_names": ["WRAP"], "owner_competitor_places": {"PLATF9RM": ""},
                 "name_links": {"owner:platf9rm": {"confirmed": ["PLATF9RM"]}, "place-plusx": {"rejected": ["Plus X Innovation Hub"]}}}
    config, _ = assemble_with_owners(decisions)
    group = config["slot_adjudications"]["PLATF9RM"]
    assert group["google_place_id"] is None and group["business_name"] == "PLATF9RM"
    entry = config["analyst_decisions"]["owner_competitors"][0]
    assert entry["google_place_id"] is None and entry["match_status"] == "not_in_system"


def test_googles_own_review_count_and_rating_travel_with_the_report():
    saved = [dict(row) for row in BUSINESS_ROWS]
    try:
        BUSINESS_ROWS[0].update(rating="4.6", reviews="2,431")
        BUSINESS_ROWS[1].update(rating=None, reviews="not a number")
        config, _ = assemble({"confirmed_target_names": ["WRAP"]})
    finally:
        for row, original in zip(BUSINESS_ROWS, saved):
            row.clear()
            row.update(original)
    listing = config["owner_report"]["listing_reviews"]
    assert listing[TARGET_ID] == {"reviews": 2431, "rating": 4.6}
    assert listing["place-plusx"] == {"reviews": None, "rating": None}   # unreadable text becomes "not recorded", never an error


def test_approved_wording_for_the_business_type_travels_with_the_report_and_is_disclosed():
    wording = {"label": "sauna", "booking": "book a session", "pricing": "session prices", "questions": "what to bring",
               "details": "opening times", "review_themes": []}
    config, _ = assemble({"confirmed_target_names": ["WRAP"], "type_wording": wording})
    assert config["owner_report"]["type_wording"]["booking"] == "book a session"
    assert any("drafted by an AI" in line and "sauna" in line for line in config["methodology_validation"])
    plain, _ = assemble({"confirmed_target_names": ["WRAP"]})
    assert plain["owner_report"]["type_wording"] == {}
    assert not any("drafted by an AI" in line for line in plain["methodology_validation"])
