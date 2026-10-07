"""Free-check business metrics: counts come from saved rows, and nothing is guessed."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import free_check_metrics as metrics  # noqa: E402

NOW = datetime(2026, 10, 7, 14, 0, tzinfo=timezone.utc)


def check(owner, status, *, hours_ago=1, recommended=None, valid=None, calls=None, minutes=None, listing=False):
    created = NOW - timedelta(hours=hours_ago)
    return {"id": f"check-{owner}-{status}", "owner_user_id": owner, "business_name": f"Synthetic {owner}",
            "location": "Hove", "status": status, "error_code": "attempts_exhausted" if status == "failed" else None,
            "created_at": created, "question_count": 3, "listing_confirmed": listing,
            "recommended_answers": recommended, "valid_answers": valid, "expected_answers": 9 if valid else None,
            "attempt_count": 1, "completed_at": created + timedelta(minutes=minutes) if minutes else None,
            "calls": calls, "input_tokens": calls and calls * 100, "output_tokens": calls and calls * 50}


def account(owner, *, confirmed=True, hours_ago=2):
    created = NOW - timedelta(hours=hours_ago)
    return {"id": owner, "email": f"{owner}@example.org", "created_at": created,
            "email_confirmed_at": created if confirmed else None, "last_sign_in_at": created if confirmed else None}


CHECKS = [check("a", "completed", recommended=2, valid=9, calls=9, minutes=4, listing=True),
          check("b", "partial", recommended=0, valid=7, calls=9, minutes=8),
          check("c", "running", calls=3),
          check("d", "failed", hours_ago=30)]
ACCOUNTS = [account("a"), account("b"), account("c"), account("d", hours_ago=31), account("e", confirmed=False)]


def test_headline_counts_separate_sign_ups_checks_and_outcomes():
    out = metrics.summarise(CHECKS, ACCOUNTS, now=NOW, days=7)
    assert (out["sign_ups"], out["confirmed_sign_ups"], out["owners_with_check"]) == (5, 4, 3)
    assert (out["checks"], out["delivered"], out["partial"], out["in_progress"], out["failed"]) == (4, 2, 1, 1, 1)
    assert (out["recommended"], out["not_recommended"], out["listing_confirmed"]) == (1, 1, 1)
    assert out["median_minutes_to_results"] == 6.0
    assert (out["ai_calls"], out["input_tokens"], out["output_tokens"], out["checks_with_usage"]) == (21, 2100, 1050, 3)


def test_daily_series_uses_london_days_and_ends_today():
    out = metrics.summarise(CHECKS, ACCOUNTS, now=NOW, days=7)
    assert len(out["daily"]) == 7 and out["daily"][-1] == {"day": NOW.date(), "sign_ups": 4, "checks": 3}
    assert out["daily"][-2]["checks"] == 1 and out["daily"][-2]["sign_ups"] == 1
    assert out["checks_today"] == 3
    # 23:30 UTC on a summer evening is already the next day in London.
    late = [{**CHECKS[0], "created_at": datetime(2026, 7, 1, 23, 30, tzinfo=timezone.utc)}]
    summer = metrics.summarise(late, [], now=datetime(2026, 7, 2, 9, 0, tzinfo=timezone.utc), days=2)
    assert [day["checks"] for day in summer["daily"]] == [0, 1]


def test_follow_up_lists_show_emails_and_who_has_no_check():
    out = metrics.summarise(CHECKS, ACCOUNTS, now=NOW)
    first = out["recent"][0]
    assert (first["email"], first["recommended"], first["status"]) == ("a@example.org", "2 of 9", "completed")
    assert out["recent"][2]["recommended"] is None, "no result is shown for a check still running"
    # A failed check does not use up the free check, so that owner still has no check.
    assert [row["email"] for row in out["signed_up_without_check"]] == ["d@example.org", "e@example.org"]
    assert [row["confirmed"] for row in out["signed_up_without_check"]] == [True, False]


def test_missing_accounts_are_unknown_not_zero():
    out = metrics.summarise(CHECKS, None, now=NOW, days=3)
    assert out["sign_ups"] is None and out["confirmed_sign_ups"] is None and out["signed_up_without_check"] is None
    assert all(day["sign_ups"] is None for day in out["daily"]) and out["recent"][0]["email"] is None
    assert out["checks"] == 4 and out["owners_with_check"] == 3


def test_no_data_at_all_gives_zeroes_and_no_averages():
    out = metrics.summarise([], [], now=NOW)
    assert out["checks"] == 0 and out["sign_ups"] == 0 and out["median_minutes_to_results"] is None
    assert out["recent"] == [] and out["signed_up_without_check"] == []


def run_page(checks, accounts):
    import streamlit as st
    from streamlit.testing.v1 import AppTest
    st.cache_data.clear()  # the page caches its load for a minute
    page = str(Path(__file__).resolve().parents[1] / "app" / "pages" / "16_Free_Check_Metrics.py")
    with patch.object(metrics, "load_checks", return_value=checks), \
            patch.object(metrics, "load_accounts", **accounts):
        return AppTest.from_file(page, default_timeout=60).run()


def test_page_renders_with_data_without_data_and_without_account_access():
    full = run_page(CHECKS, {"return_value": ACCOUNTS})
    assert not full.exception and not full.warning
    assert {m.label: m.value for m in full.metric}["Emails captured"] == "5"
    assert {m.label: m.value for m in full.metric}["Results delivered"] == "2"
    empty = run_page([], {"return_value": []})
    assert not empty.exception and any("No free checks" in info.value for info in empty.info)
    blocked = run_page(CHECKS, {"side_effect": RuntimeError("permission denied")})
    assert not blocked.exception and len(blocked.warning) == 1
    assert {m.label: m.value for m in blocked.metric}["Emails captured"] == "–"
