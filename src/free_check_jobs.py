"""Durable job queue for customer free checks (public.visibility_jobs / public.customer_checks).

Every function takes an open connection inside a transaction owned by the caller. A job is leased to
one worker at a time; an expired lease can be reclaimed, and attempts are bounded. A job that already
has a run keeps its claim on that run, so a retry only repeats the calls that are still missing.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

LEASE_SECONDS = 600
RETRY_DELAY_SECONDS = 120
DAILY_NEW_CHECK_CAP = 10


FAIL_EXHAUSTED_SQL = """
        update public.visibility_jobs
        set state='failed', lease_owner=null, lease_expires_at=null, completed_at=now(),
            last_error=coalesce(last_error, 'Attempts exhausted')
        where attempt_count >= max_attempts
          and (state='queued' or (state='leased' and lease_expires_at < now()))
        returning check_id
    """
FAIL_EXHAUSTED_CHECKS_SQL = """
            update public.customer_checks set status='failed', error_code='attempts_exhausted'
            where id = any(cast(:ids as uuid[])) and status in ('queued', 'running')
        """
STARTED_TODAY_SQL = """
        select count(*) from public.visibility_jobs j
        join public.ai_visibility_runs r on r.id = j.run_id
        where r.started_at >= date_trunc('day', now() at time zone 'Europe/London') at time zone 'Europe/London'
    """
CLAIM_SQL = """
        with candidate as (
            select id from public.visibility_jobs
            where attempt_count < max_attempts
              and ((state='queued' and next_attempt_at <= now())
                   or (state='leased' and lease_expires_at < now()))
              and (run_id is not null or :allow_new)
            order by (run_id is null), next_attempt_at, created_at
            for update skip locked
            limit 1
        )
        update public.visibility_jobs j
        set state='leased', lease_owner=:worker_id, heartbeat_at=now(),
            lease_expires_at=now() + make_interval(secs => :lease_seconds),
            attempt_count=j.attempt_count + 1
        from candidate where j.id = candidate.id
        returning j.*
    """
MARK_RUNNING_SQL = "update public.customer_checks set status='running' where id=:id and status='queued'"
LOAD_CHECK_SQL = "select * from public.customer_checks where id=:id"
ATTACH_RUN_SQL = """
        update public.visibility_jobs set run_id=:run_id
        where id=:id and state='leased' and lease_owner=:worker_id and run_id is null
    """
ATTACH_RUN_CHECK_SQL = """
        update public.customer_checks c set run_id=:run_id
        from public.visibility_jobs j where j.id=:id and c.id=j.check_id
    """
HEARTBEAT_SQL = """
        update public.visibility_jobs
        set heartbeat_at=now(), lease_expires_at=now() + make_interval(secs => :lease_seconds),
            completed_calls=:completed_calls
        where id=:id and state='leased' and lease_owner=:worker_id
    """
COMPLETE_JOB_SQL = """
        update public.visibility_jobs
        set state='succeeded', lease_owner=null, lease_expires_at=null, completed_at=now(),
            completed_calls=:completed_calls, last_error=null
        where id=:id and state='leased' and lease_owner=:worker_id
    """
COMPLETE_CHECK_SQL = """
        update public.customer_checks c
        set status=:status, result_projection=cast(:projection as jsonb),
            result_projection_version=:version,
            error_code=case when :status='partial' then 'some_answers_missing' else null end
        from public.visibility_jobs j where j.id=:id and c.id=j.check_id
    """
REPLACE_PROJECTION_SQL = """
        update public.customer_checks
        set result_projection=cast(:projection as jsonb), result_projection_version=:version
        where id=:id and status in ('completed', 'partial')
    """
RELEASE_SQL = """
        update public.visibility_jobs
        set state='queued', lease_owner=null, lease_expires_at=null,
            next_attempt_at=now() + make_interval(secs => :delay_seconds), last_error=:error
        where id=:id and state='leased' and lease_owner=:worker_id
    """


def fail_exhausted_jobs(connection) -> int:
    """Close jobs that used every attempt without finishing, and tell their checks."""
    check_ids = connection.execute(text(FAIL_EXHAUSTED_SQL)).scalars().all()
    if check_ids:
        connection.execute(text(FAIL_EXHAUSTED_CHECKS_SQL), {"ids": list(check_ids)})
    return len(check_ids)


def new_checks_started_today(connection) -> int:
    """Free checks whose paid run began today (Europe/London). Retries of a run are not new checks."""
    return int(connection.execute(text(STARTED_TODAY_SQL)).scalar_one())


def claim_next_job(connection, *, worker_id: str, lease_seconds: int = LEASE_SECONDS,
                   daily_cap: int = DAILY_NEW_CHECK_CAP) -> dict[str, Any] | None:
    """Lease the oldest runnable job, or return None. New runs stop once the daily cap is reached."""
    fail_exhausted_jobs(connection)
    allow_new = new_checks_started_today(connection) < daily_cap
    row = connection.execute(text(CLAIM_SQL), {"worker_id": worker_id, "lease_seconds": int(lease_seconds), "allow_new": allow_new}).mappings().first()
    if row is None:
        return None
    connection.execute(text(MARK_RUNNING_SQL),
                       {"id": row["check_id"]})
    return dict(row)


def load_check(connection, check_id: str) -> dict[str, Any]:
    return dict(connection.execute(text(LOAD_CHECK_SQL),
                                   {"id": check_id}).mappings().one())


def _owned(connection, sql: str, params: dict[str, Any]) -> None:
    """Run a job update that must still belong to this worker's lease."""
    if connection.execute(text(sql), params).rowcount != 1:
        raise RuntimeError("Job lease was lost; another worker may have reclaimed it")


def attach_run(connection, *, job_id: str, worker_id: str, run_id: str) -> None:
    """Record the paid run before any provider call, so a retry reuses it instead of starting again."""
    _owned(connection, ATTACH_RUN_SQL, {"id": job_id, "worker_id": worker_id, "run_id": run_id})
    connection.execute(text(ATTACH_RUN_CHECK_SQL), {"id": job_id, "run_id": run_id})


def heartbeat(connection, *, job_id: str, worker_id: str, completed_calls: int,
              lease_seconds: int = LEASE_SECONDS) -> None:
    _owned(connection, HEARTBEAT_SQL, {"id": job_id, "worker_id": worker_id, "completed_calls": int(completed_calls),
          "lease_seconds": int(lease_seconds)})


def complete_job(connection, *, job_id: str, worker_id: str, check_status: str,
                 projection: dict[str, Any], completed_calls: int) -> None:
    if check_status not in {"completed", "partial"}:
        raise ValueError("A delivered check is completed or partial")
    _owned(connection, COMPLETE_JOB_SQL, {"id": job_id, "worker_id": worker_id, "completed_calls": int(completed_calls)})
    connection.execute(text(COMPLETE_CHECK_SQL), {"id": job_id, "status": check_status, "version": projection["schema_version"],
           "projection": json.dumps(projection, ensure_ascii=False, allow_nan=False)})


def release_for_retry(connection, *, job_id: str, worker_id: str, error: str,
                      delay_seconds: int = RETRY_DELAY_SECONDS) -> None:
    """Hand the job back to the queue. fail_exhausted_jobs closes it once attempts run out."""
    _owned(connection, RELEASE_SQL, {"id": job_id, "worker_id": worker_id, "delay_seconds": int(delay_seconds),
          "error": str(error)[:500]})


def replace_projection(connection, *, check_id: str, projection: dict[str, Any]) -> None:
    """Swap a delivered check's summary for one rebuilt from the same saved answers."""
    if connection.execute(text(REPLACE_PROJECTION_SQL), {
            "id": check_id, "version": projection["schema_version"],
            "projection": json.dumps(projection, ensure_ascii=False, allow_nan=False)}).rowcount != 1:
        raise RuntimeError("Check is not delivered, so its summary was not replaced")
