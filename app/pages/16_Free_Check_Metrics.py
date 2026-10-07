"""Read-only business metrics for the website's free visibility check."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.free_check_jobs import DAILY_NEW_CHECK_CAP
from src.free_check_metrics import load_accounts, load_checks, summarise

st.set_page_config(page_title="Free check metrics", page_icon="📊", layout="wide")
st.title("Free check metrics")
st.caption("Sign-ups and free checks from the website, counted from the database. Website analytics "
           "only sees visitors who accepted cookies, so use this page for totals. Read-only; refreshes every minute.")


@st.cache_data(ttl=60)
def load():
    checks = load_checks()
    try:
        accounts = load_accounts()
    except Exception:
        accounts = None
    return checks, accounts


try:
    checks, accounts = load()
except Exception as exc:
    st.error(f"Free check data could not be loaded ({type(exc).__name__}).")
    st.stop()
if accounts is None:
    st.warning("Sign-in accounts could not be read with this database login, so sign-up counts and "
               "email addresses are missing below. Check counts are unaffected.")

days = st.radio("Daily chart covers", [7, 30, 90], index=1, horizontal=True, format_func=lambda n: f"Last {n} days")
metrics = summarise(checks, accounts, now=datetime.now(timezone.utc), days=days)


def shown(value):
    return "–" if value is None else f"{value:,}"


def share(part, whole):
    return f"{part / whole:.0%} of {whole:,}" if whole else None


st.subheader("Sign-ups")
a, b, c = st.columns(3)
a.metric("Emails captured", shown(metrics["sign_ups"]), help="Every address that asked for a sign-in link.")
b.metric("Confirmed their email", shown(metrics["confirmed_sign_ups"]),
         share(metrics["confirmed_sign_ups"], metrics["sign_ups"]) if accounts is not None else None,
         delta_color="off", help="Opened the sign-in link at least once.")
c.metric("Ran a check", shown(metrics["owners_with_check"]),
         share(metrics["owners_with_check"], metrics["sign_ups"]) if accounts is not None else None,
         delta_color="off", help="Owners with a check that is delivered or in progress.")

st.subheader("Checks")
a, b, c, d, e = st.columns(5)
a.metric("Checks started", shown(metrics["checks"]))
b.metric("Results delivered", shown(metrics["delivered"]),
         f"{metrics['partial']} with missing answers" if metrics["partial"] else None, delta_color="off")
c.metric("In progress", shown(metrics["in_progress"]))
d.metric("Failed", shown(metrics["failed"]), help="A failed check does not use up the owner's free check.")
e.metric("Started today", f"{metrics['checks_today']} / {DAILY_NEW_CHECK_CAP}",
         help="Against the worker's default daily cap. The cap actually in force is set on the website and worker.")

st.subheader("Outcomes")
a, b, c, d = st.columns(4)
a.metric("Recommended at least once", shown(metrics["recommended"]),
         share(metrics["recommended"], metrics["delivered"]), delta_color="off")
b.metric("Not recommended at all", shown(metrics["not_recommended"]),
         share(metrics["not_recommended"], metrics["delivered"]), delta_color="off")
c.metric("Confirmed a directory listing", shown(metrics["listing_confirmed"]),
         share(metrics["listing_confirmed"], metrics["checks"]), delta_color="off")
d.metric("Typical wait for results",
         "–" if metrics["median_minutes_to_results"] is None else f"{metrics['median_minutes_to_results']:g} min",
         help="Median time from submitting to results being saved.")

st.subheader("Sign-ups and checks per day")
daily = pd.DataFrame(metrics["daily"]).set_index("day")
st.bar_chart(daily.rename(columns={"sign_ups": "Sign-ups", "checks": "Checks"}).dropna(axis=1, how="all"),
             stack=False)

st.subheader("AI usage")
st.caption("Calls and tokens recorded for free checks. This page does not convert usage to money: "
           "provider prices and live-search fees are not stored here, so take spend from the provider bills.")
a, b, c, d = st.columns(4)
a.metric("AI calls", shown(metrics["ai_calls"]))
b.metric("Input tokens", shown(metrics["input_tokens"]))
c.metric("Output tokens", shown(metrics["output_tokens"]))
d.metric("Calls per check", "–" if not metrics["checks_with_usage"]
         else f"{metrics['ai_calls'] / metrics['checks_with_usage']:.1f}")

st.subheader("Checks, newest first")
if metrics["recent"]:
    st.dataframe(pd.DataFrame(metrics["recent"]), hide_index=True, width="stretch", column_config={
        "started": st.column_config.DatetimeColumn("Started", format="D MMM YYYY, HH:mm"),
        "business": "Business", "area": "Area", "email": "Email", "status": "Status", "questions": "Questions",
        "recommended": "Recommended in", "listing_confirmed": "Listing confirmed", "attempts": "Attempts",
        "error": "Error"})
else:
    st.info("No free checks have been started yet.")

if metrics["signed_up_without_check"] is not None:
    st.subheader("Signed up but has no check")
    st.caption("Asked for a sign-in link and has no delivered or in-progress check.")
    if metrics["signed_up_without_check"]:
        st.dataframe(pd.DataFrame(metrics["signed_up_without_check"]), hide_index=True, width="stretch",
                     column_config={
                         "email": "Email", "confirmed": "Confirmed email",
                         "requested": st.column_config.DatetimeColumn("Requested", format="D MMM YYYY, HH:mm"),
                         "last_sign_in": st.column_config.DatetimeColumn("Last sign-in", format="D MMM YYYY, HH:mm")})
    else:
        st.info("Everyone who signed up has a check.")
