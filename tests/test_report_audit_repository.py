from __future__ import annotations

import json

from src.report_audit_repository import (
    attach_benchmark_revision,
    get_latest_report_audit,
    save_evidence_states_revision,
    save_owner_brief_revision,
    save_owner_competitors_revision,
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


def test_owner_brief_can_mark_a_new_measurement_from_a_configured_report():
    engine = Engine()

    result = save_owner_brief_revision(
        target_google_place_id="place-1",
        target_business_name="Example Business",
        known_for="Excellent commercial cleaning in Brighton",
        desired_searches="Who offers commercial cleaning in Brighton?",
        workflow_origin="configured_report_restart",
        engine=engine,
    )

    assert '"workflow_origin": "configured_report_restart"' in result["owner_context"]


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


def test_owner_brief_update_preserves_configured_measurement_origin():
    engine = Engine(
        {
            "id": "audit-1",
            "revision": 1,
            "benchmark_run_id": None,
            "website_evidence_state": "not_checked",
            "review_evidence_state": "not_checked",
            "owner_context": {"workflow_origin": "configured_report_restart"},
        }
    )

    result = save_owner_brief_revision(
        target_google_place_id="place-1",
        target_business_name="Example Business",
        known_for="Updated commercial cleaning priorities",
        desired_searches="Who offers commercial cleaning in Brighton?",
        engine=engine,
    )

    assert '"workflow_origin": "configured_report_restart"' in result["owner_context"]


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


# ---------------------------------------------------------------- revision history and restore
from src.report_audit_repository import list_report_audit_revisions, restore_report_audit_revision  # noqa: E402


class HistoryResult:
    def __init__(self, rows):
        self.rows = list(rows)

    def mappings(self):
        return self

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None

    def one(self):
        return self.rows[0]


class HistoryConnection:
    """A store of revisions by number, so restore can be tested against genuinely different rows."""

    def __init__(self, revisions):
        self.by_revision = {int(row["revision"]): dict(row) for row in revisions}
        self.insert = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def _latest(self):
        return self.by_revision[max(self.by_revision)] if self.by_revision else None

    def execute(self, statement, parameters):
        sql = str(statement)
        if "insert into report_audit_revisions" in sql:
            self.insert = parameters
            row = dict(parameters)
            self.by_revision[row["revision"]] = row
            return HistoryResult([row])
        if "revision = :revision" in sql:
            row = self.by_revision.get(int(parameters["revision"]))
            return HistoryResult([row] if row else [])
        if "order by revision desc" in sql:
            return HistoryResult([self.by_revision[n] for n in sorted(self.by_revision, reverse=True)])
        raise AssertionError(f"Unexpected query: {sql[:80]}")


class HistoryEngine:
    def __init__(self, revisions=()):
        self.connection = HistoryConnection(revisions)

    def connect(self):
        return self.connection

    def begin(self):
        return self.connection


COWORKING_REVISION = {
    "id": "audit-coworking", "revision": 3, "target_business_name": "WRAP",
    "known_for": "A friendly coworking space", "desired_searches": ["Best coworking in Brighton"],
    "owner_competitors": ["PLATF9RM"], "benchmark_run_id": "run-coworking",
    "website_evidence_state": "available", "review_evidence_state": "available",
    "reviewer_decisions": {"confirmed_target_names": ["WRAP"]}, "reviewer_decisions_complete": True,
    "owner_context": {"priority_services": ["Coworking"]}, "manual_website_url": "https://wrap.example",
}
NURSERY_REVISION = {
    "id": "audit-nursery", "revision": 5, "target_business_name": "WRAP",
    "known_for": "On-site childcare in Brighton", "desired_searches": ["Best nursery in Hove"],
    "owner_competitors": ["Hopscotch"], "benchmark_run_id": "run-nursery",
    "website_evidence_state": "not_checked", "review_evidence_state": "not_checked",
    "reviewer_decisions": {}, "reviewer_decisions_complete": False,
    "owner_context": {"priority_services": ["Nursery places"]}, "manual_website_url": "https://wrap.example",
}


def test_the_full_history_is_listed_most_recent_first_and_nothing_is_left_out():
    engine = HistoryEngine([COWORKING_REVISION, NURSERY_REVISION])
    history = list_report_audit_revisions("place-wrap", engine=engine)
    assert [row["revision"] for row in history] == [5, 3]
    assert history[1]["known_for"] == "A friendly coworking space"


def test_restoring_an_earlier_revision_copies_every_field_of_it_exactly():
    engine = HistoryEngine([COWORKING_REVISION, NURSERY_REVISION])
    result = restore_report_audit_revision("place-wrap", 3, engine=engine)
    assert result["revision"] == 6 and result["supersedes_revision_id"] == "audit-nursery"
    assert result["revision_reason"] == "Restored from revision 3"
    assert result["known_for"] == "A friendly coworking space"
    assert result["benchmark_run_id"] == "run-coworking"
    assert json.loads(result["reviewer_decisions"]) == {"confirmed_target_names": ["WRAP"]}
    assert result["reviewer_decisions_complete"] is True
    assert json.loads(result["owner_context"]) == {"priority_services": ["Coworking"]}


def test_nothing_is_lost_by_restoring_the_earlier_one_can_be_restored_again():
    # The whole point: switching between two saved configurations never destroys either.
    engine = HistoryEngine([COWORKING_REVISION, NURSERY_REVISION])
    restore_report_audit_revision("place-wrap", 3, engine=engine)  # -> revision 6, a copy of 3
    back = restore_report_audit_revision("place-wrap", 5, engine=engine)  # -> revision 7, a copy of 5 (nursery)
    assert back["known_for"] == "On-site childcare in Brighton" and back["revision"] == 7
    assert len(list_report_audit_revisions("place-wrap", engine=engine)) == 4


def test_restoring_a_revision_that_does_not_exist_is_refused_plainly():
    engine = HistoryEngine([COWORKING_REVISION])
    try:
        restore_report_audit_revision("place-wrap", 99, engine=engine)
    except ValueError as exc:
        assert "Revision 99 was not found" in str(exc)
    else:
        raise AssertionError("A missing revision was silently accepted")


def test_restoring_the_only_revision_is_revision_one_with_no_predecessor():
    engine = HistoryEngine([])
    row = {**COWORKING_REVISION, "revision": 1}
    engine.connection.by_revision[1] = row
    result = restore_report_audit_revision("place-wrap", 1, engine=engine)
    assert result["revision"] == 2 and result["supersedes_revision_id"] == "audit-coworking"


# ---------------------------------------------------------------- adding a competitor mid-review
def test_a_new_competitor_can_be_added_without_disturbing_the_review():
    engine = Engine({
        "id": "audit-1", "revision": 4, "target_business_name": "WRAP", "known_for": "Coworking and childcare",
        "desired_searches": ["Best nursery in Hove"], "owner_competitors": ["Hopscotch"], "benchmark_run_id": "run-1",
        "website_evidence_state": "available", "review_evidence_state": "available",
        "reviewer_decisions": {"confirmed_target_names": ["WRAP"], "approved_recommendations": [{"id": "a1"}]},
        "reviewer_decisions_complete": True, "owner_context": {"priority_services": ["Nursery places"]},
        "manual_website_url": "https://wrap.example",
    })

    result = save_owner_competitors_revision(
        target_google_place_id="place-1", owner_competitors=["Hopscotch", "Hove Village"], engine=engine,
    )

    assert result["revision"] == 5 and result["supersedes_revision_id"] == "audit-1"
    assert json.loads(result["owner_competitors"]) == ["Hopscotch", "Hove Village"]
    assert result["benchmark_run_id"] == "run-1"  # the paid run stays attached
    assert json.loads(result["reviewer_decisions"]) == {
        "confirmed_target_names": ["WRAP"], "approved_recommendations": [{"id": "a1"}],
    }  # nothing already decided is lost
    assert result["reviewer_decisions_complete"] is False  # the new name still needs a decision
    assert json.loads(result["owner_context"]) == {"priority_services": ["Nursery places"]}


def test_duplicate_and_blank_competitor_names_are_tidied_up():
    engine = Engine({
        "id": "audit-1", "revision": 1, "target_business_name": "WRAP", "known_for": "Coworking",
        "desired_searches": [], "owner_competitors": [], "benchmark_run_id": None,
        "website_evidence_state": "not_checked", "review_evidence_state": "not_checked",
        "reviewer_decisions": {}, "owner_context": {}, "manual_website_url": None,
    })
    result = save_owner_competitors_revision(
        target_google_place_id="place-1",
        owner_competitors=["Hopscotch", "  ", "Hopscotch", "Hove Village "], engine=engine,
    )
    assert json.loads(result["owner_competitors"]) == ["Hopscotch", "Hove Village"]


def test_naming_a_competitor_before_any_brief_exists_is_refused():
    engine = Engine()
    try:
        save_owner_competitors_revision(target_google_place_id="place-1", owner_competitors=["Hopscotch"], engine=engine)
    except ValueError as exc:
        assert "Submit the report owner brief" in str(exc)
    else:
        raise AssertionError("A competitor was accepted with no brief to attach it to")
