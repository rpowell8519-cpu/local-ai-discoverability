from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import streamlit as st
from sqlalchemy import text


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from src.database import get_engine
from src.poc_audit_production import list_report_generator_definitions
from src.report_generator_readiness import (
    ACTIVE_REPORT_PROJECT_KEY,
    REPORT_SEARCH_KEY,
    owner_brief_missing_fields,
    report_journey,
)


BUILD_VERSION = "Report Console v1.0"
REPORT_GENERATOR_PAGE = "pages/10_AI_Report_Generator.py"

st.set_page_config(
    page_title="Report Console",
    page_icon="📋",
    layout="wide",
)


_PROJECTS = text(
    """
    with latest as (
        select distinct on (target_google_place_id)
            target_google_place_id,
            target_business_name,
            revision,
            known_for,
            desired_searches,
            benchmark_run_id,
            reviewer_decisions_complete,
            created_at
        from report_audit_revisions
        order by target_google_place_id, revision desc
    )
    select
        latest.target_google_place_id,
        latest.target_business_name,
        latest.revision,
        latest.known_for,
        latest.desired_searches,
        latest.reviewer_decisions_complete,
        latest.created_at,
        exists (
            select 1
            from ai_visibility_runs run
            where run.id = latest.benchmark_run_id
              and run.status = 'completed'
        ) as benchmark_complete,
        exists (
            select 1
            from website_audit_runs audit
            where audit.google_place_id = latest.target_google_place_id
              and audit.audit_status in ('completed', 'partial')
        ) as website_ready,
        (
            select count(*)
            from business_reviews review
            where review.google_place_id = latest.target_google_place_id
        ) as review_count
    from latest
    order by latest.created_at desc
    """
)


@st.cache_data(ttl=60)
def load_report_projects() -> list[dict[str, Any]]:
    """Read every saved report project with its evidence state. Read-only."""

    with get_engine().connect() as connection:
        rows = connection.execute(_PROJECTS).mappings().all()
    return [dict(row) for row in rows]


@st.cache_data(ttl=300)
def configured_place_ids() -> set[str]:
    """Place IDs with an approved, already-configured report definition."""

    return {
        str(definition.target_google_place_id)
        for definition in list_report_generator_definitions()
    }


def project_journey(project: dict[str, Any], *, configured: bool) -> dict[str, Any]:
    """Describe one project using the same rules as the report generator."""

    brief = {
        "known_for": project.get("known_for") or "",
        "desired_searches": list(project.get("desired_searches") or []),
    }
    return report_journey(
        owner_ready=configured or not owner_brief_missing_fields(brief),
        ai_ready=configured or bool(project.get("benchmark_complete")),
        website_ready=bool(project.get("website_ready")),
        reviews_ready=int(project.get("review_count") or 0) > 0,
        configuration_ready=(
            configured or bool(project.get("reviewer_decisions_complete"))
        ),
    )


def clear_business_search() -> None:
    """A search left over from earlier must not filter the project being opened."""

    for key in (REPORT_SEARCH_KEY, "report_business_search_box"):
        st.session_state.pop(key, None)


def open_report(place_id: str) -> None:
    """Send the operator to the report generator with this project selected."""

    clear_business_search()
    st.session_state[ACTIVE_REPORT_PROJECT_KEY] = str(place_id)
    st.switch_page(REPORT_GENERATOR_PAGE)


def readiness_line(journey: dict[str, Any]) -> str:
    parts = []
    for item in journey["items"]:
        if item["importance"] == "Optional":
            continue
        parts.append(("✅ " if item["ready"] else "⬜ ") + str(item["label"]))
    return " · ".join(parts)


st.title("Client report console")
st.caption(
    "Start a new AI visibility report, or pick up one that is already under way. "
    "Each report walks you through every step in order."
)

st.caption("A report needs the business to be in the database. You will be told straight away if it is not.")
if st.button("Start a new report", type="primary", icon=":material/add:"):
    st.session_state.pop(ACTIVE_REPORT_PROJECT_KEY, None)
    clear_business_search()
    st.switch_page(REPORT_GENERATOR_PAGE)

try:
    projects = load_report_projects()
except Exception as exc:
    st.error("The saved report projects could not be loaded from the database.")
    st.exception(exc)
    projects = []

try:
    configured = configured_place_ids()
except Exception:
    configured = set()

decorated = []
for project in projects:
    place_id = str(project["target_google_place_id"])
    journey = project_journey(project, configured=place_id in configured)
    decorated.append((project, place_id, journey))

in_progress = [item for item in decorated if not item[2]["can_generate"]]
finished = [item for item in decorated if item[2]["can_generate"]]

st.divider()
st.subheader(f"Reports in progress ({len(in_progress)})")

if not in_progress:
    st.info(
        "Nothing is part-finished. Every saved report has reached the point where "
        "its PDF can be generated."
    )

for project, place_id, journey in in_progress:
    with st.container(border=True):
        details, action = st.columns([4, 1])
        with details:
            st.markdown(f"**{project['target_business_name']}**")
            st.caption(
                f"Saved setup revision {project['revision']} · "
                f"last updated {project['created_at']:%d %b %Y}"
            )
            st.markdown(f"**Next step:** {journey['next_step']['title']}")
            st.caption(journey["next_step"]["body"])
            st.caption(readiness_line(journey))
        with action:
            if st.button(
                "Continue",
                key=f"continue_{place_id}",
                type="primary",
                use_container_width=True,
            ):
                open_report(place_id)

st.divider()
st.subheader(f"Ready to generate ({len(finished)})")
st.caption(
    "These reports have the evidence they need. Open one to review it or produce the PDF again."
)

for project, place_id, journey in finished:
    with st.container(border=True):
        details, action = st.columns([4, 1])
        with details:
            st.markdown(f"**{project['target_business_name']}**")
            st.caption(
                f"Saved setup revision {project['revision']} · "
                f"last updated {project['created_at']:%d %b %Y}"
            )
            st.caption(readiness_line(journey))
            if journey["missing_recommended"]:
                st.caption(
                    "Reported as unavailable: "
                    + ", ".join(journey["missing_recommended"])
                )
        with action:
            if st.button(
                "Open",
                key=f"open_{place_id}",
                use_container_width=True,
            ):
                open_report(place_id)

st.divider()
st.subheader("Tools")
st.caption(
    "You do not normally need these. The report takes you to the right tool at the "
    "right moment, then brings you back."
)

evidence_column, testing_column, data_column = st.columns(3)

with evidence_column:
    st.markdown("**Evidence**")
    st.page_link("pages/5_Website_Audits.py", label="Check a website", icon="🌐")
    st.page_link("pages/7_Review_Insights.py", label="Pull customer reviews", icon="⭐")
    st.page_link(
        "pages/6_Website_Benchmark.py", label="Compare website features", icon="📊"
    )

with testing_column:
    st.markdown("**AI testing**")
    st.page_link(
        "pages/8_AI_Visibility.py", label="Run an AI visibility test", icon="🤖"
    )
    st.page_link(
        "pages/0_AI_Discovery_Scan.py", label="Explore who AI recommends", icon="🔍"
    )
    st.page_link(
        "pages/9_AI_Competitive_Diagnostic.py",
        label="Competitive diagnostic (older report flow)",
        icon="🗂️",
    )

with data_column:
    st.markdown("**Business data**")
    st.page_link(
        "pages/12_Business_Data_Explorer.py", label="Browse business data", icon="🔎"
    )
    st.page_link(
        "pages/4_Data_Admin.py", label="Import and manage businesses", icon="⚙️"
    )
    st.page_link(
        "pages/3_Competitor_Matcher.py", label="Match competitor identities", icon="🔗"
    )

st.divider()
st.caption(f"Build: {BUILD_VERSION}")
