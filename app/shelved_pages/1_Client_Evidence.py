"""One read-only summary of a client's evidence, with links into the detailed tools."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.client_evidence import build_client_evidence
from src.evidence_foundations_repository import list_foundation_businesses, list_business_runs, load_measurement_wave
from src.focused_monitoring_repository import load_wave_summary
from src.intervention_repository import list_interventions
from src.positioning_repository import load_owner_brief
from src.positioning_triangulation import triangulate
from src.public_evidence_archive_repository import list_captures, load_capture, list_decisions
from src.report_generator_readiness import ACTIVE_REPORT_PROJECT_KEY

CLIENT_EVIDENCE_BUSINESS_KEY = "client_evidence_business"
RECENT_RUNS = 20

st.set_page_config(page_title="Client evidence", page_icon="🧾", layout="wide")
st.title("Client evidence")
st.caption("Where a client stands on the owner's goals, what needs you next, what the reviewed evidence suggests and "
           "what is being done about it. Read-only: nothing here collects, saves or pays for anything.")

try:
    businesses = list_foundation_businesses()
except Exception as exc:
    st.error(f"Businesses could not be loaded ({type(exc).__name__}).")
    st.stop()
if not businesses:
    st.info("No businesses are available.")
    st.stop()
active = st.session_state.get(ACTIVE_REPORT_PROJECT_KEY) or st.session_state.get(CLIENT_EVIDENCE_BUSINESS_KEY)
index = next((i for i, b in enumerate(businesses) if b["google_place_id"] == active), 0)
business = st.selectbox("Business", businesses, index=index, format_func=lambda b: b["business_name"])
pid = str(business["google_place_id"])
# The detailed evidence pages open on this business when no report is active.
st.session_state[CLIENT_EVIDENCE_BUSINESS_KEY] = pid


def link(container, page: str, label: str, icon: str) -> None:
    try:
        container.page_link(page, label=label, icon=icon)
    except Exception:
        # Outside the multipage app (a single-page test run) there is nothing to link to.
        container.caption(f"{label}: use the sidebar.")


@st.cache_data(ttl=60, show_spinner="Loading saved evidence…")
def load(place_id: str):
    target = next(b for b in businesses if str(b["google_place_id"]) == place_id)
    brief = load_owner_brief(place_id)
    runs = list_business_runs(place_id)
    summaries, incomplete, benchmarks = [], 0, []
    for run in runs[:RECENT_RUNS]:
        wave = load_measurement_wave(str(run["id"]))
        if not wave or wave.get("panel_kind") != "focused":
            benchmarks.append({"started": run["started_at"], "status": run["status"], "questions": run["prompt_count"],
                               "repeats": run["repeat_count"], "providers": ", ".join(run["providers"] or [])})
            continue
        summary = load_wave_summary(run, businesses)
        if summary["issues"]:
            incomplete += 1
        else:
            summaries.append(summary)
    captures = list_captures(place_id)
    capture = load_capture(str(captures[0]["id"])) if captures else None
    decisions = list_decisions(str(capture["id"])) if capture else []
    positioning = triangulate(capture, decisions, owner_brief=brief) if capture else None
    view = build_client_evidence(business=target, brief=brief, summaries=summaries, incomplete_waves=incomplete,
                                 capture=capture, decisions=decisions, positioning=positioning,
                                 actions=list_interventions(place_id), has_benchmark=bool(benchmarks))
    return view, benchmarks


try:
    view, benchmarks = load(pid)
except Exception as exc:
    st.error(f"This business's evidence could not be loaded ({type(exc).__name__}).")
    st.stop()

st.header("1. Where they stand")
if view["goals"]:
    st.metric("Recommended in", f"{view['total_recommended']} of {view['total_answers']} answers",
              help="Across the newest completed focused test of each goal. An answer counts once however many businesses it recommends.")
    for goal in view["goals"]:
        st.markdown(f"**{goal['goal']}** · {goal['provider']} · {pd.Timestamp(goal['measured_at']).strftime('%-d %b %Y')}")
        st.write(f"{view['business']} was recommended in {goal['recommended']} of {goal['answers']} answers.")
        if goal["compared_with"]:
            st.dataframe(pd.DataFrame([{
                "Compared with": other["business"],
                "Recommended in": f"{other['recommended']} of {other['answers']}",
                "Possibly also in": other["unconfirmed"] or None,
            } for other in goal["compared_with"]]), hide_index=True, width="stretch", column_config={
                "Possibly also in": st.column_config.NumberColumn(
                    help="Answers that named something that may be this business. Not counted until the name is confirmed.")})
    st.caption("These are small samples from one day. They show who was recommended, not why.")
elif benchmarks:
    st.info("No focused test is saved for this business. Its report benchmark holds the reviewed results: open the "
            "AI Report Generator to see them. Focused tests are for tracking change after an action.")
else:
    st.info("Nothing has been measured for this business yet.")
if view["stated_goals"]:
    with st.expander("The owner's stated goals"):
        for goal in view["stated_goals"]:
            st.write(f"- {goal}")
if benchmarks:
    with st.expander(f"Report benchmarks saved for this business ({len(benchmarks)})"):
        st.caption("Full benchmarks belong to reports; open the AI Report Generator to see their results.")
        st.dataframe(pd.DataFrame(benchmarks), hide_index=True, width="stretch", column_config={
            "started": st.column_config.DatetimeColumn("Started", format="D MMM YYYY, HH:mm"), "status": "Status",
            "questions": "Questions", "repeats": "Repeats", "providers": "Providers"})

st.header("2. What needs you")
if not view["tasks"] and not view["names_to_confirm"]:
    st.success("Nothing is waiting for you on this business.")
for task in view["tasks"]:
    left, right = st.columns([3, 1])
    left.markdown(f"**{task['task']}**")
    left.caption(task["detail"])
    link(right, task["page"], "Open", "➡️")
if view["names_to_confirm"]:
    st.markdown(f"**{len(view['names_to_confirm'])} name{'s' if len(view['names_to_confirm']) != 1 else ''} the AI used "
                "may be a business being compared**")
    st.caption("Until a person confirms each one, those answers are not counted for that business. "
               "There is no screen for confirming these yet.")
    st.dataframe(pd.DataFrame(view["names_to_confirm"]), hide_index=True, width="stretch", column_config={
        "ai_name": "Name the AI used", "may_be": "May be", "answers": "Answers", "why": "Why it was flagged"})

st.header("3. What the evidence suggests")
if view["suggestions"]:
    st.dataframe(pd.DataFrame(view["suggestions"]), hide_index=True, width="stretch", column_config={
        "topic": "Topic", "meaning": "What the reviewed evidence suggests", "owner_priority": "Owner priority",
        "customer_records": "Supporting customer records"})
    st.caption("Suggestions describe saved, reviewed evidence. They are not ranking factors or causes.")
elif not view["excerpts"]["has_capture"]:
    st.info("Nothing yet: this business's evidence has not been saved for review.")
elif view["excerpts"]["undecided"] == view["excerpts"]["total"]:
    st.info(f"Nothing yet: none of the {view['excerpts']['total']} excerpts has been reviewed.")
else:
    st.info("The excerpts reviewed so far do not yet support a suggestion for any topic.")
if view["topics_awaiting_review"] and view["excerpts"]["has_capture"]:
    st.caption(f"{view['topics_awaiting_review']} topic(s) have too little reviewed evidence for a suggestion.")
link(st, "pages/13_Positioning.py", "Open Positioning for the detail", "🧭")

st.header("4. What we are doing about it")
if view["actions"]:
    st.dataframe(pd.DataFrame(view["actions"]), hide_index=True, width="stretch", column_config={
        "finding": "Finding", "action": "Action and what it should test", "status": "Status", "planned": "Planned",
        "done": "Done"})
else:
    st.info("No actions are recorded for this business. Record one on the Positioning page once there is a finding to act on.")
