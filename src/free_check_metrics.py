"""Read-only business metrics for the customer free check: sign-ups, checks run and their outcomes.

The database is the source of truth for these counts. Website analytics only sees visitors who
accepted analytics cookies, so it is not used here. Nothing in this module writes.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
from statistics import median
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text

from src.database import get_engine

LONDON = ZoneInfo("Europe/London")
DELIVERED = ("completed", "partial")
IN_PROGRESS = ("queued", "running")

CHECKS_SQL = """
    select c.id, c.owner_user_id, c.business_name, c.location, c.status, c.error_code, c.created_at,
           cardinality(c.questions) as question_count, c.questions,
           (c.claimed_google_place_id is not null) as listing_confirmed,
           (c.result_projection #>> '{target,recommended_answers}')::int as recommended_answers,
           (c.result_projection ->> 'valid_answers')::int as valid_answers,
           (c.result_projection ->> 'expected_answers')::int as expected_answers,
           j.attempt_count, j.completed_at,
           usage.calls, usage.input_tokens, usage.output_tokens
    from public.customer_checks c
    left join public.visibility_jobs j on j.check_id = c.id
    left join lateral (
        select count(*) as calls, sum(r.input_tokens) as input_tokens, sum(r.output_tokens) as output_tokens
        from public.ai_visibility_results r where r.run_id = c.run_id
    ) usage on true
    order by c.created_at desc
"""
ACCOUNTS_SQL = """
    select id, email, created_at, email_confirmed_at, last_sign_in_at
    from auth.users order by created_at desc
"""
CHECK_DETAIL_SQL = """
    select c.id, c.business_name, c.website, c.location, c.services, c.competitors, c.questions,
           c.status, c.error_code, c.created_at, c.run_id, c.claimed_google_place_id,
           f.business_name as claimed_listing_name, c.result_projection
    from public.customer_checks c
    left join public.business_features f on f.google_place_id = c.claimed_google_place_id
    where c.id = cast(:id as uuid)
"""
ANSWERS_SQL = """
    select coalesce(q.base_prompt_order, q.prompt_order) as prompt_order, q.prompt_text,
           r.provider, r.model, r.status, r.response_complete, r.raw_response, r.error_message, r.created_at
    from public.ai_visibility_results r
    join public.ai_visibility_queries q on q.id = r.query_id
    where r.run_id = cast(:run_id as uuid)
    order by prompt_order, r.provider, r.created_at
"""
# The tools every free check asks, in the order the customer sees them (free_check_worker.PROVIDERS).
PROVIDERS = ("OpenAI", "Claude", "Gemini")
CELL_LABELS = {"recommended": "Recommended", "not_recommended": "Not recommended", "missing": "No answer"}


def load_checks() -> list[dict[str, Any]]:
    with get_engine().connect() as connection:
        return [dict(row) for row in connection.execute(text(CHECKS_SQL)).mappings()]


def load_accounts() -> list[dict[str, Any]]:
    """Every email address that asked for a sign-in link, confirmed or not."""
    with get_engine().connect() as connection:
        return [dict(row) for row in connection.execute(text(ACCOUNTS_SQL)).mappings()]


def load_check_detail(check_id: str) -> dict[str, Any] | None:
    """One check's brief and saved result summary, plus every saved AI answer for its run."""
    with get_engine().connect() as connection:
        row = connection.execute(text(CHECK_DETAIL_SQL), {"id": check_id}).mappings().first()
        if row is None:
            return None
        detail = dict(row)
        detail["answers"] = [] if not detail.get("run_id") else [
            dict(answer) for answer in connection.execute(text(ANSWERS_SQL), {"run_id": str(detail["run_id"])}).mappings()]
    return detail


def _complete(answer: dict[str, Any]) -> bool:
    # Same test as the customer's summary (free_check_projection._valid).
    return answer.get("status") == "completed" and answer.get("response_complete") is True


def answer_grid(questions: list[str], answers: list[dict[str, Any]], providers: list[str],
                projection: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Each question with one entry per AI tool: the answer shown and how the customer's summary scored it.

    A retried call can leave several saved rows for one question and tool; the latest completed one is
    shown, otherwise the latest attempt with its error. The score is read from the saved summary's
    cells, never recounted here, so this view always agrees with what the customer was shown.
    """
    cells = {(int(cell["order"]), str(cell["provider"])): str(cell["state"])
             for cell in (projection or {}).get("cells") or []}
    grid = []
    for order, question in enumerate(questions, start=1):
        rows = []
        for provider in providers:
            attempts = [a for a in answers if int(a.get("prompt_order") or 0) == order and a.get("provider") == provider]
            completed = [a for a in attempts if _complete(a)]
            chosen = (completed or attempts or [None])[-1]
            rows.append({
                "provider": provider,
                "model": chosen.get("model") if chosen else None,
                "result": CELL_LABELS.get(cells.get((order, provider)), "Not scored yet") if projection else "Not scored yet",
                "answer": (chosen.get("raw_response") or "") if chosen and _complete(chosen) else "",
                "problem": None if chosen and _complete(chosen) else (
                    "Not asked yet" if chosen is None
                    else str(chosen.get("error_message") or "Incomplete answer (not counted)")),
                "attempts": len(attempts)})
        grid.append({"order": order, "question": question, "providers": rows})
    return grid


def _day(moment: datetime) -> date:
    return moment.astimezone(LONDON).date()


def summarise(checks: list[dict[str, Any]], accounts: list[dict[str, Any]] | None, *,
              now: datetime, days: int = 30) -> dict[str, Any]:
    """Headline counts, a daily series and follow-up lists. `accounts` is None when unavailable.

    A check that failed outright does not use up the owner's free check, so "ran a check" counts
    owners with a check that is delivered or still in progress.
    """
    status = Counter(str(check["status"]) for check in checks)
    delivered = [check for check in checks if check["status"] in DELIVERED]
    recommended = [check for check in delivered if (check.get("recommended_answers") or 0) > 0]
    minutes = [(check["completed_at"] - check["created_at"]).total_seconds() / 60
               for check in delivered if check.get("completed_at")]
    used = [check for check in checks if check.get("calls")]
    today = _day(now)
    first = today - timedelta(days=days - 1)
    checks_by_day = Counter(_day(check["created_at"]) for check in checks)
    accounts_by_day = Counter(_day(account["created_at"]) for account in accounts or [])
    daily = [{"day": first + timedelta(days=offset),
              "sign_ups": accounts_by_day[first + timedelta(days=offset)] if accounts is not None else None,
              "checks": checks_by_day[first + timedelta(days=offset)]}
             for offset in range(days)]

    email = {str(account["id"]): account["email"] for account in accounts or []}
    owners_with_check = {str(check["owner_user_id"]) for check in checks if check["status"] != "failed"}
    recent = [{"id": str(check["id"]), "started": check["created_at"], "business": check["business_name"],
               "area": check["location"], "email": email.get(str(check["owner_user_id"])), "status": check["status"],
               "questions": " · ".join(check.get("questions") or []),
               "recommended": (f"{check['recommended_answers']} of {check['valid_answers']}"
                               if check["status"] in DELIVERED and check.get("valid_answers") is not None else None),
               "listing_confirmed": bool(check["listing_confirmed"]), "attempts": check.get("attempt_count"),
               "error": check.get("error_code")} for check in checks]
    no_check = None if accounts is None else [
        {"email": account["email"], "requested": account["created_at"],
         "confirmed": account["email_confirmed_at"] is not None, "last_sign_in": account["last_sign_in_at"]}
        for account in accounts if str(account["id"]) not in owners_with_check]

    return {
        "sign_ups": None if accounts is None else len(accounts),
        "confirmed_sign_ups": None if accounts is None else sum(
            1 for account in accounts if account["email_confirmed_at"] is not None),
        "owners_with_check": len(owners_with_check),
        "checks": len(checks),
        "delivered": len(delivered),
        "partial": status["partial"],
        "in_progress": sum(status[name] for name in IN_PROGRESS),
        "failed": status["failed"],
        "recommended": len(recommended),
        "not_recommended": len(delivered) - len(recommended),
        "listing_confirmed": sum(1 for check in checks if check["listing_confirmed"]),
        "median_minutes_to_results": round(median(minutes), 1) if minutes else None,
        "checks_today": checks_by_day[today],
        "ai_calls": sum(int(check["calls"]) for check in used),
        "input_tokens": sum(int(check["input_tokens"] or 0) for check in used),
        "output_tokens": sum(int(check["output_tokens"] or 0) for check in used),
        "checks_with_usage": len(used),
        "daily": daily,
        "recent": recent,
        "signed_up_without_check": no_check,
    }
