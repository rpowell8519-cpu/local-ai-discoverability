from __future__ import annotations

from src.report_audit_repository import (
    attach_benchmark_revision,
    get_latest_report_audit,
    save_evidence_states_revision,
    save_owner_brief_revision,
)


class Result:
    def __init__(self, row=None):
        self.row = row

    def mappings(self):
        return self

    def first(self):
        return self.row

    def one(self):
        return self.row


class Connection:
    def __init__(self, latest=None):
        self.latest = latest
        self.insert = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, statement, parameters):
        if "insert into report_audit_revisions" in str(statement):
            self.insert = parameters
            return Result({**parameters})
        return Result(self.latest)


class Engine:
    def __init__(self, latest=None):
        self.connection = Connection(latest)

    def connect(self):
        return self.connection

    def begin(self):
        return self.connection


def test_latest_revision_is_loaded_by_canonical_place_id():
    engine = Engine({"id": "audit-1", "revision": 2})

    result = get_latest_report_audit("place-1", engine=engine)

    assert result == {"id": "audit-1", "revision": 2}


def test_first_owner_brief_creates_revision_one():
    engine = Engine()

    result = save_owner_brief_revision(
        target_google_place_id="place-1",
        target_business_name="Example Business",
        known_for="Excellent commercial cleaning in Brighton",
        desired_searches="Who offers commercial cleaning in Brighton?",
        engine=engine,
    )

    assert result["revision"] == 1
    assert result["supersedes_revision_id"] is None
    assert engine.connection.insert["benchmark_run_id"] is None


def test_owner_can_supply_a_missing_website_address():
    engine = Engine()

    result = save_owner_brief_revision(
        target_google_place_id="place-1",
        target_business_name="Example Business",
        known_for="Excellent commercial cleaning in Brighton",
        desired_searches="Who offers commercial cleaning in Brighton?",
        manual_website_url="https://example.test/services",
        priority_services="Office cleaning\nCarpet cleaning",
        engine=engine,
    )

    assert result["manual_website_url"] == "https://example.test/services"
    assert '"Office cleaning"' in result["owner_context"]


def test_invalid_manual_website_address_is_rejected():
    engine = Engine()

    try:
        save_owner_brief_revision(
            target_google_place_id="place-1",
            target_business_name="Example Business",
            known_for="Excellent commercial cleaning in Brighton",
            desired_searches="Who offers commercial cleaning in Brighton?",
            manual_website_url="example.test",
            engine=engine,
        )
    except ValueError as exc:
        assert "http:// or https://" in str(exc)
    else:
        raise AssertionError("Invalid website URL was accepted")


def test_owner_brief_update_invalidates_benchmark_and_review_state():
    engine = Engine(
        {
            "id": "audit-1",
            "revision": 1,
            "benchmark_run_id": "run-1",
            "website_evidence_state": "available",
            "review_evidence_state": "unavailable",
            "reviewer_decisions": {"approved": True},
            "reviewer_decisions_complete": True,
        }
    )

    result = save_owner_brief_revision(
        target_google_place_id="place-1",
        target_business_name="Example Business",
        known_for="Excellent office and commercial cleaning",
        desired_searches="Who offers office cleaning in Brighton?",
        engine=engine,
    )

    assert result["revision"] == 2
    assert result["supersedes_revision_id"] == "audit-1"
    assert result["benchmark_run_id"] is None
    assert result["reviewer_decisions_complete"] is False


def test_completed_benchmark_is_attached_as_a_new_revision():
    engine = Engine(
        {
            "id": "audit-1",
            "revision": 1,
            "target_business_name": "Example Business",
            "known_for": "Excellent commercial cleaning",
            "desired_searches": ["Who offers commercial cleaning?"],
            "owner_competitors": [],
            "website_evidence_state": "not_checked",
            "review_evidence_state": "not_checked",
        }
    )

    result = attach_benchmark_revision(
        target_google_place_id="place-1",
        benchmark_run_id="run-1",
        engine=engine,
    )

    assert result["revision"] == 2
    assert result["benchmark_run_id"] == "run-1"


def test_unavailable_evidence_is_saved_without_removing_benchmark():
    engine = Engine(
        {
            "id": "audit-1",
            "revision": 2,
            "target_business_name": "Example Business",
            "known_for": "Excellent commercial cleaning",
            "desired_searches": ["Who offers commercial cleaning?"],
            "owner_competitors": [],
            "owner_context": {},
            "manual_website_url": None,
            "benchmark_run_id": "run-1",
        }
    )

    result = save_evidence_states_revision(
        target_google_place_id="place-1",
        website_evidence_state="unavailable",
        review_evidence_state="unavailable",
        engine=engine,
    )

    assert result["benchmark_run_id"] == "run-1"
    assert result["website_evidence_state"] == "unavailable"
    assert result["review_evidence_state"] == "unavailable"
    assert result["reviewer_decisions_complete"] is False
