from __future__ import annotations

import os
import threading
import time
import unittest
import uuid
from datetime import date
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb
from sqlalchemy import create_engine

from src.poc_audit_payload import payload_sha256
from src.poc_audit_repository import (
    SnapshotMetadata,
    create_snapshot,
)
from tests.test_poc_audit_payload import payload as base_payload


DATABASE_URL = os.getenv("POC_AUDIT_TEST_DATABASE_URL")


@unittest.skipUnless(
    DATABASE_URL,
    "POC_AUDIT_TEST_DATABASE_URL is not configured",
)
class PocAuditPostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.connection = psycopg.connect(DATABASE_URL)
        cls.connection.autocommit = True
        cls.connection.execute(
            """
            create table public.ai_visibility_runs (
                id uuid primary key
            )
            """
        )
        migration = Path(
            "sql/001_create_poc_audit_snapshots.sql"
        ).read_text(encoding="utf-8")
        cls.connection.execute(migration)

    @classmethod
    def tearDownClass(cls):
        cls.connection.close()

    def _new_run(self) -> str:
        run_id = str(uuid.uuid4())
        self.connection.execute(
            "insert into ai_visibility_runs (id) values (%s)",
            (run_id,),
        )
        return run_id

    @staticmethod
    def _payload(
        run_id: str,
        *,
        revision: int = 1,
        supersedes: str | None = None,
        target: str = "synthetic-place-id",
    ) -> dict:
        return {
            "schema_version": "poc_audit_v1",
            "audit": {
                "baseline_run_id": run_id,
                "target_google_place_id": target,
                "target_business_name": "Synthetic Test Business",
                "audit_date": "2026-08-25",
            },
            "revision": {
                "snapshot_revision": revision,
                "supersedes_snapshot_id": supersedes,
                "revision_reason": (
                    "Original synthetic test"
                    if revision == 1
                    else "Synthetic correction"
                ),
            },
        }

    @staticmethod
    def _parameters(
        run_id: str,
        *,
        revision: int = 1,
        supersedes: str | None = None,
        snapshot_id: str | None = None,
        payload: dict | None = None,
        payload_hash: str = "a" * 64,
        pdf_hash: str = "b" * 64,
        pdf_bytes: bytes = b"%PDF-1.7\nsynthetic\n%%EOF",
    ) -> dict:
        return {
            "id": snapshot_id or str(uuid.uuid4()),
            "schema_version": "poc_audit_v1",
            "ai_run_id": run_id,
            "snapshot_revision": revision,
            "supersedes_snapshot_id": supersedes,
            "revision_reason": (
                "Original synthetic test"
                if revision == 1
                else "Synthetic correction"
            ),
            "target_google_place_id": "synthetic-place-id",
            "target_business_name": "Synthetic Test Business",
            "audit_date": date(2026, 8, 25),
            "report_payload": Jsonb(
                payload
                if payload is not None
                else PocAuditPostgresIntegrationTests._payload(
                    run_id,
                    revision=revision,
                    supersedes=supersedes,
                )
            ),
            "report_payload_sha256": payload_hash,
            "pdf_bytes": pdf_bytes,
            "pdf_sha256": pdf_hash,
            "pdf_filename": "synthetic.pdf",
            "frozen_by": "integration-test",
        }

    INSERT = """
        insert into public.poc_audit_snapshots (
            id, schema_version, ai_run_id, snapshot_revision,
            supersedes_snapshot_id, revision_reason,
            target_google_place_id, target_business_name, audit_date,
            report_payload, report_payload_sha256, pdf_bytes,
            pdf_sha256, pdf_filename, frozen_by
        ) values (
            %(id)s, %(schema_version)s, %(ai_run_id)s,
            %(snapshot_revision)s, %(supersedes_snapshot_id)s,
            %(revision_reason)s, %(target_google_place_id)s,
            %(target_business_name)s, %(audit_date)s,
            %(report_payload)s, %(report_payload_sha256)s,
            %(pdf_bytes)s, %(pdf_sha256)s, %(pdf_filename)s,
            %(frozen_by)s
        )
        returning id
    """

    def _insert(self, parameters: dict) -> str:
        return str(
            self.connection.execute(
                self.INSERT,
                parameters,
            ).fetchone()[0]
        )

    def _assert_rejected(self, parameters: dict):
        with self.assertRaises(psycopg.Error):
            with psycopg.connect(DATABASE_URL) as connection:
                connection.execute(self.INSERT, parameters)

    def test_schema_objects_created_by_literal_migration(self):
        version = self.connection.execute(
            "select version()"
        ).fetchone()[0]
        self.assertIn("PostgreSQL 13.3", version)

        constraints = {
            row[0]
            for row in self.connection.execute(
                """
                select conname
                from pg_constraint
                where conrelid = 'public.poc_audit_snapshots'::regclass
                """
            )
        }
        self.assertIn("poc_audit_snapshots_ai_run_fk", constraints)
        self.assertIn(
            "poc_audit_snapshots_supersedes_same_run_fk",
            constraints,
        )
        self.assertIn(
            "poc_audit_snapshots_run_revision_key",
            constraints,
        )

        functions = {
            row[0]
            for row in self.connection.execute(
                """
                select proname
                from pg_proc
                join pg_namespace on pg_namespace.oid = pronamespace
                where nspname = 'public'
                and proname like '%poc_audit_snapshot%'
                """
            )
        }
        self.assertEqual(
            functions,
            {
                "enforce_poc_audit_snapshot_lineage",
                "prevent_poc_audit_snapshot_mutation",
            },
        )

        triggers = {
            row[0]
            for row in self.connection.execute(
                """
                select tgname
                from pg_trigger
                where tgrelid = 'public.poc_audit_snapshots'::regclass
                and not tgisinternal
                """
            )
        }
        self.assertEqual(
            triggers,
            {
                "poc_audit_snapshots_lineage_before_insert",
                "poc_audit_snapshots_immutable_before_change",
            },
        )

        indexes = {
            row[0]
            for row in self.connection.execute(
                """
                select indexname
                from pg_indexes
                where schemaname = 'public'
                and tablename = 'poc_audit_snapshots'
                """
            )
        }
        self.assertIn("poc_audit_snapshots_target_frozen_idx", indexes)
        self.assertIn("poc_audit_snapshots_supersedes_idx", indexes)

    def test_revision_one_duplicate_and_valid_revision_two(self):
        run_id = self._new_run()
        revision_one = self._parameters(run_id)
        first_id = self._insert(revision_one)

        self._assert_rejected(self._parameters(run_id))

        revision_two = self._parameters(
            run_id,
            revision=2,
            supersedes=first_id,
        )
        self._insert(revision_two)
        rows = self.connection.execute(
            """
            select snapshot_revision, supersedes_snapshot_id
            from poc_audit_snapshots
            where ai_run_id = %s
            order by snapshot_revision
            """,
            (run_id,),
        ).fetchall()
        self.assertEqual([row[0] for row in rows], [1, 2])
        self.assertEqual(str(rows[1][1]), first_id)

    def test_repository_insert_path_against_postgresql(self):
        run_id = self._new_run()
        candidate = base_payload()
        candidate["audit"].update(
            {
                "baseline_run_id": run_id,
                "target_business_name": "Synthetic Test Business",
                "audit_date": "2026-08-25",
            }
        )
        engine = create_engine(
            DATABASE_URL.replace(
                "postgresql://",
                "postgresql+psycopg://",
                1,
            )
        )
        try:
            inserted = create_snapshot(
                payload=candidate,
                expected_payload_sha256=payload_sha256(candidate),
                pdf_bytes=b"%PDF-1.7\nsynthetic\n%%EOF",
                metadata=SnapshotMetadata(
                    ai_run_id=run_id,
                    snapshot_revision=1,
                    supersedes_snapshot_id=None,
                    revision_reason="Original audit",
                    target_google_place_id="canonical-place-1",
                    target_business_name="Synthetic Test Business",
                    audit_date=date(2026, 8, 25),
                    frozen_by="integration-test",
                    pdf_filename="synthetic.pdf",
                ),
                engine=engine,
            )
        finally:
            engine.dispose()

        stored = self.connection.execute(
            """
            select report_payload_sha256, pdf_sha256,
                   octet_length(pdf_bytes)
            from poc_audit_snapshots
            where id = %s
            """,
            (inserted["id"],),
        ).fetchone()
        self.assertEqual(stored[0], payload_sha256(candidate))
        self.assertEqual(stored[1], inserted["pdf_sha256"])
        self.assertGreater(stored[2], 0)

    def test_skipped_revision_and_wrong_parent_are_rejected(self):
        run_id = self._new_run()
        first_id = self._insert(self._parameters(run_id))
        self._assert_rejected(
            self._parameters(
                run_id,
                revision=3,
                supersedes=first_id,
            )
        )
        self._assert_rejected(
            self._parameters(
                run_id,
                revision=2,
                supersedes=str(uuid.uuid4()),
            )
        )

    def test_cross_run_supersession_is_rejected(self):
        first_run = self._new_run()
        first_id = self._insert(self._parameters(first_run))
        second_run = self._new_run()
        self._insert(self._parameters(second_run))
        self._assert_rejected(
            self._parameters(
                second_run,
                revision=2,
                supersedes=first_id,
            )
        )

    def test_missing_payload_correspondence_fields_are_rejected(self):
        paths = [
            ("schema_version",),
            ("audit", "baseline_run_id"),
            ("audit", "target_google_place_id"),
            ("audit", "target_business_name"),
            ("audit", "audit_date"),
            ("revision", "snapshot_revision"),
            ("revision", "revision_reason"),
        ]
        for path in paths:
            with self.subTest(path=path):
                run_id = self._new_run()
                payload = self._payload(run_id)
                if len(path) == 1:
                    payload.pop(path[0])
                else:
                    payload[path[0]].pop(path[1])
                self._assert_rejected(
                    self._parameters(run_id, payload=payload)
                )

    def test_payload_correspondence_mismatches_are_rejected(self):
        changes = [
            ("run", lambda value: value["audit"].update(
                baseline_run_id=str(uuid.uuid4())
            )),
            ("target", lambda value: value["audit"].update(
                target_google_place_id="wrong-target"
            )),
            ("revision", lambda value: value["revision"].update(
                snapshot_revision=2
            )),
        ]
        for label, change in changes:
            with self.subTest(label=label):
                run_id = self._new_run()
                payload = self._payload(run_id)
                change(payload)
                self._assert_rejected(
                    self._parameters(run_id, payload=payload)
                )

    def test_malformed_hashes_and_empty_pdf_are_rejected(self):
        cases = [
            {"payload_hash": "not-a-hash"},
            {"pdf_hash": "not-a-hash"},
            {"pdf_bytes": b""},
        ]
        for values in cases:
            with self.subTest(values=values):
                run_id = self._new_run()
                self._assert_rejected(
                    self._parameters(run_id, **values)
                )

    def test_update_and_delete_are_rejected(self):
        run_id = self._new_run()
        snapshot_id = self._insert(self._parameters(run_id))
        with self.assertRaises(psycopg.Error):
            with psycopg.connect(DATABASE_URL) as connection:
                connection.execute(
                    """
                    update poc_audit_snapshots
                    set target_business_name = 'Changed'
                    where id = %s
                    """,
                    (snapshot_id,),
                )
        with self.assertRaises(psycopg.Error):
            with psycopg.connect(DATABASE_URL) as connection:
                connection.execute(
                    "delete from poc_audit_snapshots where id = %s",
                    (snapshot_id,),
                )
        count = self.connection.execute(
            "select count(*) from poc_audit_snapshots where id = %s",
            (snapshot_id,),
        ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_failed_insert_rolls_back_without_partial_snapshot(self):
        run_id = self._new_run()
        parameters = self._parameters(run_id, pdf_bytes=b"")
        self._assert_rejected(parameters)
        count = self.connection.execute(
            "select count(*) from poc_audit_snapshots where ai_run_id = %s",
            (run_id,),
        ).fetchone()[0]
        self.assertEqual(count, 0)

    def test_direct_sql_concurrent_next_revision_is_serialized(self):
        run_id = self._new_run()
        first_id = self._insert(self._parameters(run_id))
        winner = self._parameters(
            run_id,
            revision=2,
            supersedes=first_id,
        )
        loser = self._parameters(
            run_id,
            revision=2,
            supersedes=first_id,
        )
        outcome: dict[str, object] = {}
        started = threading.Event()

        def competing_insert():
            try:
                with psycopg.connect(DATABASE_URL) as connection:
                    connection.execute("set statement_timeout = '5s'")
                    started.set()
                    connection.execute(self.INSERT, loser)
                outcome["result"] = "unexpected-success"
            except psycopg.Error as exc:
                outcome["error"] = exc

        first_connection = psycopg.connect(DATABASE_URL)
        first_connection.execute(self.INSERT, winner)
        thread = threading.Thread(target=competing_insert)
        thread.start()
        self.assertTrue(started.wait(timeout=2))
        time.sleep(0.25)
        self.assertTrue(
            thread.is_alive(),
            "Competing insert did not wait for the advisory lock",
        )
        first_connection.commit()
        first_connection.close()
        thread.join(timeout=5)

        self.assertFalse(thread.is_alive())
        self.assertIn("error", outcome)
        self.assertNotIn("result", outcome)
        rows = self.connection.execute(
            """
            select snapshot_revision
            from poc_audit_snapshots
            where ai_run_id = %s
            order by snapshot_revision
            """,
            (run_id,),
        ).fetchall()
        self.assertEqual([row[0] for row in rows], [1, 2])


if __name__ == "__main__":
    unittest.main()
