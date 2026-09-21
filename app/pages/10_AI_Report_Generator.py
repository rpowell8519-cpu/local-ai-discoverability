from __future__ import annotations

import importlib
import inspect
import sys
import re
import uuid
from pathlib import Path
from collections.abc import Mapping
from typing import Any

import pandas as pd
import streamlit as st
from sqlalchemy import text


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from src.database import get_engine  # noqa: E402
import src.ai_visibility_repository as visibility_repository  # noqa: E402
import src.ai_visibility_runner as visibility_runner  # noqa: E402
import src.llm_providers.anthropic_provider as anthropic_provider  # noqa: E402
import src.llm_providers.base as provider_base  # noqa: E402
import src.llm_providers.gemini_provider as gemini_provider  # noqa: E402
import src.llm_providers.openai_provider as openai_provider  # noqa: E402

# Streamlit can hot-reload a page while retaining an older imported module.
# Reload the benchmark modules when a deployment changes their public API,
# before a paid-run control can be displayed.
repository_mode = inspect.signature(visibility_repository.create_visibility_run).parameters.get("benchmark_mode")
if repository_mode is None or repository_mode.default != "search_grounded":
    visibility_repository = importlib.reload(visibility_repository)
if getattr(visibility_runner, "SUPPORTED_BENCHMARK_MODES", frozenset()) != frozenset({"model_memory", "search_grounded"}):
    provider_base = importlib.reload(provider_base)
    openai_provider = importlib.reload(openai_provider)
    anthropic_provider = importlib.reload(anthropic_provider)
    gemini_provider = importlib.reload(gemini_provider)
    visibility_runner = importlib.reload(visibility_runner)

create_visibility_queries = visibility_repository.create_visibility_queries
create_visibility_run = visibility_repository.create_visibility_run
execute_calls = visibility_runner.execute_calls
finalise_run_from_results = visibility_runner.finalise_run_from_results
from src.website_audit import audit_website  # noqa: E402
from src.website_audit_repository import (  # noqa: E402
    create_audit_run,
    finish_audit_run,
    save_audit_page,
)
from src.review_ingestion import (  # noqa: E402
    import_reviews,
    normalise_review_frame,
    read_outscraper_reviews,
)
from src.outscraper_reviews import (  # noqa: E402
    DEFAULT_APP_COST_CEILING_GBP,
    OutscraperError,
    api_import_source_name,
    flatten_google_reviews_response,
    get_request_result,
    review_pull_within_cost_ceiling,
    submit_google_reviews,
)
from src.poc_audit_production import (  # noqa: E402
    build_reviewable_poc_audit,
    list_report_generator_definitions,
)
from src.client_summary.adapter import (  # noqa: E402
    build_client_summary_report,
    render_client_summary_pdf,
)
from src.poc_audit_generic import (  # noqa: E402
    assemble_generic_report_payload,
    build_reviewable_generic_audit,
)
from src.report_audit_candidates import load_report_candidates  # noqa: E402
from src.business_lookup import near_misses, search_businesses  # noqa: E402
from src.report_identity import find_possible_target_names  # noqa: E402
from src.site_checks import check_ai_crawler_access, crawler_finding  # noqa: E402
from src.report_priorities import NOT_LINKED, suggest_priority_map  # noqa: E402
from src.report_competitors import (  # noqa: E402
    catchment_radius_miles,
    resolve_run_location,
    classify_location,
    match_owner_competitors,
)
from src.report_audit_workflow import (  # noqa: E402
    AuditWorkflowInput,
    EvidenceState,
    workflow_summary,
)
from src.report_audit_repository import (  # noqa: E402
    attach_benchmark_revision,
    get_latest_report_audit,
    save_evidence_states_revision,
    save_owner_brief_revision,
    save_reviewer_decisions_revision,
)
from src.report_generator_readiness import (  # noqa: E402
    ACTIVE_REPORT_PROJECT_KEY,
    REPORT_SEARCH_KEY,
    normalise_owner_brief,
    owner_brief_missing_fields,
    report_journey,
)


BUILD_VERSION = "Accessible AI Report Generator v3.1.0 (client summary, identity review, business search)"
REPORT_STATE_KEY = "accessible_ai_report_generator_result"
SUMMARY_STATE_KEY = "accessible_ai_client_summary_result"
AI_VISIBILITY_HANDOFF_KEY = "ai_visibility_report_handoff_target"
AI_VISIBILITY_FORCE_PROMPTS_KEY = "ai_visibility_force_owner_prompts"
BRIEFS_STATE_KEY = "accessible_ai_report_owner_briefs"
DEFAULT_MODELS = {
    "OpenAI": "gpt-5.6-terra",
    "Claude": "claude-sonnet-5",
    "Gemini": "gemini-3.6-flash",
}


def secret_value(key: str, default: str = "") -> str:
    try:
        value = st.secrets.get(key, default)
    except Exception:
        value = default
    return str(value or default)


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
            rol.raw_data->>'city' as city,
            coalesce(rol.raw_data->>'address', rol.raw_data->>'full_address') as address,
            coalesce(rol.raw_data->>'latitude', rol.raw_data->>'lat') as latitude,
            coalesce(rol.raw_data->>'longitude', rol.raw_data->>'lng') as longitude,
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


@st.cache_data(ttl=120)
def load_run_prompt_seed(run_id: str) -> list[dict[str, Any]]:
    """Load one verbatim copy of each question from a saved benchmark."""

    with get_engine().connect() as connection:
        rows = connection.execute(
            text(
                """
                select distinct on (base_prompt_order)
                    base_prompt_order, prompt_category, prompt_source, prompt_text
                from ai_visibility_queries
                where run_id = :run_id
                order by base_prompt_order, repeat_index, prompt_order, id
                """
            ),
            {"run_id": run_id},
        ).mappings().all()
    return [dict(row) for row in rows]


@st.cache_data(ttl=60)
def has_configured_measurement_project(google_place_id: str) -> bool:
    """Recognise a configured-report restart across all saved revisions."""

    with get_engine().connect() as connection:
        return bool(
            connection.execute(
                text(
                    """
                    select exists (
                        select 1
                        from report_audit_revisions
                        where target_google_place_id = :google_place_id
                          and owner_context->>'workflow_origin' = 'configured_report_restart'
                    )
                    """
                ),
                {"google_place_id": google_place_id},
            ).scalar_one()
        )


def site_findings_for(business: Mapping[str, Any], audit: Mapping[str, Any] | None) -> tuple[str, list[dict[str, Any]]]:
    """Read the client's robots.txt once (read-only) and return (website address, findings)."""

    url = clean_text((audit or {}).get("manual_website_url")) or clean_text(business.get("source_website_url"))
    finding = crawler_finding(check_ai_crawler_access(url)) if url else None
    return url, [finding] if finding else []


def clean_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def review_comparison_website(
    *, place_id: str, business_name: str, website_url: str, business_group: str
) -> None:
    """Crawl and save one comparison business's website, as for the target."""

    audit_run_id = create_audit_run(
        audit_batch_id=str(uuid.uuid4()),
        google_place_id=place_id,
        business_name=business_name,
        requested_url=website_url,
    )
    try:
        audit_result, audit_pages = audit_website(
            website_url=website_url,
            business_group=business_group,
            max_pages=20,
            timeout_seconds=12,
            adaptive_stop=True,
        )
        for audit_page in audit_pages:
            save_audit_page(audit_run_id=audit_run_id, page=audit_page)
        finish_audit_run(audit_run_id=audit_run_id, result=audit_result)
    except Exception as exc:
        finish_audit_run(
            audit_run_id=audit_run_id,
            result={"audit_status": "failed", "error_message": str(exc)},
        )
        raise


SEARCH_BOX_KEY = "report_business_search_box"


def use_suggestion(name: str) -> None:
    st.session_state[SEARCH_BOX_KEY] = name


def show_business_not_found(query: str, suggestions: list[dict[str, Any]]) -> None:
    """Say plainly that the business is not in the database, and how to add it."""

    st.warning(f"“{query}” is not in the business database yet.")
    if suggestions:
        st.markdown("**Did you mean one of these?**")
        for record in suggestions:
            st.button(
                business_label(record),
                key=f"suggest_{record['google_place_id']}",
                on_click=use_suggestion,
                args=(str(record["business_name"]),),
            )
    with st.container(border=True):
        st.markdown("**To run a report for it, add it to the database first**")
        st.markdown(
            "A report can only be run for a business that has a verified Google Place ID in the database.\n\n"
            "1. Export the business from Google Maps with Outscraper, as a `.csv` or `.xlsx` that includes "
            "`place_id` and `name`.\n"
            "2. Open Data Admin and use **1. Import business data**. The import adds the business and builds its "
            "features automatically. You do not need the full rebuild in section 2.\n"
            "3. Come back here. Your search is kept, so the business will appear."
        )
        action_columns = st.columns(2)
        with action_columns[0]:
            if st.button("Open Data Admin to import it", type="primary", use_container_width=True):
                st.switch_page("pages/4_Data_Admin.py")
        with action_columns[1]:
            if st.button("I've imported it: search again", use_container_width=True):
                st.cache_data.clear()
                st.rerun()


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
requested_place_id = str(
    st.query_params.get("report_business")
    or st.session_state.get(ACTIVE_REPORT_PROJECT_KEY)
    or ""
)
if SEARCH_BOX_KEY not in st.session_state:
    # Restore a search that was waiting while the operator was in Data Admin.
    st.session_state[SEARCH_BOX_KEY] = st.session_state.get(REPORT_SEARCH_KEY, "")
search_query = st.text_input(
    "Find the business",
    placeholder="Start typing the business name, town or Google Place ID",
    key=SEARCH_BOX_KEY,
    help="Reports can only be run for businesses in the database. You will be told if it is not there.",
).strip()
st.session_state[REPORT_SEARCH_KEY] = search_query
if search_query:
    matches = search_businesses(business_records, search_query)
    if not matches:
        show_business_not_found(search_query, near_misses(business_records, search_query))
        st.stop()
    business_options = [str(match["google_place_id"]) for match in matches]
else:
    business_options = list(businesses_by_id)
default_business_index = (
    business_options.index(requested_place_id)
    if requested_place_id in business_options
    else 0
)
selected_place_id = st.selectbox(
    "Business" if not search_query else f"Business ({len(business_options)} found)",
    options=business_options,
    index=default_business_index,
    format_func=lambda place_id: business_label(businesses_by_id[place_id]),
    help="Pick the business to report on.",
)
business = businesses_by_id[selected_place_id]
st.session_state[ACTIVE_REPORT_PROJECT_KEY] = selected_place_id
st.query_params["report_business"] = selected_place_id

with st.expander("How the report process works", expanded=True):
    process_columns = st.columns(4)
    process_steps = (
        ("1. Set the priorities", "Tell us what the business should be known for and what customers might ask."),
        ("2. Run AI Visibility", "Review those questions, then test them across ChatGPT, Claude and Gemini."),
        ("3. Add useful evidence", "Website and review evidence enrich the comparison when they are available."),
        ("4. Review and generate", "We use businesses found in the AI answers, check the conclusions and create the PDF."),
    )
    for column, (title, body) in zip(process_columns, process_steps):
        with column.container(border=True):
            st.markdown(f"**{title}**")
            st.caption(body)
    st.caption(
        "Required: owner priorities and completed AI Visibility. Recommended: website and review evidence. "
        "Optional: competitor names from the owner."
    )

definitions = list_report_generator_definitions()
configured_definitions = [
    item for item in definitions if item.target_google_place_id == selected_place_id
]
configured_definition = configured_definitions[0] if configured_definitions else None

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

new_measurement_origin = "configured_report_restart"
has_new_measurement = bool(
    configured_definition
    and durable_audit
    and (
        dict(durable_audit.get("owner_context") or {}).get("workflow_origin")
        == new_measurement_origin
        or has_configured_measurement_project(selected_place_id)
    )
)
measurement_view_key = f"report_measurement_view_{selected_place_id}"
if measurement_view_key not in st.session_state:
    st.session_state[measurement_view_key] = "new" if has_new_measurement else "original"
viewing_new_measurement = bool(
    configured_definition
    and has_new_measurement
    and st.session_state[measurement_view_key] == "new"
)
definition = None if viewing_new_measurement else configured_definition
saved_brief = durable_audit or briefs.get(selected_place_id, {})
if durable_audit:
    briefs[selected_place_id] = {
        "known_for": durable_audit["known_for"],
        "desired_searches": list(durable_audit["desired_searches"]),
        "owner_competitors": list(durable_audit["owner_competitors"]),
    }

if configured_definition is not None:
    if viewing_new_measurement:
        with st.container(border=True):
            st.info(
                "**New measurement in progress.** Edit the exact questions in the AI Visibility table below, "
                "then approve the paid run when they are ready. The original report remains unchanged."
            )
            if st.button("View the original saved report", use_container_width=True):
                st.session_state[measurement_view_key] = "original"
                st.rerun()
    else:
        with st.container(border=True):
            st.success(
                "**Original saved report available.** You can generate it again without rerunning AI Visibility."
            )
            if has_new_measurement:
                if st.button("Continue editing the new measurement", type="primary", use_container_width=True):
                    st.session_state[measurement_view_key] = "new"
                    st.rerun()
            elif st.button(
                "Start a new measurement and edit the prompts",
                type="primary",
                use_container_width=True,
                help="Copies the original questions into a new editable project. It does not alter the original report.",
            ):
                try:
                    configured_queries = load_run_prompt_seed(
                        configured_definition.baseline_run_id
                    )
                    if not configured_queries:
                        raise ValueError("The original saved benchmark has no questions to copy")
                    save_owner_brief_revision(
                        target_google_place_id=selected_place_id,
                        target_business_name=str(business["business_name"]),
                        known_for=(
                            f"The services and customer needs covered by the original "
                            f"{configured_definition.client_name} measurement. Review and update this description."
                        ),
                        desired_searches="\n".join(
                            str(query["prompt_text"]) for query in configured_queries
                        ),
                        manual_website_url=str(business.get("source_website_url") or ""),
                        workflow_origin=new_measurement_origin,
                        created_by="streamlit_configured_report_restart",
                    )
                except Exception as exc:
                    st.error("The editable measurement project could not be created.")
                    st.exception(exc)
                else:
                    st.session_state[measurement_view_key] = "new"
                    st.cache_data.clear()
                    st.rerun()

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
        if viewing_new_measurement:
            desired_searches = "\n".join(saved_brief.get("desired_searches") or [])
            st.info(
                "Edit the exact customer questions in **3. Run AI Visibility** below. "
                "That table is the single source for the next measurement."
            )
            st.caption(
                f"{len(saved_brief.get('desired_searches') or [])} question(s) copied from the original report."
            )
        else:
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
            owner_competitors = st.text_area(
                "Businesses the owner sees as competitors (optional)",
                value="\n".join(saved_brief.get("owner_competitors") or []),
                placeholder="One business per line, if useful.",
                help=(
                    "Context only. The report automatically uses businesses that appeared "
                    "most often in AI Visibility."
                ),
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
        submitted = st.form_submit_button(
            "Save owner details" if viewing_new_measurement else "Submit report brief",
            type="primary",
        )

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
                    workflow_origin=(
                        new_measurement_origin if viewing_new_measurement else ""
                    ),
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
                st.cache_data.clear()
                st.rerun()

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
    st.caption(f"AI Visibility run selected for this report: `{selected_run_id}`")

readiness_rows = []
for item in journey["items"]:
    detail = item["detail"]
    if item["label"] == "AI Visibility" and ai_ready:
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
    st.subheader("3. Run AI Visibility")
    st.write(
        "Review and edit the questions here. The test uses the same AI Visibility engine as the specialist page."
    )
    prompt_state_key = f"report_ai_questions_{selected_place_id}_{(durable_audit or {}).get('revision', 0)}"
    if prompt_state_key not in st.session_state:
        st.session_state[prompt_state_key] = pd.DataFrame(
            [
                {
                    "include": True,
                    "intent": "Owner priority",
                    "question": str(question),
                }
                for question in list(saved_brief.get("desired_searches") or [])
            ]
        )
    question_table = st.data_editor(
        st.session_state[prompt_state_key],
        hide_index=True,
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "include": st.column_config.CheckboxColumn("Run"),
            "intent": st.column_config.TextColumn("Intent"),
            "question": st.column_config.TextColumn("Customer question", width="large"),
        },
        key=f"report_ai_question_editor_{selected_place_id}",
    )
    st.session_state[prompt_state_key] = question_table.copy()
    selected_questions = question_table[
        question_table["include"].fillna(False)
        & question_table["question"].fillna("").astype(str).str.strip().ne("")
    ].copy()
    ai_controls = st.columns(3)
    with ai_controls[0]:
        repetitions = st.selectbox(
            "Repetitions per question",
            options=[1, 2, 3],
            index=2,
            help="Three repetitions give a more reliable view of variable AI answers.",
        )
    api_keys = {
        "OpenAI": secret_value("OPENAI_API_KEY"),
        "Claude": secret_value("ANTHROPIC_API_KEY"),
        "Gemini": secret_value("GEMINI_API_KEY"),
    }
    available_providers = [name for name, key in api_keys.items() if key]
    run_location = resolve_run_location(
        dict(saved_brief.get("owner_context") or {}).get("service_areas") or [],
        business.get("city"),
    )
    if not run_location:
        st.error(
            "This business has no city on record and no service area was entered, so the AI platforms would not "
            "know where the customer is searching from. Add a service area in the owner context above."
        )
    with ai_controls[1]:
        st.metric("AI platforms connected", f"{len(available_providers)} / 3")
    call_count = len(selected_questions) * int(repetitions) * len(available_providers)
    with ai_controls[2]:
        st.metric("Planned API calls", call_count)
    missing_providers = [name for name in DEFAULT_MODELS if name not in available_providers]
    if missing_providers:
        st.error("Connect all three required AI platforms before running: " + ", ".join(missing_providers) + ".")
    if len(selected_questions) > 8:
        st.error(
            "Select no more than eight questions for one report. Additional questions can be saved for a separate run."
        )
    st.warning(
        "This starts paid API calls. Check the questions and planned call count before continuing. "
        "Each platform will use its live web search capability, so search-tool charges may also apply."
    )
    confirm_ai_spend = st.checkbox(
        "I have reviewed the questions and approve this AI Visibility run",
        key=f"confirm_report_ai_{selected_place_id}",
    )
    run_ai_visibility = st.button(
        "Run AI Visibility",
        type="primary",
        use_container_width=True,
        disabled=(
            not confirm_ai_spend
            or len(selected_questions) == 0
            or len(selected_questions) > 8
            or len(available_providers) != 3
            or not run_location
        ),
    )
    if run_ai_visibility:
        prompt_records = [
            {
                "category": str(row.get("intent") or "Owner priority"),
                "source": "owner_brief",
                "prompt": str(row["question"]).strip(),
            }
            for row in selected_questions.to_dict("records")
        ]
        models = {
            "OpenAI": secret_value("OPENAI_MODEL", DEFAULT_MODELS["OpenAI"]),
            "Claude": secret_value("ANTHROPIC_MODEL", DEFAULT_MODELS["Claude"]),
            "Gemini": secret_value("GEMINI_MODEL", DEFAULT_MODELS["Gemini"]),
        }
        progress = st.progress(0)
        status_box = st.empty()

        def progress_callback(done: int, total: int) -> None:
            progress.progress(min(done / max(total, 1), 1.0))

        def status_callback(question: str) -> None:
            status_box.write(f"Testing: **{question}**")

        try:
            run_id = create_visibility_run(
                target_google_place_id=selected_place_id,
                target_business_name=str(business["business_name"]),
                primary_group=str(business.get("primary_group") or "generic"),
                location_context=run_location,
                providers=available_providers,
                models=models,
                prompt_count=len(prompt_records),
                repeat_count=int(repetitions),
            )
            query_records = create_visibility_queries(
                run_id=run_id,
                prompts=prompt_records,
                repetitions=int(repetitions),
            )
            call_plan = [
                {**query_record, "provider": provider}
                for query_record in query_records
                for provider in available_providers
            ]
            execute_calls(
                run_id=run_id,
                call_plan=call_plan,
                models=models,
                api_keys=api_keys,
                target_google_place_id=selected_place_id,
                target_business_name=str(business["business_name"]),
                known_businesses=[
                    {
                        "google_place_id": str(item["google_place_id"]),
                        "business_name": str(item["business_name"]),
                    }
                    for item in business_records
                ],
                benchmark_mode="search_grounded",
                location_context=run_location,
                progress_callback=progress_callback,
                status_callback=status_callback,
            )
            run_status = finalise_run_from_results(
                run_id=run_id,
                expected_call_count=len(call_plan),
            )
            if run_status != "completed":
                raise RuntimeError(
                    "The AI Visibility run was not complete. Open the advanced tools to inspect or retry failed calls."
                )
            attach_benchmark_revision(
                target_google_place_id=selected_place_id,
                benchmark_run_id=run_id,
            )
        except Exception as exc:
            st.error("AI Visibility did not complete successfully. Saved individual results remain available for recovery.")
            st.exception(exc)
        else:
            status_box.empty()
            st.success("AI Visibility is complete and attached to this report project.")
            st.cache_data.clear()
            st.rerun()

    with st.expander("Advanced AI Visibility tools"):
        st.write("Use the specialist page for raw-response inspection, retries and identity enrichment.")
        if st.button("Open advanced AI Visibility", use_container_width=True):
            st.session_state[AI_VISIBILITY_HANDOFF_KEY] = selected_place_id
            st.session_state[AI_VISIBILITY_FORCE_PROMPTS_KEY] = selected_place_id
            st.switch_page("pages/8_AI_Visibility.py")

st.subheader("4. Add website and review evidence")
with st.container(border=True):
    st.write(
        "Use these only when the evidence exists. Missing reviews or a business without a website "
        "should not stop the report; the limitation will be stated clearly."
    )
    saved_cohort_ids = list(
        dict((durable_audit or {}).get("reviewer_decisions") or {}).get("cohort_place_ids") or []
    )
    evidence_business_ids = list(dict.fromkeys([selected_place_id, *saved_cohort_ids]))
    st.markdown("**Website evidence**")
    website_url = str(
        (durable_audit or {}).get("manual_website_url")
        or business.get("source_website_url")
        or ""
    ).strip()
    if website_ready:
        st.success(
            f"Website review complete: {int(evidence['website_audit'].get('pages_crawled') or 0)} page(s) saved."
        )
    elif website_url:
        st.caption(f"Website to review: {website_url}")
        run_website_audit = st.button(
            "Review this website now",
            use_container_width=True,
            help="This visits public pages on the saved website and stores the evidence for the report.",
        )
        if run_website_audit:
            audit_run_id = create_audit_run(
                audit_batch_id=str(uuid.uuid4()),
                google_place_id=selected_place_id,
                business_name=str(business["business_name"]),
                requested_url=website_url,
            )
            try:
                with st.spinner("Reviewing the website and saving the evidence…"):
                    audit_result, audit_pages = audit_website(
                        website_url=website_url,
                        business_group=str(business.get("primary_group") or "generic"),
                        max_pages=20,
                        timeout_seconds=12,
                        adaptive_stop=True,
                    )
                    for audit_page in audit_pages:
                        save_audit_page(audit_run_id=audit_run_id, page=audit_page)
                    finish_audit_run(audit_run_id=audit_run_id, result=audit_result)
            except Exception as exc:
                finish_audit_run(
                    audit_run_id=audit_run_id,
                    result={"audit_status": "failed", "error_message": str(exc)},
                )
                st.error("The website could not be reviewed. You can retry or record that it is unavailable.")
                st.exception(exc)
            else:
                st.success("Website evidence has been saved to this report project.")
                st.cache_data.clear()
                st.rerun()
    else:
        st.info("No website is saved. Enter one in Owner context above, or record that no website evidence is available.")

    st.divider()
    st.markdown("**Customer review evidence**")
    if reviews_ready:
        st.success(f"{evidence['review_count']:,} customer review(s) are already available for this business.")
    uploaded_reviews = st.file_uploader(
        "Upload an Outscraper review file",
        type=["csv", "xlsx"],
        key=f"report_review_upload_{selected_place_id}",
        help="The file may contain several businesses; only reviews matching this business's Google Place ID are imported here.",
    )
    if uploaded_reviews is not None:
        try:
            raw_reviews = read_outscraper_reviews(uploaded_reviews)
            matching_reviews = raw_reviews[
                raw_reviews["place_id"].fillna("").astype(str).eq(selected_place_id)
            ].copy()
            valid_reviews, invalid_reviews = normalise_review_frame(matching_reviews)
        except Exception as exc:
            st.error("This review file could not be read.")
            st.exception(exc)
        else:
            st.caption(
                f"Found {len(valid_reviews):,} valid matching review(s)"
                + (f" and {len(invalid_reviews):,} incomplete matching row(s)." if len(invalid_reviews) else ".")
            )
            if st.button(
                "Import matching reviews",
                disabled=valid_reviews.empty,
                use_container_width=True,
            ):
                try:
                    imported = import_reviews(
                        matching_reviews,
                        source_file_name=str(uploaded_reviews.name),
                    )
                except Exception as exc:
                    st.error("The matching reviews could not be imported.")
                    st.exception(exc)
                else:
                    st.success(f"Imported {int(imported['processed_rows']):,} review(s).")
                    st.cache_data.clear()
                    st.rerun()

    outscraper_api_key = secret_value("OUTSCRAPER_API_KEY")
    with st.expander("Or fetch reviews directly from Outscraper"):
        if not outscraper_api_key:
            st.info("Outscraper is not connected. Use the file upload above, or ask an administrator to add the API key.")
        else:
            reviews_limit = st.selectbox(
                "Maximum reviews to request",
                options=[50, 100, 200],
                index=1,
                key=f"report_review_limit_{selected_place_id}",
            )
            within_ceiling, projected_cost = review_pull_within_cost_ceiling(
                requested_reviews=int(reviews_limit),
                ceiling_gbp=DEFAULT_APP_COST_CEILING_GBP,
            )
            st.caption(
                f"Conservative estimated maximum cost: £{projected_cost:.2f}. "
                f"The app ceiling is £{DEFAULT_APP_COST_CEILING_GBP:.2f}."
            )
            request_key = f"report_outscraper_request_{selected_place_id}"
            if st.button(
                "Request reviews from Outscraper",
                disabled=not within_ceiling,
                use_container_width=True,
            ):
                try:
                    request = submit_google_reviews(
                        api_key=outscraper_api_key,
                        place_ids=[selected_place_id],
                        reviews_limit=int(reviews_limit),
                    )
                except OutscraperError as exc:
                    st.error(f"Outscraper could not start the request: {exc}")
                else:
                    st.session_state[request_key] = str(request.get("id") or "")
                    st.success("Review collection started. Use the check button below when it has finished.")
            request_id = str(st.session_state.get(request_key) or "")
            if request_id and st.button("Check and import collected reviews", use_container_width=True):
                try:
                    response = get_request_result(api_key=outscraper_api_key, request_id=request_id)
                    api_reviews = flatten_google_reviews_response(response.get("data"))
                    matching_api_reviews = api_reviews[
                        api_reviews["place_id"].fillna("").astype(str).eq(selected_place_id)
                    ].copy() if not api_reviews.empty else api_reviews
                    if matching_api_reviews.empty:
                        st.info(f"The request is currently {response.get('status') or 'processing'}; no reviews are ready yet.")
                    else:
                        imported = import_reviews(
                            matching_api_reviews,
                            source_file_name=api_import_source_name(request_id),
                        )
                        st.session_state.pop(request_key, None)
                        st.success(f"Imported {int(imported['processed_rows']):,} review(s) from Outscraper.")
                        st.cache_data.clear()
                        st.rerun()
                except (OutscraperError, ValueError) as exc:
                    st.error(f"The review request could not be checked: {exc}")

    with st.expander("Advanced evidence tools"):
        st.write("Use the specialist pages for multi-business audit batches, review benchmarking and detailed diagnostics.")
        advanced_links = st.columns(2)
        with advanced_links[0]:
            if st.button("Open advanced website tools", use_container_width=True):
                st.session_state["active_diagnostic_cohort"] = {
                    "target_google_place_id": selected_place_id,
                    "target_business_name": str(business["business_name"]),
                    "business_ids": evidence_business_ids,
                }
                st.switch_page("pages/5_Website_Audits.py")
        with advanced_links[1]:
            if st.button("Open advanced review tools", use_container_width=True):
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
    st.subheader("5. Review the AI-selected comparison set")
    st.write(
        "The platform suggests three verified, geographically relevant businesses found in "
        "AI Visibility. Owner-nominated competitors are measured separately, including those "
        "with no visibility. A reviewer can override the AI-discovered set when there is a "
        "clear relevance, location or identity reason."
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
    owner_context = dict((saved_brief or {}).get("owner_context") or {})
    initial_decisions = dict((durable_audit or {}).get("reviewer_decisions") or {})
    suggested_radius = catchment_radius_miles(
        str(business.get("primary_group") or ""),
        str(business.get("business_format") or ""),
    )
    radius_options = [3, 5, 10, 15, 25, 35, 60]
    saved_radius = float(initial_decisions.get("catchment_radius_miles") or suggested_radius)
    default_radius = min(radius_options, key=lambda value: abs(value - saved_radius))
    selected_radius = st.selectbox(
        "Expected competitor catchment",
        options=radius_options,
        index=radius_options.index(default_radius),
        format_func=lambda value: f"{value} miles",
        help="The suggested distance reflects the business type. Adjust it when the owner's real service area is narrower or wider.",
    )
    target_location = {
        key: business.get(key) for key in ("city", "address", "latitude", "longitude")
    }
    service_areas = list(owner_context.get("service_areas") or [])
    verified_candidates = [
        {
            **item,
            **classify_location(
                item,
                target=target_location,
                primary_group=str(business.get("primary_group") or ""),
                business_format=str(business.get("business_format") or ""),
                service_areas=service_areas,
                radius_miles=float(selected_radius),
            ),
        }
        for item in verified_candidates
    ]
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
            "Fewer than three verified AI-visible businesses are available. Use the relevant verified businesses available; a report can proceed without a forced comparison set."
        )
    existing_decisions = dict((durable_audit or {}).get("reviewer_decisions") or {})
    local_default_ids = [
        str(item["google_place_id"])
        for item in verified_candidates
        if item.get("location_classification") in {"local", "unknown"}
    ]
    wider_default_ids = [
        str(item["google_place_id"])
        for item in verified_candidates
        if item.get("location_classification") == "wider_area"
    ]
    eligible_default_ids = [*local_default_ids, *wider_default_ids]
    default_cohort = [
        item for item in existing_decisions.get("cohort_place_ids", []) if item in candidate_by_id
    ] or eligible_default_ids[:3]
    recommendation_counts = {
        str(item.get("google_place_id")): int(item.get("recommendations") or 0)
        for item in verified_candidates
    }
    owner_matches = match_owner_competitors(
        list((saved_brief or {}).get("owner_competitors") or []),
        business_records,
        recommendation_counts,
    )
    st.caption(
        f"Suggested catchment for this business type: {suggested_radius:.0f} miles. "
        "Owner-stated service areas take priority when provided."
    )
    if owner_matches:
        st.markdown("**The competitors the owner identified**")
        st.dataframe(
            pd.DataFrame([
                {
                    "Owner entry": item["owner_name"],
                    "Matched business": item["business_name"] if item["match_status"] == "matched" else "Needs confirmation",
                    "Benchmark result": item["visibility_status"],
                }
                for item in owner_matches
            ]),
            hide_index=True,
            use_container_width=True,
        )
    if default_cohort:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "AI-selected business": candidate_by_id[place_id]["business_name"],
                        "Recommendations": int(candidate_by_id[place_id].get("recommendations") or 0),
                        "Location": candidate_by_id[place_id].get("city") or "Not available",
                        "Catchment": str(candidate_by_id[place_id].get("location_classification") or "unknown").replace("_", " ").title(),
                    }
                    for place_id in default_cohort
                ]
            ),
            hide_index=True,
            use_container_width=True,
        )
    cohort_ids_for_quotes = tuple(dict.fromkeys([selected_place_id, *default_cohort]))
    st.markdown("**Evidence for the comparison businesses**")
    st.caption(
        "Section 4 collects evidence for this business only. The comparison page shows “Not assessed” for "
        "any comparison business without website pages, and its review evidence is reported as unavailable. "
        "Collect what exists for the businesses above; the report generates without it and says so."
    )
    comparison_evidence = []
    for place_id in cohort_ids_for_quotes:
        try:
            status = load_evidence_status(place_id)
        except Exception:
            status = {"website_audit": None, "review_count": 0}
        record = businesses_by_id.get(place_id, {})
        comparison_evidence.append(
            {
                "place_id": place_id,
                "name": clean_text(record.get("business_name")) or place_id,
                "group": clean_text(record.get("primary_group")) or "generic",
                "website_url": clean_text(record.get("source_website_url")),
                "pages": int((status["website_audit"] or {}).get("pages_crawled") or 0),
                "has_website_audit": status["website_audit"] is not None,
                "reviews": int(status["review_count"]),
                "is_target": place_id == selected_place_id,
            }
        )
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Business": ("Your client: " if item["is_target"] else "") + item["name"],
                    "Website pages saved": item["pages"] if item["has_website_audit"] else "None yet",
                    "Reviews saved": item["reviews"] if item["reviews"] else "None yet",
                }
                for item in comparison_evidence
            ]
        ),
        hide_index=True,
        use_container_width=True,
    )
    for item in comparison_evidence:
        if item["is_target"] or item["has_website_audit"]:
            continue
        if not item["website_url"]:
            st.caption(f"{item['name']}: no website is saved, so no website comparison is possible.")
            continue
        if st.button(
            f"Review the website of {item['name']}",
            key=f"review_comparison_website_{item['place_id']}",
            help="Visits public pages on this business's saved website and stores them as evidence.",
        ):
            try:
                with st.spinner(f"Reviewing {item['name']}'s website and saving the evidence…"):
                    review_comparison_website(
                        place_id=item["place_id"],
                        business_name=item["name"],
                        website_url=item["website_url"],
                        business_group=item["group"],
                    )
            except Exception as exc:
                st.error(f"The website of {item['name']} could not be reviewed. You can retry or continue without it.")
                st.exception(exc)
            else:
                st.cache_data.clear()
                st.rerun()
    if any(not item["reviews"] for item in comparison_evidence):
        st.caption(
            "Customer reviews are collected through the review tools, which can pull for several businesses at once "
            "and apply the cost ceiling."
        )
        if st.button("Open review tools for these businesses", key="open_review_tools_for_comparison"):
            st.session_state["active_diagnostic_cohort"] = {
                "target_google_place_id": selected_place_id,
                "target_business_name": str(business["business_name"]),
                "business_ids": list(cohort_ids_for_quotes),
            }
            st.switch_page("pages/7_Review_Insights.py")
    try:
        review_choices = load_review_choices(cohort_ids_for_quotes)
    except Exception:
        review_choices = []
    review_by_id = {str(item["review_id"]): item for item in review_choices}
    with st.form(f"report_review_{selected_place_id}"):
        with st.expander("Optional: override the AI-selected businesses"):
            selected_cohort = st.multiselect(
                "Comparison businesses",
                options=list(candidate_by_id),
                default=default_cohort,
                max_selections=3,
                format_func=lambda place_id: (
                    f"{candidate_by_id[place_id]['business_name']} — "
                    f"{int(candidate_by_id[place_id].get('recommendations') or 0)} recommendation(s) — "
                    f"{str(candidate_by_id[place_id].get('location_classification') or 'unknown').replace('_', ' ')}"
                ),
                help="Locally relevant businesses are suggested first. Wider or out-of-area results remain available when there is a clear reason.",
            )
        outside_selected = [
            candidate_by_id[item]["business_name"] for item in selected_cohort
            if candidate_by_id[item].get("location_classification") == "outside"
        ]
        if outside_selected:
            st.warning(
                "Outside the expected catchment: " + ", ".join(outside_selected)
                + ". Keep only when the wider-area comparison is genuinely relevant."
            )
        possible_target_names = find_possible_target_names(
            str(business["business_name"]), candidates["unresolved"]
        )
        stored_confirmed = set(existing_decisions.get("confirmed_target_names") or [])
        stored_rejected = set(existing_decisions.get("rejected_target_names") or [])
        target_name_choices: dict[str, str] = {}
        if possible_target_names:
            st.markdown("**Is the business under a different name in the AI answers?**")
            st.caption(
                f"The Google listing is “{business['business_name']}”. These names in the AI answers could not be "
                "matched to it automatically. If they are this business, its appearances would otherwise be "
                "left out and the report could wrongly say it did not appear. The report cannot be completed "
                "until each name is confirmed or rejected."
            )
            for position, option in enumerate(possible_target_names):
                target_name_choices[option["name"]] = st.radio(
                    f"“{option['name']}” — named in {option['recommendations']} answer(s). {option['reason']}.",
                    options=["undecided", "yes", "no"],
                    index=1 if option["name"] in stored_confirmed else (2 if option["name"] in stored_rejected else 0),
                    format_func={
                        "undecided": "Not decided",
                        "yes": "Yes, this is the business",
                        "no": "No, a different business",
                    }.get,
                    horizontal=True,
                    key=f"target_name_choice_{selected_place_id}_{position}",
                )
        priority_services = [str(item) for item in owner_context.get("priority_services") or []]
        try:
            review_questions = load_run_prompt_seed(saved_benchmark_run_id)
        except Exception:
            review_questions = []
        question_choices: dict[str, str] = {}
        if priority_services and review_questions:
            st.markdown("**Which of the owner's priorities does each question test?**")
            st.caption(
                "This lets the report show results for each priority. Choices are suggested from the wording "
                "and must be checked. A priority with no question is reported as not tested, not as absent."
            )
            stored_links = dict(existing_decisions.get("question_priority_map") or {})
            suggested_links = suggest_priority_map(review_questions, priority_services)
            link_options = ["", *priority_services, NOT_LINKED]
            for question in review_questions:
                order = str(int(question["base_prompt_order"]))
                preselected = stored_links.get(order) or suggested_links.get(order) or ""
                question_choices[order] = st.selectbox(
                    f"Q{order}: {question['prompt_text']}",
                    options=link_options,
                    index=link_options.index(preselected) if preselected in link_options else 0,
                    format_func=lambda value: "Choose…" if value == "" else value,
                    key=f"question_priority_{selected_place_id}_{order}",
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
            placeholder="Reviewer ideas only. The v4 report needs source-checked observations and completion checks before prescribing changes.",
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
            disabled=len(selected_cohort) > 3,
        )
    undecided_names = [
        name for name, choice in target_name_choices.items() if choice == "undecided"
    ] if (save_draft or complete_review) else []
    unlinked_questions = [
        order for order, choice in question_choices.items() if not choice
    ] if (save_draft or complete_review) else []
    if complete_review and (undecided_names or unlinked_questions):
        problems = []
        if undecided_names:
            problems.append(
                "whether these names are this business: " + ", ".join(f"“{name}”" for name in undecided_names)
            )
        if unlinked_questions:
            problems.append(
                "which priority each of these questions tests: " + ", ".join(f"Q{order}" for order in unlinked_questions)
            )
        st.error(
            "Before completing the review, decide " + "; and ".join(problems)
            + ". Your other changes have not been saved."
        )
    elif save_draft or complete_review:
        reviewer_decisions = {
            "confirmed_target_names": [n for n, c in target_name_choices.items() if c == "yes"],
            "rejected_target_names": [n for n, c in target_name_choices.items() if c == "no"],
            "question_priority_map": {order: choice for order, choice in question_choices.items() if choice},
            "cohort_place_ids": selected_cohort,
            "headline": " ".join(headline.split()),
            "summary": " ".join(summary.split()),
            "action_titles": [line.strip(" \t-•") for line in action_titles.splitlines() if line.strip(" \t-•")],
            "review_quote_ids": selected_quotes,
            "review_notes": " ".join(review_notes.split()),
            "owner_competitor_matches": owner_matches,
            "cohort_location_assessments": {
                place_id: {
                    key: candidate_by_id[place_id].get(key)
                    for key in ("city", "address", "location_classification", "location_reason", "distance_miles", "catchment_radius_miles")
                }
                for place_id in selected_cohort
            },
            "catchment_radius_miles": float(selected_radius),
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

st.subheader("6. Generate report")
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
        st.caption(f"Saved AI Visibility run: {report_run_id}")
        report_kind = st.radio(
            "Report type",
            options=["full", "summary"],
            format_func={
                "full": "Full evidence report (RP)",
                "summary": "Client summary (LS)",
            }.get,
            horizontal=True,
            key=f"report_kind_{selected_place_id}",
        )
        st.caption(
            "Detailed, evidence-led report with the questions, methods and sources in appendices."
            if report_kind == "full"
            else "Six pages in plain language: the result, what was tested, where the business appeared, "
            "who else appeared, three actions and how to follow up. Same saved evidence and counts as the full report. "
            "When it is generated it also reads the website's robots.txt (a read-only request) to see whether AI search "
            "crawlers are blocked; any block found becomes a sourced action."
        )
        summary_is_draft = True
        if report_kind == "summary":
            summary_is_draft = st.checkbox(
                "Mark the summary as a draft",
                value=True,
                key=f"summary_draft_{selected_place_id}",
                help="Adds a small DRAFT label to each page header. Untick it once the report has been checked and signed off.",
            )
        generate = st.button(
            "Generate report from saved evidence" if report_kind == "full" else "Generate client summary from saved evidence",
            type="primary",
            use_container_width=True,
        )

    summary_key = definition.key if definition else f"generic_{durable_audit['id']}"
    if generate and report_kind == "summary":
        try:
            with st.spinner("Assembling the saved evidence and laying out the client summary…"):
                summary_site_url, summary_findings = site_findings_for(business, durable_audit)
                summary_payload = (
                    definition.assembler()
                    if definition is not None
                    else assemble_generic_report_payload(durable_audit, site_findings=summary_findings)
                )
                summary_data = build_client_summary_report(
                    summary_payload,
                    site_findings=summary_findings,
                    website_checked=bool(summary_site_url),
                    draft=summary_is_draft,
                    business_group=str(business.get("primary_group") or ""),
                    owner_questions=list((saved_brief or {}).get("desired_searches") or []),
                    reviewer_action_titles=list(
                        dict((durable_audit or {}).get("reviewer_decisions") or {}).get("action_titles") or []
                    ),
                )
                summary_pdf = render_client_summary_pdf(summary_data)
        except ValueError as exc:
            st.error(f"The client summary could not be created. {exc}")
        except Exception as exc:
            st.error(
                "The client summary could not be generated from the saved evidence. "
                "AI Visibility was not rerun and no data was changed."
            )
            st.exception(exc)
        else:
            st.session_state[SUMMARY_STATE_KEY] = {"key": summary_key, "pdf": summary_pdf}

    saved_summary = st.session_state.get(SUMMARY_STATE_KEY)
    if report_kind == "summary" and saved_summary and saved_summary["key"] == summary_key:
        st.success("The client summary is ready.")
        st.download_button(
            "Download client summary",
            data=saved_summary["pdf"],
            file_name=(
                re.sub(r"[^a-z0-9]+", "-", report_client_name.lower()).strip("-") or "business"
            ) + "-ai-visibility-summary.pdf",
            mime="application/pdf",
            type="primary",
            use_container_width=True,
        )
        st.caption(
            "Generated in memory from the same saved evidence as the full report. The actions are suggested checks, "
            "not confirmed gaps. Downloading it does not freeze or save a report snapshot."
        )

    if generate and report_kind == "full":
        try:
            with st.spinner("Assembling the saved evidence and laying out the report…"):
                reviewable = (
                    build_reviewable_poc_audit(definition)
                    if definition is not None
                    else build_reviewable_generic_audit(
                        durable_audit, site_findings=site_findings_for(business, durable_audit)[1]
                    )
                )
        except Exception as exc:
            st.error(
                "The report could not be generated from the configured evidence. "
                "AI Visibility was not rerun and no data was changed."
            )
            st.exception(exc)
        else:
            st.session_state[REPORT_STATE_KEY] = reviewable

    reviewable = st.session_state.get(REPORT_STATE_KEY)
    expected_definition_key = definition.key if definition else f"generic_{durable_audit['id']}"
    if report_kind == "full" and reviewable is not None and reviewable.definition.key == expected_definition_key:
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
        if reviewable.payload.get("report", {}).get("report_format") == "accessible_owner_services_v4":
            from src.owner_services_report import evidence_index_html
            index_name = reviewable.payload["report"].get("owner_report", {}).get("evidence_index", "Report evidence index.html")
            st.download_button(
                "Download companion evidence index",
                data=evidence_index_html(reviewable.payload),
                file_name=index_name,
                mime="text/html",
                use_container_width=True,
            )
            st.caption("Keep the evidence index beside the PDF so its saved-answer links work. It contains original answers and saved research, not newly collected evidence.")
