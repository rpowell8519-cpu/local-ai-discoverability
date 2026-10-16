"""Reads and writes for the client account area (beta). See src/client_account.py.

Loading never writes. The writers (`create_client_account`, `add_member`, `remove_member`,
`publish_test`, `publish_report`, `withdraw`) are explicit, each one statement or transaction, and
need sql/20261016120000_client_accounts.sql applied; `stores_ready` says whether it is.
"""
from __future__ import annotations

import json
from typing import Any, Iterable, Mapping

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID

from src.client_account import VERSION, clean
from src.database import get_engine

STORES = ("client_accounts", "client_account_members", "client_account_tests", "client_account_reports")


def stores_ready(*, engine=None) -> bool:
    with (engine or get_engine()).connect() as connection:
        return all(connection.execute(text("select to_regclass('public.' || :n) is not null"), {"n": n}).scalar_one() for n in STORES)


def load_answers(run_ids: Iterable[str], *, engine=None) -> list[dict[str, Any]]:
    """Completed and failed answers of the given runs, with the prompt each answered. Run order is kept."""
    run_ids = list(dict.fromkeys(str(r) for r in run_ids))
    with (engine or get_engine()).connect() as connection:
        rows = connection.execute(text("""
            select res.run_id::text, q.prompt_text, q.base_prompt_order, res.provider, res.model, res.status,
                   res.response_complete, res.raw_response, res.report_metadata
            from ai_visibility_results res join ai_visibility_queries q on q.id = res.query_id
            where res.run_id = any(:runs)
            order by q.base_prompt_order, q.repeat_index, res.provider
        """).bindparams(bindparam("runs", type_=ARRAY(UUID(as_uuid=False)))), {"runs": run_ids}).mappings().all()
    return [{**row, "run_order": run_ids.index(row["run_id"])} for row in rows]


def load_runs(place_id: str, *, engine=None) -> list[dict[str, Any]]:
    """The business's completed runs, newest first, with the number of completed answers and prompts."""
    with (engine or get_engine()).connect() as connection:
        return [dict(row) for row in connection.execute(text("""
            select r.id::text as run_id, r.created_at, r.models, count(distinct q.base_prompt_order) as prompts,
                   count(res.id) filter (where res.status = 'completed') as answers
            from ai_visibility_runs r
            join ai_visibility_queries q on q.run_id = r.id
            left join ai_visibility_results res on res.query_id = q.id
            where r.target_google_place_id = :place and r.status = 'completed'
            group by r.id order by r.created_at desc
        """), {"place": place_id}).mappings()]


def load_reviewed_names(place_id: str, *, engine=None) -> list[str]:
    """The client names confirmed in the business's latest complete report review, to start the first test from."""
    with (engine or get_engine()).connect() as connection:
        row = connection.execute(text("""
            select reviewer_decisions -> 'confirmed_target_names' as names from report_audit_revisions
            where target_google_place_id = :place and reviewer_decisions_complete
            order by created_at desc, revision desc limit 1
        """), {"place": place_id}).mappings().first()
        business = connection.execute(text("select business_name from business_features where google_place_id = :place"),
                                      {"place": place_id}).scalar()
    return [n for n in dict.fromkeys([clean(business), *map(clean, (row or {}).get("names") or [])]) if n]


def list_client_accounts(*, engine=None) -> list[dict[str, Any]]:
    with (engine or get_engine()).connect() as connection:
        return [dict(row) for row in connection.execute(text(
            "select id::text, slug, name, services, next_test_note from client_accounts order by name")).mappings()]


def list_members(client_id: str, *, engine=None) -> list[dict[str, Any]]:
    with (engine or get_engine()).connect() as connection:
        return [dict(row) for row in connection.execute(text("""
            select id::text, email, display_name, added_by, added_at from client_account_members
            where client_id = :c and removed_at is null order by added_at"""), {"c": client_id}).mappings()]


def list_tests(client_id: str, *, engine=None) -> list[dict[str, Any]]:
    """Published tests, newest first, withdrawn ones included and marked."""
    with (engine or get_engine()).connect() as connection:
        return [dict(row) for row in connection.execute(text("""
            select id::text, service, google_place_id, tested_on, run_ids::text[] as run_ids, payload, decisions, note,
                   published_by, published_at, withdrawn_at
            from client_account_tests where client_id = :c order by tested_on desc, published_at desc"""), {"c": client_id}).mappings()]


def list_reports(client_id: str, *, engine=None) -> list[dict[str, Any]]:
    with (engine or get_engine()).connect() as connection:
        return [dict(row) for row in connection.execute(text("""
            select id::text, service, title, report_date, file_name, octet_length(pdf_bytes) as size, published_at, withdrawn_at
            from client_account_reports where client_id = :c order by report_date desc"""), {"c": client_id}).mappings()]


def latest_decisions(client_id: str, service: str, *, engine=None) -> dict[str, Any] | None:
    """The decisions saved with the service's most recent published test, withdrawn or not."""
    with (engine or get_engine()).connect() as connection:
        return connection.execute(text("""
            select decisions from client_account_tests where client_id = :c and service = :s
            order by tested_on desc, published_at desc limit 1"""), {"c": client_id, "s": service}).scalar()


def create_client_account(slug: str, name: str, services: list[dict[str, str]], *, engine=None) -> str:
    with (engine or get_engine()).begin() as connection:
        return connection.execute(text("""
            insert into client_accounts (slug, name, services) values (:slug, :name, cast(:services as jsonb)) returning id::text
        """), {"slug": slug, "name": clean(name), "services": json.dumps(services)}).scalar_one()


def set_next_test_note(client_id: str, note: str, *, engine=None) -> None:
    with (engine or get_engine()).begin() as connection:
        connection.execute(text("update client_accounts set next_test_note = :n, updated_at = now() where id = :c"),
                           {"n": clean(note) or None, "c": client_id})


def add_member(client_id: str, email: str, display_name: str, added_by: str, *, engine=None) -> None:
    with (engine or get_engine()).begin() as connection:
        connection.execute(text("""
            insert into client_account_members (client_id, email, display_name, added_by) values (:c, :e, :d, :b)
        """), {"c": client_id, "e": email.strip().lower(), "d": clean(display_name) or None, "b": clean(added_by)})


def remove_member(member_id: str, *, engine=None) -> None:
    with (engine or get_engine()).begin() as connection:
        connection.execute(text("update client_account_members set removed_at = now() where id = :m and removed_at is null"),
                           {"m": member_id})


def publish_test(client_id: str, service: str, place_id: str, run_ids: list[str], payload: Mapping[str, Any],
                 decisions: Mapping[str, Any], note: str, published_by: str, *, engine=None) -> str:
    """Publish one test day. An earlier published copy of the same day is withdrawn in the same transaction."""
    with (engine or get_engine()).begin() as connection:
        connection.execute(text("""
            update client_account_tests set withdrawn_at = now()
            where client_id = :c and service = :s and tested_on = :d and withdrawn_at is null
        """), {"c": client_id, "s": service, "d": payload["tested_on"]})
        return connection.execute(text("""
            insert into client_account_tests (client_id, service, google_place_id, tested_on, run_ids, payload,
                payload_version, decisions, note, published_by)
            values (:c, :s, :p, :d, cast(:runs as uuid[]), cast(:payload as jsonb), :v, cast(:decisions as jsonb), :n, :b)
            returning id::text
        """), {"c": client_id, "s": service, "p": place_id, "d": payload["tested_on"], "runs": "{" + ",".join(run_ids) + "}",
               "payload": json.dumps(payload), "v": VERSION, "decisions": json.dumps(decisions),
               "n": clean(note) or None, "b": clean(published_by)}).scalar_one()


def publish_report(client_id: str, service: str, title: str, report_date: str, file_name: str, pdf: bytes,
                   published_by: str, *, engine=None) -> str:
    with (engine or get_engine()).begin() as connection:
        return connection.execute(text("""
            insert into client_account_reports (client_id, service, title, report_date, file_name, pdf_bytes, published_by)
            values (:c, :s, :t, :d, :f, :pdf, :b) returning id::text
        """), {"c": client_id, "s": service, "t": clean(title), "d": report_date, "f": file_name, "pdf": pdf,
               "b": clean(published_by)}).scalar_one()


def withdraw(table: str, row_id: str, *, engine=None) -> None:
    if table not in ("client_account_tests", "client_account_reports"):
        raise ValueError(table)
    with (engine or get_engine()).begin() as connection:
        connection.execute(text(f"update {table} set withdrawn_at = now() where id = :i and withdrawn_at is null"), {"i": row_id})
