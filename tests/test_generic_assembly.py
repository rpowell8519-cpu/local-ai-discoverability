"""The generic report assembler run against stubbed data, capturing the config it builds.

assemble_poc_audit_payload needs a database, so it is replaced by a function that returns
the config it was given. Everything this repository's own code decides is then visible:
which names are credited to the target, how priorities map to questions, what is disclosed.
"""
import datetime as dt
from unittest import mock

import pytest

from src.poc_audit_generic import assemble_generic_report_payload
from src.report_identity import UndecidedTargetNamesError

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
    with pytest.raises(UndecidedTargetNamesError, match="“WRAP”"):
        assemble({})


def test_a_rejected_name_lets_generation_proceed_without_crediting_it():
    config, _ = assemble({"rejected_target_names": ["WRAP"]})
    assert config["slot_adjudications"] == {}


def test_a_confirmed_name_is_credited_to_the_target_and_disclosed():
    config, loader = assemble({"confirmed_target_names": ["WRAP"]})
    assert config["slot_adjudications"]["WRAP"]["google_place_id"] == TARGET_ID
    assert config["slot_adjudications"]["WRAP"]["resolution_method"] == "reviewer_confirmed_target_name"
    assert any("“WRAP”" in line for line in config["methodology_validation"])
    assert loader.call_args.kwargs["confirmed_target_names"] == ["WRAP"]


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
