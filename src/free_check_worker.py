"""Background worker that executes customer free checks.

Run with:  python -m src.free_check_worker                     (poll forever)
           python -m src.free_check_worker --once              (process at most one job, then exit)
           python -m src.free_check_worker --reproject <id>    (rebuild a saved summary; no calls)

It makes paid provider calls. It reuses the same run creation, call execution, recommendation
parsing and name resolution as the operator AI Discovery Scan, so a free check measures exactly
what an operator scan measures; only the customer-safe summary is new. Runs are recorded with the
free_check panel kind, which core_run_filter keeps out of canonical reports and benchmarks.

Required environment: DATABASE_URL, OPENAI_API_KEY, ANTHROPIC_API_KEY, GEMINI_API_KEY.
Optional: OPENAI_MODEL, ANTHROPIC_MODEL, GEMINI_MODEL, FREE_CHECK_DAILY_CAP.
"""
from __future__ import annotations

import argparse
import logging
import os
import socket
import time
from typing import Any

import pandas as pd
from sqlalchemy import text

from src import free_check_jobs as jobs
from src.ai_discovery_repository import create_discovery_run
from src.ai_enrichment_repository import load_entity_aliases
from src.ai_recommendation_intelligence import build_recommendation_records
from src.ai_visibility_repository import (create_visibility_queries, get_run_queries, get_run_results,
                                          get_visibility_run)
from src.ai_visibility_runner import build_retry_plan, execute_calls, finalise_run_from_results
from src.database import get_engine
from src.free_check_projection import build_projection

log = logging.getLogger("free_check_worker")

PROVIDERS = ["OpenAI", "Claude", "Gemini"]
# Same defaults as the operator pages; override per environment without a code change.
DEFAULT_MODELS = {"OpenAI": "gpt-5.6-terra", "Claude": "claude-sonnet-5", "Gemini": "gemini-3.6-flash"}
KEY_NAMES = {"OpenAI": "OPENAI_API_KEY", "Claude": "ANTHROPIC_API_KEY", "Gemini": "GEMINI_API_KEY"}
MODEL_NAMES = {"OpenAI": "OPENAI_MODEL", "Claude": "ANTHROPIC_MODEL", "Gemini": "GEMINI_MODEL"}
BENCHMARK_MODE = "search_grounded"
PRIMARY_GROUP = "unclassified"
POLL_SECONDS = 5


def load_settings(environ=os.environ) -> dict[str, Any]:
    api_keys = {p: str(environ.get(KEY_NAMES[p]) or "").strip() for p in PROVIDERS}
    missing = [KEY_NAMES[p] for p in PROVIDERS if not api_keys[p]]
    if missing:
        raise RuntimeError("Missing provider keys: " + ", ".join(missing))
    return {"api_keys": api_keys,
            "models": {p: str(environ.get(MODEL_NAMES[p]) or DEFAULT_MODELS[p]) for p in PROVIDERS},
            "daily_cap": int(environ.get("FREE_CHECK_DAILY_CAP") or jobs.DAILY_NEW_CHECK_CAP)}


def _prompts(check: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"prompt": q, "source": "customer_free_check", "category": "free_check"} for q in check["questions"]]


def _directory(engine, target_id: str, business_name: str) -> pd.DataFrame:
    with engine.connect() as connection:
        rows = connection.execute(text(
            "select google_place_id, business_name, primary_group, business_format from business_features"
        )).mappings().all()
    stub = {"google_place_id": target_id, "business_name": business_name,
            "primary_group": PRIMARY_GROUP, "business_format": None}
    return pd.concat([pd.DataFrame(rows), pd.DataFrame([stub])], ignore_index=True)


def project_saved_run(check: dict[str, Any], *, run_id: str, engine) -> dict[str, Any]:
    """Build the customer-safe summary from a run's saved answers. Makes no provider calls."""
    business_name = check["business_name"].strip()
    run = get_visibility_run(run_id)
    target_id = str(run["target_google_place_id"])
    results = get_run_results(run_id)
    recommendations = build_recommendation_records(
        results=results, businesses=_directory(engine, target_id, business_name),
        aliases=load_entity_aliases(), target_google_place_id=target_id,
        commercial_competitor_ids=set(), primary_group=PRIMARY_GROUP)
    return build_projection(
        business_name=business_name, questions=list(check["questions"]), providers=PROVIDERS,
        queries=get_run_queries(run_id).to_dict("records"), results=results.to_dict("records"),
        recommendations=recommendations.to_dict("records"), target_id=target_id,
        measured_at=str(run.get("completed_at") or run.get("started_at") or ""),
        benchmark_mode=BENCHMARK_MODE)


def reproject_check(check_id: str, *, engine=None, save: bool = True) -> dict[str, Any]:
    """Rebuild a delivered check's summary from its saved answers, e.g. after a counting fix."""
    engine = engine or get_engine()
    with engine.begin() as connection:
        check = jobs.load_check(connection, check_id)
    if check["status"] not in {"completed", "partial"} or not check.get("run_id"):
        raise ValueError("Only a delivered check with a saved run can be re-projected")
    projection = project_saved_run(check, run_id=str(check["run_id"]), engine=engine)
    if save:
        with engine.begin() as connection:
            jobs.replace_projection(connection, check_id=check_id, projection=projection)
    return projection


def run_job(job: dict[str, Any], *, settings: dict[str, Any], worker_id: str, engine=None) -> str:
    """Execute one leased job to a delivered, retried or failed outcome. Returns that outcome."""
    engine = engine or get_engine()
    job_id = str(job["id"])
    with engine.begin() as connection:
        check = jobs.load_check(connection, str(job["check_id"]))
    business_name = check["business_name"].strip()
    prompts = _prompts(check)
    expected = len(prompts) * len(PROVIDERS)
    if expected > int(job["reserved_calls"]):
        raise ValueError("Check needs more calls than were reserved")

    if job.get("run_id"):
        run_id = str(job["run_id"])
        run = get_visibility_run(run_id)
        target_id, models = str(run["target_google_place_id"]), dict(run["models"])
        plan = build_retry_plan(queries=get_run_queries(run_id), results=get_run_results(run_id),
                                providers=PROVIDERS)
    else:
        models = settings["models"]
        created = create_discovery_run(
            target_business_name=business_name, target_google_place_id=None,
            target_resolution_status="unresolved", target_dataset_match_name=None,
            primary_group=PRIMARY_GROUP, category_label="Free check",
            location_context=check["location"].strip(), website=check.get("website") or "",
            description=check["services"].strip(), propositions=[],
            providers=PROVIDERS, models=models, prompt_count=len(prompts), repeat_count=1,
            benchmark_mode=BENCHMARK_MODE, prompts=prompts, panel_kind="free_check",
            panel_settings={"customer_check_id": str(check["id"])})
        run_id, target_id = created["run_id"], created["target_google_place_id"]
        with engine.begin() as connection:
            jobs.attach_run(connection, job_id=job_id, worker_id=worker_id, run_id=run_id)
        queries = create_visibility_queries(run_id=run_id, prompts=prompts, repetitions=1)
        plan = [{**query, "provider": provider} for query in queries for provider in PROVIDERS]

    already_done = expected - len(plan)

    def progress(processed: int, total: int) -> None:
        with engine.begin() as connection:
            jobs.heartbeat(connection, job_id=job_id, worker_id=worker_id,
                           completed_calls=already_done + processed)

    if plan:
        execute_calls(run_id=run_id, call_plan=plan, models=models, api_keys=settings["api_keys"],
                      target_google_place_id=target_id, target_business_name=business_name,
                      known_businesses=[{"google_place_id": target_id, "business_name": business_name}],
                      benchmark_mode=BENCHMARK_MODE, location_context=check["location"].strip(),
                      progress_callback=progress)
    status = finalise_run_from_results(run_id=run_id, expected_call_count=expected)

    attempts_left = int(job["attempt_count"]) < int(job["max_attempts"])
    if status == "failed" or (status == "partial" and attempts_left):
        with engine.begin() as connection:
            jobs.release_for_retry(connection, job_id=job_id, worker_id=worker_id,
                                   error=f"Run ended {status}; missing answers will be retried")
        return "retry"

    projection = project_saved_run(check, run_id=run_id, engine=engine)
    with engine.begin() as connection:
        jobs.complete_job(connection, job_id=job_id, worker_id=worker_id, check_status=status,
                          projection=projection, completed_calls=projection["valid_answers"])
    return status


def process_one(*, settings: dict[str, Any], worker_id: str, engine=None) -> str | None:
    """Claim and run at most one job. Returns its outcome, or None when nothing was runnable."""
    engine = engine or get_engine()
    with engine.begin() as connection:
        job = jobs.claim_next_job(connection, worker_id=worker_id, daily_cap=settings["daily_cap"])
    if job is None:
        return None
    try:
        outcome = run_job(job, settings=settings, worker_id=worker_id, engine=engine)
    except Exception as exc:  # A crashed attempt goes back to the queue; attempts are bounded.
        log.exception("Job %s failed", job["id"])
        try:
            with engine.begin() as connection:
                jobs.release_for_retry(connection, job_id=str(job["id"]), worker_id=worker_id,
                                       error=type(exc).__name__)
        except Exception:
            log.exception("Could not release job %s; its lease will expire", job["id"])
        return "error"
    log.info("Job %s finished: %s", job["id"], outcome)
    return outcome


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--once", action="store_true", help="process at most one job, then exit")
    parser.add_argument("--reproject", metavar="CHECK_ID",
                        help="rebuild one delivered check's summary from saved answers; no provider calls")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if args.reproject:
        projection = reproject_check(args.reproject)
        log.info("Re-projected %s: target recommended in %s of %s answers", args.reproject,
                 projection["target"]["recommended_answers"], projection["valid_answers"])
        return
    settings = load_settings()
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    engine = get_engine()
    log.info("Free-check worker %s started; daily cap %s", worker_id, settings["daily_cap"])
    while True:
        outcome = process_one(settings=settings, worker_id=worker_id, engine=engine)
        if args.once:
            return
        if outcome is None:
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
