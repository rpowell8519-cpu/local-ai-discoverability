from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
from sqlalchemy import text


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from src.database import get_engine  # noqa: E402
from src.poc_audit_production import (  # noqa: E402
    build_reviewable_poc_audit,
    list_report_generator_definitions,
)
from src.report_audit_workflow import (  # noqa: E402
    AuditWorkflowInput,
    EvidenceState,
    workflow_summary,
)
from src.report_generator_readiness import (  # noqa: E402
    normalise_owner_brief,
    owner_brief_missing_fields,
    report_journey,
)


BUILD_VERSION = "Accessible AI Report Generator v1.4"
REPORT_STATE_KEY = "accessible_ai_report_generator_result"
AI_VISIBILITY_HANDOFF_KEY = "ai_visibility_report_handoff_target"
AI_VISIBILITY_FORCE_PROMPTS_KEY = "ai_visibility_force_owner_prompts"
BRIEFS_STATE_KEY = "accessible_ai_report_owner_briefs"


@st.cache_data(ttl=120)
def load_businesses() -> pd.DataFrame:
    """Load the current canonical business layer for report selection."""

    query = text(
        """
        select
            google_place_id,
            business_name,
            raw_category,
            raw_type,
            primary_group,
            business_format
        from business_features
        where
            google_place_id is not null
            and business_name is not null
        order by lower(business_name), google_place_id
        """
    )
    with get_engine().connect() as connection:
        return pd.DataFrame(connection.execute(query).mappings().all())


@st.cache_data(ttl=60)
def load_evidence_status(google_place_id: str) -> dict[str, Any]:
    """Read the latest evidence available for one canonical business."""

    with get_engine().connect() as connection:
        completed_runs = connection.execute(
            text(
                """
                select id, started_at, completed_at, prompt_count, repeat_count
                from ai_visibility_runs
                where
                    target_google_place_id = :google_place_id
                    and status = 'completed'
                order by completed_at desc nulls last, started_at desc, id desc
                """
            ),
            {"google_place_id": google_place_id},
        ).mappings().all()
        website_audit = connection.execute(
            text(
                """
                select id, audit_status, completed_at, pages_crawled
                from website_audit_runs
                where
                    google_place_id = :google_place_id
                    and audit_status in ('completed', 'partial')
                order by completed_at desc nulls last, started_at desc, id desc
                limit 1
                """
            ),
            {"google_place_id": google_place_id},
        ).mappings().first()
        review_count = connection.execute(
            text(
                """
                select count(*)
                from business_reviews
                where google_place_id = :google_place_id
                """
            ),
            {"google_place_id": google_place_id},
        ).scalar_one()

    return {
        "completed_runs": [dict(row) for row in completed_runs],
        "website_audit": dict(website_audit) if website_audit else None,
        "review_count": int(review_count),
    }


def business_label(row: dict[str, Any]) -> str:
    descriptor = str(row.get("business_format") or row.get("raw_type") or "Business")
    return f"{row['business_name']} — {descriptor} — {str(row['google_place_id'])[-8:]}"


st.set_page_config(page_title="AI Report Generator", page_icon="📄", layout="wide")
st.title("AI Report Generator")
st.caption(
    "Select any business in the database, provide any missing owner context, and "
    "see whether the saved evidence is ready for the accessible client report."
)
st.caption(f"Build: {BUILD_VERSION}")
with st.expander("How the report process works", expanded=True):
    process_columns = st.columns(4)
    process_steps = (
        ("1. Set the priorities", "Tell us what the business should be known for and what customers might ask."),
        ("2. Run the benchmark", "Review those questions, then test them across ChatGPT, Claude and Gemini."),
        ("3. Add useful evidence", "Website and review evidence enrich the comparison when they are available."),
        ("4. Review and generate", "We use businesses found in the AI answers, check the conclusions and create the PDF."),
    )
    for column, (title, body) in zip(process_columns, process_steps):
        with column.container(border=True):
            st.markdown(f"**{title}**")
            st.caption(body)
    st.caption(
        "Required: owner priorities and a completed AI benchmark. Recommended: website and review evidence. "
        "Optional: competitor names from the owner."
    )

try:
    businesses = load_businesses()
except Exception as exc:
    st.error("Businesses could not be loaded from the database.")
    st.exception(exc)
    st.stop()

if businesses.empty:
    st.warning("No businesses are available in the current business database.")
    st.stop()

business_records = businesses.to_dict("records")
businesses_by_id = {str(row["google_place_id"]): row for row in business_records}
selected_place_id = st.selectbox(
    "Business",
    options=list(businesses_by_id),
    format_func=lambda place_id: business_label(businesses_by_id[place_id]),
    help="Type a business name to search the full database.",
)
business = businesses_by_id[selected_place_id]

definitions = list_report_generator_definitions()
configured_definitions = [
    item for item in definitions if item.target_google_place_id == selected_place_id
]
definition = configured_definitions[0] if configured_definitions else None

try:
    evidence = load_evidence_status(selected_place_id)
except Exception as exc:
    st.error("Saved evidence for this business could not be checked.")
    st.exception(exc)
    st.stop()

briefs = st.session_state.setdefault(BRIEFS_STATE_KEY, {})
saved_brief = briefs.get(selected_place_id, {})

st.subheader("1. Owner context")
st.write(
    "Tell us what the business should be known for and the kinds of customer searches "
    "that matter most. These answers shape the questions and interpretation."
)

if definition is not None:
    st.success("The owner context for this report has already been reviewed and configured.")
else:
    with st.form(f"report_brief_{selected_place_id}"):
        known_for = st.text_area(
            "What should this business be known for?",
            value=str(saved_brief.get("known_for") or ""),
            placeholder=(
                "For example: natural-looking balayage, wedding hair and friendly "
                "colour advice in Brighton."
            ),
        )
        desired_searches = st.text_area(
            "What would an ideal customer ask an AI assistant?",
            value="\n".join(saved_brief.get("desired_searches") or []),
            placeholder=(
                "Add one search per line, for example:\n"
                "Who is best for balayage in Brighton?\n"
                "Which Brighton salon is good for wedding hair?"
            ),
            help="One realistic customer question per line.",
        )
        owner_competitors = st.text_area(
            "Businesses the owner sees as competitors (optional)",
            value="\n".join(saved_brief.get("owner_competitors") or []),
            placeholder="One business per line, if useful.",
            help=(
                "These names provide context only. The report will compare the businesses "
                "that actually appeared in the AI responses."
            ),
        )
        submitted = st.form_submit_button("Submit report brief", type="primary")

    if submitted:
        brief = normalise_owner_brief(
            known_for=known_for,
            desired_searches=desired_searches,
            owner_competitors=owner_competitors,
        )
        missing = owner_brief_missing_fields(brief)
        if missing:
            st.error("Please complete: " + "; ".join(missing) + ".")
        else:
            briefs[selected_place_id] = brief
            saved_brief = brief
            st.success("Owner context saved for this browser session.")

st.caption(
    "Competitor names are optional. The report's comparison businesses are selected "
    "from the measured AI recommendations, whether or not the owner mentioned them."
)

st.subheader("2. What is ready, and what happens next?")
owner_ready = definition is not None or not owner_brief_missing_fields(saved_brief)
ai_ready = bool(evidence["completed_runs"])
website_ready = evidence["website_audit"] is not None
reviews_ready = evidence["review_count"] > 0
configuration_ready = definition is not None

journey = report_journey(
    owner_ready=owner_ready,
    ai_ready=ai_ready,
    website_ready=website_ready,
    reviews_ready=reviews_ready,
    configuration_ready=configuration_ready,
)
selected_run_id = definition.baseline_run_id if definition else (
    str(evidence["completed_runs"][0]["id"]) if evidence["completed_runs"] else None
)
workflow = workflow_summary(
    AuditWorkflowInput(
        target_google_place_id=selected_place_id,
        owner_brief_complete=owner_ready,
        benchmark_run_id=selected_run_id,
        benchmark_complete=ai_ready,
        website_evidence=(
            EvidenceState.AVAILABLE if website_ready else EvidenceState.NOT_CHECKED
        ),
        review_evidence=(
            EvidenceState.AVAILABLE if reviews_ready else EvidenceState.NOT_CHECKED
        ),
        reviewer_decisions_complete=configuration_ready,
    )
)
next_step = journey["next_step"]
if workflow["stage"] == "ready_to_generate":
    st.success(f"**Next: {workflow['title']}**\n\n{workflow['body']}")
elif workflow["stage"] == "needs_review":
    st.info(f"**Next: {workflow['title']}**\n\n{workflow['body']}")
else:
    st.warning(f"**Next: {workflow['title']}**\n\n{workflow['body']}")

if selected_run_id:
    st.caption(f"Benchmark selected for this report: `{selected_run_id}`")

readiness_rows = []
for item in journey["items"]:
    detail = item["detail"]
    if item["label"] == "AI benchmark" and ai_ready:
        detail = f"{len(evidence['completed_runs'])} completed run(s) available"
    elif item["label"] == "Website evidence" and website_ready:
        detail = f"{int(evidence['website_audit'].get('pages_crawled') or 0)} pages reviewed"
    elif item["label"] == "Customer reviews" and reviews_ready:
        detail = f"{evidence['review_count']:,} reviews available"
    readiness_rows.append(
        {
            "Item": item["label"],
            "Importance": item["importance"],
            "Status": "Ready" if item["ready"] else (
                "Not available" if item["importance"] == "Recommended" else "Action needed"
            ),
            "What this means": detail,
        }
    )
st.dataframe(pd.DataFrame(readiness_rows), hide_index=True, use_container_width=True)

if workflow["unchecked_evidence"]:
    st.info(
        "Still to check, but not a blocker: " + " and ".join(workflow["unchecked_evidence"]) + ". "
        "If the evidence genuinely does not exist, the report will say so rather than treating it as a poor result."
    )

if next_step["key"] == "benchmark":
    if st.button("Continue to AI Visibility with these questions", type="primary", use_container_width=True):
        st.session_state[AI_VISIBILITY_HANDOFF_KEY] = selected_place_id
        st.session_state[AI_VISIBILITY_FORCE_PROMPTS_KEY] = selected_place_id
        st.switch_page("pages/8_AI_Visibility.py")

with st.expander("Optional evidence actions"):
    st.write(
        "Use these only when the evidence exists. Missing reviews or a business without a website "
        "should not stop the report; the limitation will be stated clearly."
    )
    links = st.columns(2)
    with links[0]:
        st.page_link("pages/5_Website_Audits.py", label="Add or refresh website evidence", use_container_width=True)
    with links[1]:
        st.page_link("pages/7_Review_Insights.py", label="Add or refresh review evidence", use_container_width=True)

if saved_brief and saved_brief.get("owner_competitors"):
    with st.expander("Optional owner competitor context"):
        for competitor in saved_brief["owner_competitors"]:
            st.write(f"- {competitor}")
        st.caption("These names do not determine which businesses appear in the report.")

st.subheader("3. Generate report")
if definition is None:
    st.info(
        "There is no hidden form for you to complete here. After the required items are ready, "
        "the report reviewer checks the question set, selects relevant businesses from the AI "
        "answers and records any missing evidence as a limitation."
    )
else:
    with st.container(border=True):
        st.markdown(f"**Selected business:** {definition.client_name}")
        st.caption(f"Saved benchmark: {definition.baseline_run_id}")
        generate = st.button(
            "Generate report from saved evidence",
            type="primary",
            use_container_width=True,
        )

    if generate:
        try:
            with st.spinner("Assembling the saved evidence and laying out the report…"):
                reviewable = build_reviewable_poc_audit(definition)
        except Exception as exc:
            st.error(
                "The report could not be generated from the configured evidence. "
                "No benchmark was run and no data was changed."
            )
            st.exception(exc)
        else:
            st.session_state[REPORT_STATE_KEY] = reviewable

    reviewable = st.session_state.get(REPORT_STATE_KEY)
    if reviewable is not None and reviewable.definition.key == definition.key:
        st.success("The reviewable PDF is ready.")
        st.download_button(
            "Download PDF",
            data=reviewable.pdf_bytes,
            file_name=reviewable.definition.pdf_filename,
            mime="application/pdf",
            type="primary",
            use_container_width=True,
        )
        st.caption(
            "This draft was generated in memory. Downloading it does not freeze or "
            "save a report snapshot."
        )
