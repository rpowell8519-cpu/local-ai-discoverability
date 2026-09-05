from __future__ import annotations

import copy
import unittest
import uuid
from datetime import date
from pathlib import Path

from sqlalchemy.exc import IntegrityError

from src.poc_audit_repository import (
    SnapshotConflictError,
    SnapshotMetadata,
    SnapshotPersistenceError,
    _validate_lineage,
    create_snapshot as repository_create_snapshot,
    get_snapshot,
    list_snapshots,
)
from src.poc_audit_payload import payload_sha256
from tests.test_poc_audit_payload import payload as base_payload


RUN_ID = "631f46d0-8361-47b0-aa8c-6e544de0eca3"
SNAPSHOT_1 = "10000000-0000-4000-8000-000000000001"
SNAPSHOT_2 = "10000000-0000-4000-8000-000000000002"
PDF = b"%PDF-1.7\nPOC audit\n%%EOF"


def create_snapshot(**kwargs):
    candidate = kwargs["payload"]
    return repository_create_snapshot(
        expected_payload_sha256=payload_sha256(candidate),
        **kwargs,
    )


def audit_payload(
    *,
    revision: int = 1,
    supersedes: str | None = None,
    reason: str = "Original audit",
) -> dict:
    candidate = base_payload()
    candidate["audit"].update(
        {
            "baseline_run_id": RUN_ID,
            "target_business_name": "Cisco's Karma",
            "audit_date": "2026-08-25",
        }
    )
    candidate["revision"] = {
        "snapshot_revision": revision,
        "supersedes_snapshot_id": supersedes,
        "revision_reason": reason,
    }
    return candidate


def metadata(
    *,
    revision: int = 1,
    supersedes: str | None = None,
    reason: str = "Original audit",
    snapshot_id: str = SNAPSHOT_1,
) -> SnapshotMetadata:
    return SnapshotMetadata(
        ai_run_id=RUN_ID,
        snapshot_revision=revision,
        supersedes_snapshot_id=supersedes,
        revision_reason=reason,
        target_google_place_id="canonical-place-1",
        target_business_name="Cisco's Karma",
        audit_date=date(2026, 8, 25),
        frozen_by="operator@example.test",
        pdf_filename="ciscos-karma-poc-audit.pdf",
        snapshot_id=snapshot_id,
    )


class FakeMappings:
    def __init__(self, *, first=None, one=None, all_rows=None):
        self._first = first
        self._one = one
        self._all = all_rows or []

    def first(self):
        return self._first

    def one(self):
        return self._one

    def all(self):
        return self._all


class FakeResult:
    def __init__(self, **kwargs):
        self.values = kwargs

    def mappings(self):
        return FakeMappings(**self.values)


class FakeConnection:
    def __init__(self, *, latest=None, fail_insert=False):
        self.latest = latest
        self.fail_insert = fail_insert
        self.calls = []
        self.insert_parameters = None

    def execute(self, statement, parameters=None):
        sql = str(statement)
        self.calls.append(sql)
        if "pg_advisory_xact_lock" in sql:
            return FakeResult()
        if "order by snapshot_revision desc" in sql:
            return FakeResult(first=self.latest)
        if "insert into poc_audit_snapshots" in sql:
            self.insert_parameters = parameters
            if self.fail_insert:
                raise IntegrityError(sql, parameters, Exception("conflict"))
            return FakeResult(
                one={
                    "id": parameters["id"],
                    "snapshot_revision": parameters[
                        "snapshot_revision"
                    ],
                    "report_payload_sha256": parameters[
                        "report_payload_sha256"
                    ],
                    "pdf_sha256": parameters["pdf_sha256"],
                }
            )
        raise AssertionError(f"Unexpected SQL: {sql}")


class FakeTransaction:
    def __init__(self, engine):
        self.engine = engine

    def __enter__(self):
        return self.engine.connection

    def __exit__(self, exception_type, exception, traceback):
        if exception_type is None:
            self.engine.committed = True
        else:
            self.engine.rolled_back = True
        return False


class FakeEngine:
    def __init__(self, *, latest=None, fail_insert=False):
        self.connection = FakeConnection(
            latest=latest,
            fail_insert=fail_insert,
        )
        self.committed = False
        self.rolled_back = False

    def begin(self):
        return FakeTransaction(self)


class FakeReadConnection:
    def __init__(self, rows):
        self.rows = rows
        self.parameters = None

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        return False

    def execute(self, statement, parameters=None):
        self.parameters = parameters
        return FakeResult(
            first=(self.rows[0] if self.rows else None),
            all_rows=self.rows,
        )


class FakeReadEngine:
    def __init__(self, rows):
        self.connection = FakeReadConnection(rows)

    def connect(self):
        return self.connection


class PocAuditRepositoryTests(unittest.TestCase):
    def test_list_query_types_optional_place_id_parameter(self):
        from src.poc_audit_repository import _LIST

        sql = str(_LIST)
        self.assertIn(
            "cast(:target_google_place_id as text) is null",
            sql,
        )
        self.assertIn(
            "target_google_place_id = cast(:target_google_place_id as text)",
            sql,
        )

    def test_revision_one_is_inserted_atomically(self):
        engine = FakeEngine()
        result = create_snapshot(
            payload=audit_payload(),
            pdf_bytes=PDF,
            metadata=metadata(),
            engine=engine,
        )
        self.assertTrue(engine.committed)
        self.assertFalse(engine.rolled_back)
        self.assertEqual(result["id"], SNAPSHOT_1)
        self.assertEqual(
            engine.connection.insert_parameters["pdf_bytes"], PDF
        )
        self.assertIn(
            "pg_advisory_xact_lock",
            engine.connection.calls[0],
        )

    def test_duplicate_revision_one_is_rejected_without_insert(self):
        engine = FakeEngine(
            latest={"id": SNAPSHOT_1, "snapshot_revision": 1}
        )
        with self.assertRaises(SnapshotConflictError):
            create_snapshot(
                payload=audit_payload(),
                pdf_bytes=PDF,
                metadata=metadata(),
                engine=engine,
            )
        self.assertTrue(engine.rolled_back)
        self.assertIsNone(engine.connection.insert_parameters)

    def test_valid_revision_two_requires_latest_parent(self):
        engine = FakeEngine(
            latest={"id": SNAPSHOT_1, "snapshot_revision": 1}
        )
        result = create_snapshot(
            payload=audit_payload(
                revision=2,
                supersedes=SNAPSHOT_1,
                reason="Corrected evidence label",
            ),
            pdf_bytes=PDF,
            metadata=metadata(
                revision=2,
                supersedes=SNAPSHOT_1,
                reason="Corrected evidence label",
                snapshot_id=SNAPSHOT_2,
            ),
            engine=engine,
        )
        self.assertEqual(result["snapshot_revision"], 2)

    def test_wrong_parent_is_rejected(self):
        wrong = "20000000-0000-4000-8000-000000000002"
        engine = FakeEngine(
            latest={"id": SNAPSHOT_1, "snapshot_revision": 1}
        )
        with self.assertRaises(SnapshotConflictError):
            create_snapshot(
                payload=audit_payload(
                    revision=2,
                    supersedes=wrong,
                    reason="Correction",
                ),
                pdf_bytes=PDF,
                metadata=metadata(
                    revision=2,
                    supersedes=wrong,
                    reason="Correction",
                    snapshot_id=SNAPSHOT_2,
                ),
                engine=engine,
            )

    def test_skipped_revision_is_rejected(self):
        with self.assertRaises(SnapshotConflictError):
            _validate_lineage(
                latest={"id": SNAPSHOT_1, "snapshot_revision": 1},
                metadata=metadata(
                    revision=3,
                    supersedes=SNAPSHOT_1,
                    reason="Correction",
                ),
            )

    def test_payload_metadata_mismatch_never_opens_transaction(self):
        engine = FakeEngine()
        changed = audit_payload()
        changed["audit"]["target_business_name"] = "Wrong business"
        with self.assertRaises(SnapshotPersistenceError):
            create_snapshot(
                payload=changed,
                pdf_bytes=PDF,
                metadata=metadata(),
                engine=engine,
            )
        self.assertFalse(engine.committed)
        self.assertFalse(engine.rolled_back)
        self.assertEqual(engine.connection.calls, [])

    def test_invalid_payload_hash_evidence_never_writes(self):
        engine = FakeEngine()
        changed = copy.deepcopy(audit_payload())
        changed["baseline_validation"]["responses"][0][
            "raw_response"
        ] += " tampered"
        with self.assertRaises(ValueError):
            create_snapshot(
                payload=changed,
                pdf_bytes=PDF,
                metadata=metadata(),
                engine=engine,
            )
        self.assertEqual(engine.connection.calls, [])

    def test_empty_or_invalid_pdf_never_writes(self):
        for invalid in (b"", b"not a PDF", b"%PDF-1.7 without EOF"):
            with self.subTest(invalid=invalid):
                engine = FakeEngine()
                with self.assertRaises(SnapshotPersistenceError):
                    create_snapshot(
                        payload=audit_payload(),
                        pdf_bytes=invalid,
                        metadata=metadata(),
                        engine=engine,
                    )
                self.assertEqual(engine.connection.calls, [])

    def test_integrity_conflict_rolls_back_and_fails_safely(self):
        engine = FakeEngine(fail_insert=True)
        with self.assertRaises(SnapshotConflictError):
            create_snapshot(
                payload=audit_payload(),
                pdf_bytes=PDF,
                metadata=metadata(),
                engine=engine,
            )
        self.assertTrue(engine.rolled_back)
        self.assertFalse(engine.committed)

    def test_unapproved_payload_hash_never_writes(self):
        engine = FakeEngine()
        with self.assertRaises(SnapshotPersistenceError):
            repository_create_snapshot(
                payload=audit_payload(),
                expected_payload_sha256="0" * 64,
                pdf_bytes=PDF,
                metadata=metadata(),
                engine=engine,
            )
        self.assertEqual(engine.connection.calls, [])

    def test_migration_defends_lineage_and_immutability(self):
        migration = Path(
            "sql/001_create_poc_audit_snapshots.sql"
        ).read_text(encoding="utf-8")
        required = [
            "unique (ai_run_id, snapshot_revision)",
            "supersedes_same_run_fk",
            "perform pg_advisory_xact_lock",
            "latest_revision + 1",
            "new.supersedes_snapshot_id is distinct from latest_snapshot_id",
            "before update or delete",
            "POC audit snapshots are immutable",
            "payload_run_check",
            "payload_target_check",
            "payload_revision_check",
            "payload_hash_check",
            "pdf_bytes_check",
            "is not distinct from ai_run_id::text",
        ]
        for fragment in required:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, migration)

    def test_get_snapshot_exposes_frozen_record(self):
        row = {"id": SNAPSHOT_1, "pdf_bytes": PDF}
        engine = FakeReadEngine([row])
        self.assertEqual(
            get_snapshot(SNAPSHOT_1, engine=engine),
            row,
        )

    def test_list_snapshots_exposes_metadata_rows(self):
        rows = [
            {"id": SNAPSHOT_2, "snapshot_revision": 2},
            {"id": SNAPSHOT_1, "snapshot_revision": 1},
        ]
        engine = FakeReadEngine(rows)
        self.assertEqual(
            list_snapshots(ai_run_id=RUN_ID, engine=engine),
            rows,
        )
        self.assertEqual(
            engine.connection.parameters["ai_run_id"],
            RUN_ID,
        )


if __name__ == "__main__":
    unittest.main()
