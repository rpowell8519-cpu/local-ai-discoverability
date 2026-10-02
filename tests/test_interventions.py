"""Action records retain exact evidence and refuse guessed implementation or stale edits."""
from contextlib import contextmanager
from copy import deepcopy
from unittest.mock import patch

import pytest

from src.interventions import VERSION, new_action_id, validate_intervention
from src.intervention_repository import save_intervention, list_interventions
from src.positioning_triangulation import triangulate
from test_positioning_triangulation import inputs


def record():
    cap, _, _, _ = inputs()
    eid = cap["payload"]["matrix"]["observations"][0]["evidence_id"]
    return cap, {"version": VERSION, "action_id": new_action_id(), "google_place_id": "place",
        "proposition_key": "balayage", "capture_id": cap["id"], "finding": "Evidence needs review",
        "hypothesis": "Review the service page before deciding changes", "owner": "Operator",
        "effort": "Not yet estimated", "priority": "Not yet agreed", "status": "PLANNED",
        "created_by": "Reviewer", "revision_note": "Initial proposed investigation", "affected_evidence_ids": [eid],
        "finding_snapshot": triangulate(cap, []), "planned_date": None, "implemented_date": None,
        "completion_evidence": [], "focused_families": [], "baseline_run_id": None,
        "baseline_series_id": None, "approved_revision_id": None, "approved_action_id": None, "bundle_id": None}


def test_planned_action_preserves_unknown_baseline_dates_effort_and_approved_action():
    cap, value = record()
    assert validate_intervention(value, cap) == value
    assert value["baseline_series_id"] is None and value["implemented_date"] is None


@pytest.mark.parametrize("change", [
    {"google_place_id": "other"}, {"capture_id": "other"}, {"proposition_key": "invented"},
    {"affected_evidence_ids": ["invented"]}, {"affected_evidence_ids": []}, {"hypothesis": " "},
    {"owner": ""}, {"effort": ""}, {"revision_note": ""}, {"status": "unknown"}, {"priority": "urgent"},
    {"status": "IMPLEMENTED"}, {"implemented_date": "2099-01-01", "completion_evidence": ["https://example.org/proof"]},
    {"completion_evidence": ["file:///private/proof"]}, {"completion_evidence": ["https://user:secret@example.org"]},
    {"baseline_series_id": new_action_id()}, {"approved_action_id": "action-1"},
    {"focused_families": ["one", "one"]}, {"finding_snapshot": {}},
])
def test_invalid_or_untraceable_action_is_rejected(change):
    cap, value = record()
    with pytest.raises((ValueError, TypeError)):
        validate_intervention({**value, **change}, cap)


def test_real_completion_evidence_is_required_with_implementation_date():
    cap, value = record()
    value.update(status="IMPLEMENTED", implemented_date="2026-01-01", completion_evidence=["https://example.org/change"])
    assert validate_intervention(value, cap)["implemented_date"] == "2026-01-01"


def test_uuid_inputs_normalize_to_relational_uuid_rendering():
    cap, value = record()
    value['bundle_id'] = 'ABCDEF00-0000-0000-0000-000000000001'
    assert validate_intervention(value, cap)['bundle_id'] == value['bundle_id'].lower()


class Result:
    def __init__(self, row=None, scalar=None): self.row, self.scalar = row, scalar
    def mappings(self): return self
    def first(self): return self.row
    def scalar_one(self): return self.scalar


class Connection:
    def __init__(self, previous=None): self.previous, self.calls = previous, []
    def execute(self, statement, params=None):
        self.calls.append((str(statement), params))
        return Result(row=self.previous) if "select id,revision" in str(statement) else Result(scalar="saved")


class Engine:
    def __init__(self, connection): self.connection = connection
    @contextmanager
    def begin(self): yield self.connection


def test_missing_migration_exposes_no_writer_or_capture_read():
    cap, value = record()
    with patch('src.intervention_repository.intervention_storage_ready', return_value=False), patch('src.intervention_repository.load_capture') as reader:
        assert list_interventions("place", engine=object()) == []
        with pytest.raises(ValueError, match="separately approved"):
            save_intervention(value, engine=object())
        assert not reader.called


def test_append_revision_checks_stale_edits_before_insert():
    cap, value = record()
    conn = Connection(previous={"id": new_action_id(), "revision": 2})
    with patch('src.intervention_repository.intervention_storage_ready', return_value=True), patch('src.intervention_repository.load_capture', return_value=cap):
        with pytest.raises(ValueError, match="Reload"):
            save_intervention(value, expected_revision=1, engine=Engine(conn))
        assert not any("insert into" in sql for sql, _ in conn.calls)
        assert save_intervention(value, expected_revision=2, engine=Engine(conn)) == "saved"
        sql, parameters = conn.calls[-1]
        assert parameters["revision"] == 3 and parameters["supersedes_id"] == conn.previous["id"]
        assert "update " not in sql and "delete " not in sql
