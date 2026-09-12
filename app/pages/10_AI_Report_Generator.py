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
from src.poc_audit_generic import build_reviewable_generic_audit  # noqa: E402
from src.report_audit_candidates import load_report_candidates  # noqa: E402
from src.report_audit_workflow import (  # noqa: E402
    AuditWorkflowInput,
    EvidenceState,
    workflow_summary,
)
from src.report_audit_repository import (  # noqa: E402
    get_latest_report_audit,
    save_evidence_states_revision,
    save_owner_brief_revision,
    save_reviewer_decisions_revision,
)
from src.report_generator_readiness import (  # noqa: E402
    normalise_owner_brief,
    owner_brief_missing_fields,
    report_journey,
)


BUILD_VERSION = "Accessible AI Report Generator v2.0"
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
            business_format,
            coalesce(
                nullif(rol.raw_data->>'website', ''),
                nullif(rol.raw_data->>'site', '')
            ) as source_website_url
        from business_features bf
        left join lateral (
            select raw_data
            from raw_outscraper_locations
            where google_place_id = bf.google_place_id
            order by created_at desc, id desc
            limit 1
        ) rol on true
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


@st.cache_data(ttl=60)
def load_review_choices(place_ids: tuple[str, ...]) -> list[dict[str, Any]]:
    if not place_ids:
        return []
    with get_engine().connect() as connection:
        rows = connection.execute(
            text(
                """
                select review_id, google_place_id, business_name, review_text,
                       review_rating, review_datetime_utc
                from (
                    select review_id, google_place_id, business_name, review_text,
                           review_rating, review_datetime_utc,
                           row_number() over (
                               partition by google_place_id
                               order by review_datetime_utc desc nulls last, imported_at desc, id desc
                           ) as business_recency
                    from business_reviews
                    where google_place_id = any(:place_ids)
                      and nullif(btrim(review_text), '') is not null
                ) recent
                where business_recency <= 25
                order by review_datetime_utc desc nulls last
                """
            ),
            {"place_ids": list(place_ids)},
        ).mappings().all()
    return [dict(row) for row in rows][:100]


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
with st.expander("Business not listed?"):
    st.write(
        "Add the business to the database first so it can be tied to a verified Google Place ID. "
        "The existing import accepts an Outscraper CSV/XLSX export and preserves the full source record."
    )
    if st.button("Open business data import", use_container_width=True):
        st.switch_page("pages/4_Data_Admin.py")
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
try:
    durable_audit = get_latest_report_audit(selected_place_id)
except Exception as exc:
    st.error("The saved report setup could not be loaded.")
    st.exception(exc)
    st.stop()
saved_brief = durable_audit or briefs.get(selected_place_id, {})
if durable_audit:
    briefs[selected_place_id] = {
        "known_for": durable_audit["known_for"],
        "desired_searches": list(durable_audit["desired_searches"]),
        "owner_competitors": list(durable_audit["owner_competitors"]),
    }

st.subheader("1. Owner context")
st.write(
    "Tell us what the business should be known for and the kinds of customer searches "
    "that matter most. These answers shape the questions and interpretation."
)

if definition is not None:
    st.success("The owner context for this report has already been reviewed and configured.")
else:
    owner_context = dict(saved_brief.get("owner_context") or {})
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
        with st.expander("Additional owner details", expanded=False):
            priority_services = st.text_area(
                "Priority services or products",
                value="\n".join(owner_context.get("priority_services") or []),
                placeholder="One per line, for example:\nCommercial cleaning\nEnd-of-tenancy cleaning",
            )
            service_areas = st.text_area(
                "Locations or areas served",
                value="\n".join(owner_context.get("service_areas") or []),
                placeholder="One per line, for example:\nBrighton\nHove",
            )
            ideal_customers = st.text_area(
                "Which customers should the business attract?",
                value=str(owner_context.get("ideal_customers") or ""),
                placeholder="For example: office managers, landlords and letting agents.",
            )
            exclusions = st.text_area(
                "Services or searches not to prioritise",
                value="\n".join(owner_context.get("exclusions") or []),
                placeholder="One per line, if relevant.",
            )
            additional_context = st.text_area(
                "Anything else the report reviewer should know?",
                value=str(owner_context.get("additional_context") or ""),
            )
        detected_website = str(business.get("source_website_url") or "").strip()
        manual_website_url = st.text_input(
            "Website address",
            value=str(saved_brief.get("manual_website_url") or detected_website),
            placeholder="https://www.example.co.uk",
            help=(
                "If no website is stored, enter it manually here. Leave this blank if the business genuinely has no website."
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
            try:
                saved_revision = save_owner_brief_revision(
                    target_google_place_id=selected_place_id,
                    target_business_name=str(business["business_name"]),
                    known_for=known_for,
                    desired_searches=desired_searches,
                    owner_competitors=owner_competitors,
                    priority_services=priority_services,
                    service_areas=service_areas,
                    ideal_customers=ideal_customers,
                    exclusions=exclusions,
                    additional_context=additional_context,
                    manual_website_url=manual_website_url,
                )
            except Exception as exc:
                st.error("The owner context could not be saved.")
                st.exception(exc)
            else:
                briefs[selected_place_id] = brief
                saved_brief = saved_revision
                st.success(
                    f"Owner context saved as report setup revision {saved_revision['revision']}."
                )

st.caption(
    "Competitor names are optional. The report's comparison businesses are selected "
    "from the measured AI recommendations, whether or not the owner mentioned them."
)
if durable_audit:
    st.caption(
        f"Saved report setup revision {durable_audit['revision']} is available to other users of the app."
    )

st.subheader("2. What is ready, and what happens next?")
owner_ready = definition is not None or not owner_brief_missing_fields(saved_brief)
completed_run_ids = {str(run["id"]) for run in evidence["completed_runs"]}
saved_benchmark_run_id = str((durable_audit or {}).get("benchmark_run_id") or "")
ai_ready = (
    definition is not None
    or bool(saved_benchmark_run_id and saved_benchmark_run_id in completed_run_ids)
)
website_ready = evidence["website_audit"] is not None
reviews_ready = evidence["review_count"] > 0
configuration_ready = definition is not None or bool(
    durable_audit and durable_audit.get("reviewer_decisions_complete")
)

journey = report_journey(
    owner_ready=owner_ready,
    ai_ready=ai_ready,
    website_ready=website_ready,
    reviews_ready=reviews_ready,
    configuration_ready=configuration_ready,
)
selected_run_id = definition.baseline_run_id if definition else (saved_benchmark_run_id or None)
workflow = workflow_summary(
    AuditWorkflowInput(
        target_google_place_id=selected_place_id,
        owner_brief_complete=owner_ready,
        benchmark_run_id=selected_run_id,
        benchmark_complete=ai_ready,
        website_evidence=(EvidenceState.AVAILABLE if website_ready else EvidenceState(
            str((durable_audit or {}).get("website_evidence_state") or "not_checked")
        )),
        review_evidence=(EvidenceState.AVAILABLE if reviews_ready else EvidenceState(
            str((durable_audit or {}).get("review_evidence_state") or "not_checked")
        )),
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
    saved_cohort_ids = list(
        dict((durable_audit or {}).get("reviewer_decisions") or {}).get("cohort_place_ids") or []
    )
    evidence_business_ids = list(dict.fromkeys([selected_place_id, *saved_cohort_ids]))
    links = st.columns(2)
    with links[0]:
        if st.button("Add or refresh website evidence", use_container_width=True):
            st.session_state["active_diagnostic_cohort"] = {
                "target_google_place_id": selected_place_id,
                "target_business_name": str(business["business_name"]),
                "business_ids": evidence_business_ids,
            }
            st.switch_page("pages/5_Website_Audits.py")
    with links[1]:
        if st.button("Add or refresh review evidence", use_container_width=True):
            st.session_state["active_diagnostic_cohort"] = {
                "target_google_place_id": selected_place_id,
                "target_business_name": str(business["business_name"]),
                "business_ids": evidence_business_ids,
            }
            st.switch_page("pages/7_Review_Insights.py")
    if durable_audit and (not website_ready or not reviews_ready):
        st.divider()
        st.write("If evidence genuinely does not exist, record that here so the report can explain the limitation.")
        website_state = (
            "available" if website_ready else st.radio(
                "Website evidence",
                options=["not_checked", "unavailable"],
                index=1 if durable_audit.get("website_evidence_state") == "unavailable" else 0,
                format_func=lambda value: "Still to check" if value == "not_checked" else "No website evidence available",
                horizontal=True,
            )
        )
        review_state = (
            "available" if reviews_ready else st.radio(
                "Review evidence",
                options=["not_checked", "unavailable"],
                index=1 if durable_audit.get("review_evidence_state") == "unavailable" else 0,
                format_func=lambda value: "Still to check" if value == "not_checked" else "No customer reviews available",
                horizontal=True,
            )
        )
        if st.button("Save evidence availability", use_container_width=True):
            try:
                saved_evidence = save_evidence_states_revision(
                    target_google_place_id=selected_place_id,
                    website_evidence_state=website_state,
                    review_evidence_state=review_state,
                )
            except Exception as exc:
                st.error("The evidence status could not be saved.")
                st.exception(exc)
            else:
                st.success(f"Evidence status saved as revision {saved_evidence['revision']}.")
                st.cache_data.clear()
                st.rerun()

if ai_ready and definition is None:
    st.subheader("3. Review the AI comparison set")
    st.write(
        "Choose three verified businesses that appeared in the saved AI answers. "
        "The owner did not need to name them in advance."
    )
    try:
        candidates = load_report_candidates(
            run_id=saved_benchmark_run_id,
            target_google_place_id=selected_place_id,
        )
    except Exception as exc:
        st.error("The businesses named in the AI responses could not be prepared for review.")
        st.exception(exc)
        candidates = {"verified": [], "unresolved": []}
    verified_candidates = candidates["verified"]
    candidate_by_id = {
        str(item["google_place_id"]): item for item in verified_candidates
        if item.get("google_place_id")
    }
    if candidates["unresolved"]:
        with st.expander(f"{len(candidates['unresolved'])} unresolved AI business name(s)"):
            st.caption(
                "These names remain visible for checking, but cannot be selected until they are matched to a Google Place ID."
            )
            st.dataframe(pd.DataFrame(candidates["unresolved"]), hide_index=True, use_container_width=True)
            if st.button("Open AI Visibility identity review", use_container_width=True):
                st.session_state[AI_VISIBILITY_HANDOFF_KEY] = selected_place_id
                st.switch_page("pages/8_AI_Visibility.py")
    if len(candidate_by_id) < 3:
        st.warning(
            "Fewer than three verified AI-visible businesses are available. Resolve additional names in AI Visibility before completing the report review."
        )
    existing_decisions = dict((durable_audit or {}).get("reviewer_decisions") or {})
    default_cohort = [
        item for item in existing_decisions.get("cohort_place_ids", []) if item in candidate_by_id
    ] or list(candidate_by_id)[:3]
    cohort_ids_for_quotes = tuple(dict.fromkeys([selected_place_id, *default_cohort]))
    try:
        review_choices = load_review_choices(cohort_ids_for_quotes)
    except Exception:
        review_choices = []
    review_by_id = {str(item["review_id"]): item for item in review_choices}
    with st.form(f"report_review_{selected_place_id}"):
        selected_cohort = st.multiselect(
            "Three comparison businesses",
            options=list(candidate_by_id),
            default=default_cohort,
            max_selections=3,
            format_func=lambda place_id: (
                f"{candidate_by_id[place_id]['business_name']} — "
                f"{int(candidate_by_id[place_id].get('recommendations') or 0)} recommendation(s)"
            ),
        )
        headline = st.text_area(
            "Plain-English headline",
            value=str(existing_decisions.get("headline") or ""),
            placeholder="Leave blank to use the measured result automatically.",
        )
        summary = st.text_area(
            "Executive-summary context",
            value=str(existing_decisions.get("summary") or ""),
            placeholder="Optional reviewer context written for a non-technical business owner.",
        )
        action_titles = st.text_area(
            "Priority action titles",
            value="\n".join(existing_decisions.get("action_titles") or []),
            placeholder="Optional: one accessible action title per line. The report uses three.",
        )
        selected_quotes = st.multiselect(
            "Verbatim customer review quotes (optional, up to six)",
            options=list(review_by_id),
            default=[item for item in existing_decisions.get("review_quote_ids", []) if item in review_by_id],
            max_selections=6,
            format_func=lambda review_id: (
                f"{review_by_id[review_id].get('business_name') or 'Business'} — "
                f"{str(review_by_id[review_id]['review_text'])[:110]}"
            ),
        )
        review_notes = st.text_area(
            "Internal reviewer notes",
            value=str(existing_decisions.get("review_notes") or ""),
            help="Saved with the report setup but not printed as client-facing evidence.",
        )
        review_columns = st.columns(2)
        save_draft = review_columns[0].form_submit_button("Save review draft", use_container_width=True)
        complete_review = review_columns[1].form_submit_button(
            "Complete report review",
            type="primary",
            use_container_width=True,
            disabled=len(selected_cohort) != 3,
        )
    if save_draft or complete_review:
        reviewer_decisions = {
            "cohort_place_ids": selected_cohort,
            "headline": " ".join(headline.split()),
            "summary": " ".join(summary.split()),
            "action_titles": [line.strip(" \t-•") for line in action_titles.splitlines() if line.strip(" \t-•")],
            "review_quote_ids": selected_quotes,
            "review_notes": " ".join(review_notes.split()),
        }
        try:
            saved_review = save_reviewer_decisions_revision(
                target_google_place_id=selected_place_id,
                reviewer_decisions=reviewer_decisions,
                complete=bool(complete_review),
            )
        except Exception as exc:
            st.error("The report review could not be saved.")
            st.exception(exc)
        else:
            st.success(
                f"Report review saved as revision {saved_review['revision']}."
            )
            st.cache_data.clear()
            st.rerun()

if saved_brief and saved_brief.get("owner_competitors"):
    with st.expander("Optional owner competitor context"):
        for competitor in saved_brief["owner_competitors"]:
            st.write(f"- {competitor}")
        st.caption("These names do not determine which businesses appear in the report.")

st.subheader("4. Generate report")
if definition is None and not configuration_ready:
    st.info(
        "There is no hidden form for you to complete here. After the required items are ready, "
        "the report reviewer checks the question set, selects relevant businesses from the AI "
        "answers and records any missing evidence as a limitation."
    )
else:
    with st.container(border=True):
        report_client_name = definition.client_name if definition else str(durable_audit["target_business_name"])
        report_run_id = definition.baseline_run_id if definition else saved_benchmark_run_id
        st.markdown(f"**Selected business:** {report_client_name}")
        st.caption(f"Saved benchmark: {report_run_id}")
        generate = st.button(
            "Generate report from saved evidence",
            type="primary",
            use_container_width=True,
        )

    if generate:
        try:
            with st.spinner("Assembling the saved evidence and laying out the report…"):
                reviewable = (
                    build_reviewable_poc_audit(definition)
                    if definition is not None
                    else build_reviewable_generic_audit(durable_audit)
                )
        except Exception as exc:
            st.error(
                "The report could not be generated from the configured evidence. "
                "No benchmark was run and no data was changed."
            )
            st.exception(exc)
        else:
            st.session_state[REPORT_STATE_KEY] = reviewable

    reviewable = st.session_state.get(REPORT_STATE_KEY)
    expected_definition_key = definition.key if definition else f"generic_{durable_audit['id']}"
    if reviewable is not None and reviewable.definition.key == expected_definition_key:
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
