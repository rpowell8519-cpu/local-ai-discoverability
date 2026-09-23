from __future__ import annotations

from dataclasses import dataclass

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
if (
    getattr(visibility_runner, "SUPPORTED_BENCHMARK_MODES", frozenset()) != frozenset({"model_memory", "search_grounded"})
    or getattr(anthropic_provider, "REQUIRED_SEARCH_VERSION", 0) != 1
    or visibility_runner.call_anthropic is not anthropic_provider.call_anthropic
):
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
    get_audit_pages,
    get_latest_audits,
    save_audit_page,
)
from src.review_repository import get_reviews  # noqa: E402
from src.evidence_analysis import MAX_LEADERS, MIN_LEADERS, analyse_evidence, select_leaders  # noqa: E402
from src.client_summary.actions import has_builtin_profile  # noqa: E402
from src import type_wording as type_wording_tools  # noqa: E402
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
from src.business_matching import (  # noqa: E402
    TARGET_KEY,
    UndecidedNamesError,
    conflicting_confirmations,
    default_owner_match,
    owner_competitor_candidates,
    owner_key,
    plan_subjects,
    undecided_items,
)
from src.client_summary.pdf import join_names  # noqa: E402
from src.report_identity import (  # noqa: E402
    UndecidedTargetNamesError,
    find_possible_target_names,
    undecided_target_names,
)
from src.site_checks import check_ai_crawler_access, crawler_finding  # noqa: E402
from src.report_priorities import NOT_LINKED, suggest_priority_map, undecided_questions  # noqa: E402
from src.report_competitors import (  # noqa: E402
    MAX_COMPARISON_BUSINESSES,
    catchment_radius_miles,
    resolve_run_location,
    select_comparison_set,
    classify_location,
    match_owner_competitors,
)
from src.report_audit_workflow import (  # noqa: E402
    AuditWorkflowInput,
    EvidenceState,
    workflow_summary,
)
import src.report_audit_repository as report_audit_repository  # noqa: E402

# A running Streamlit worker may retain the pre-history module after deployment.
# Refresh it before importing the new API, just as for the benchmark API above.
if any(not hasattr(report_audit_repository, name) for name in (
    "list_report_audit_revisions", "restore_report_audit_revision",
)):
    report_audit_repository = importlib.reload(report_audit_repository)

from src.report_audit_repository import (  # noqa: E402
    attach_benchmark_revision,
    get_latest_report_audit,
    list_report_audit_revisions,
    restore_report_audit_revision,
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


BUILD_VERSION = "Accessible AI Report Generator v3.9.0 (switch between saved versions of a business)"
REPORT_STATE_KEY = "accessible_ai_report_generator_result"
SUMMARY_STATE_KEY = "accessible_ai_client_summary_result"

@dataclass(frozen=True)
class ReportType:
    """One kind of report the page can produce. Add an entry here and its two handlers in the generate step."""

    key: str
    label: str
    description: str
    button: str


REPORT_TYPES = (
    ReportType(
        "full", "Full evidence report (RP)",
        "Detailed, evidence-led report with the questions, methods and sources in appendices.",
        "Generate report from saved evidence",
    ),
    ReportType(
        "summary", "Client summary (LS)",
        "Six pages in plain language: the result, what was tested, where the business appeared, "
        "who else appeared, three actions and how to follow up. Same saved evidence and counts as the full report. "
        "When it is generated it also reads the website's robots.txt (a read-only request) to see whether AI search "
        "crawlers are blocked; any block found becomes a sourced action.",
        "Generate client summary from saved evidence",
    ),
)
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
            ) as source_website_url,
            nullif(rol.raw_data->>'rating', '') as google_rating,
            nullif(rol.raw_data->>'reviews', '') as google_reviews
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


@st.cache_data(ttl=60)
def load_evidence_frames(place_ids: tuple[str, ...]):
    """Saved website audits, their pages and review text for the client and the most visible businesses."""

    ids = list(place_ids)
    audits = get_latest_audits(ids)
    pages_by_run = {}
    if not audits.empty:
        for row in audits.to_dict("records"):
            try:
                pages_by_run[str(row["id"])] = get_audit_pages(str(row["id"]))
            except Exception:
                pages_by_run[str(row["id"])] = pd.DataFrame()
    return audits, pages_by_run, get_reviews(ids)


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
def load_revision_history(google_place_id: str) -> list[dict[str, Any]]:
    """Every saved revision for this business, most recent first."""

    return list_report_audit_revisions(google_place_id)


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


def google_review_text(record: Mapping[str, Any]) -> str | None:
    """Google's own review count and rating from the saved listing, or None if it is missing or unreadable."""

    try:
        count = int(float(clean_text(record.get("google_reviews")).replace(",", "")))
    except ValueError:
        return None
    text = f"{count:,} reviews"
    try:
        text += f", {float(clean_text(record.get('google_rating'))):g} stars"
    except ValueError:
        pass
    return text


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
    other_revisions = [
        row for row in load_revision_history(selected_place_id) if int(row["revision"]) != int(durable_audit["revision"])
    ]
    if other_revisions:
        with st.expander(f"Switch to a different saved version of this report ({len(other_revisions) + 1} saved)"):
            st.caption(
                "This business has been set up more than once, for example for two different customer-intent "
                "audits of the same business. Nothing here is ever deleted: switching makes an earlier version "
                "current again, as a new saved revision, and you can switch back the same way. This changes what "
                "everyone sees when they open this business, including its saved review decisions."
            )
            labels = {
                int(row["revision"]): (
                    f"Revision {row['revision']} — {clean_text(row.get('revision_reason')) or 'saved'} — "
                    f"{(clean_text(row.get('known_for')) or 'no known-for text saved')[:70]}"
                    + (" — review complete" if row.get("reviewer_decisions_complete") else " — review not complete")
                )
                for row in other_revisions
            }
            chosen_revision = st.selectbox(
                "An earlier saved version",
                options=sorted(labels, reverse=True),
                format_func=labels.get,
                key=f"revision_pick_{selected_place_id}",
            )
            if st.button("Make this the current version", key=f"revision_restore_{selected_place_id}"):
                try:
                    restore_report_audit_revision(selected_place_id, int(chosen_revision))
                except Exception as exc:
                    st.error("That version could not be restored.")
                    st.exception(exc)
                else:
                    st.cache_data.clear()
                    st.rerun()

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
        "Website and review evidence for the client and the most visible businesses is what the recommendations are based on, "
        "in every report type. Collect it here. Where it genuinely does not exist (no website, no reviews), you can accept "
        "going ahead without it in step 5, and the report will say so."
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
                    finished = str(response.get("status") or "").strip().casefold() == "success"
                    if matching_api_reviews.empty and not finished:
                        st.info(f"The request is currently {response.get('status') or 'processing'}; check again in a moment.")
                    elif matching_api_reviews.empty:
                        st.warning(
                            "Outscraper finished, but returned no reviews with text for this business. Only reviews with "
                            "text are used as evidence; a star rating with no text is not enough."
                        )
                        st.session_state.pop(request_key, None)
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

review_update_reasons: list[str] = []
review_notice = None
if ai_ready and definition is None:
    st.subheader("5. Review the AI-selected comparison set")
    review_notice = st.empty()
    st.write(
        f"The report compares the business with up to {MAX_COMPARISON_BUSINESSES} others, {MAX_COMPARISON_BUSINESSES + 1} in all. "
        "The suggested set mixes the competitors the owner named with the most visible businesses in the AI "
        "answers, including any the owner named that the AI never recommended. A reviewer can change it "
        "when there is a clear relevance, location or identity reason."
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
    existing_decisions = dict((durable_audit or {}).get("reviewer_decisions") or {})
    names_by_id = {str(row["google_place_id"]): str(row["business_name"]) for row in business_records}
    owner_names_now = [str(name) for name in (saved_brief or {}).get("owner_competitors") or []]
    stored_places = dict(existing_decisions.get("owner_competitor_places") or {})
    owner_candidate_lists = {name: owner_competitor_candidates(name, business_records) for name in owner_names_now}
    # None means undecided; "" means the reviewer said it is not in the database.
    owner_defaults: dict[str, str | None] = {
        name: (str(stored_places[name]) if name in stored_places else default_owner_match(name, owner_candidate_lists[name]))
        for name in owner_names_now
    }
    owner_place_ids_now = [pid for pid in owner_defaults.values() if pid and pid != selected_place_id]
    # A business the owner named that the AI never recommended is still a comparison, with no appearances.
    present_ids = {str(item.get("google_place_id")) for item in verified_candidates}
    for pid in owner_place_ids_now:
        if pid not in present_ids and pid in businesses_by_id:
            record = businesses_by_id[pid]
            verified_candidates.append({
                "google_place_id": pid, "business_name": record["business_name"], "recommendations": 0,
                "city": record.get("city"), "address": record.get("address"), "latitude": record.get("latitude"),
                "longitude": record.get("longitude"), "primary_group": record.get("primary_group"),
                "business_format": record.get("business_format"),
            })
            present_ids.add(pid)
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
            "Fewer than three verified AI-visible businesses are available. Use the relevant businesses available, including any the owner named; a report can proceed without a forced comparison set."
        )
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
    ] or select_comparison_set([pid for pid in owner_place_ids_now if pid in candidate_by_id], eligible_default_ids)
    recommendation_counts = {
        str(item.get("google_place_id")): int(item.get("recommendations") or 0)
        for item in verified_candidates
    }
    owner_priorities_now = [str(item) for item in owner_context.get("priority_services") or []]
    try:
        questions_now = load_run_prompt_seed(saved_benchmark_run_id)
    except Exception:
        questions_now = []
    plan_cohort_ids = list(dict.fromkeys([*default_cohort, *owner_place_ids_now]))
    identity_plan = plan_subjects(
        target_id=selected_place_id,
        target_name=str(business["business_name"]),
        unresolved=candidates["unresolved"],
        owner_names=owner_names_now,
        owner_places={name: (pid or "") for name, pid in owner_defaults.items()},
        cohort_ids=plan_cohort_ids,
        names_by_id=names_by_id,
        records=business_records,
    )
    # A review saved before names and priorities were matched cannot yet make a correct report.
    for item in undecided_items(identity_plan, existing_decisions, owner_names_now):
        review_update_reasons.append(
            f"match the owner's competitor “{item['subject']}” to a business in the database"
            if not item.get("name") else
            f"confirm or reject the AI answer name “{item['name']}” (named in {item['recommendations']} answers) "
            f"as {item['subject']}"
        )
    names_ready = not undecided_items(identity_plan, existing_decisions, owner_names_now)
    saved_note = st.session_state.pop(f"review_note_{selected_place_id}", None)
    if saved_note:
        st.info(saved_note)
    # The most visible businesses depend on the name matches (an unmatched name is not credited to its business),
    # so evidence is only worth collecting once those are decided. Only the top few are studied: little is learned
    # from collecting pages and reviews for businesses the AI hardly recommends, and each costs time and money.
    leader_count = int(existing_decisions.get("leader_count") or MAX_LEADERS)
    if names_ready and len([c for c in verified_candidates if int(c.get("recommendations") or 0) > 0 and str(c["google_place_id"]) != selected_place_id]) > MIN_LEADERS:
        leader_count = st.slider(
            "How many of the most visible businesses to study", min_value=MIN_LEADERS, max_value=MAX_LEADERS,
            value=min(max(leader_count, MIN_LEADERS), MAX_LEADERS), key=f"leader_count_{selected_place_id}",
            help="Their websites and reviews are compared with the client's to ground the recommendations. Fewer means less time and cost.",
        )
    leaders_now = select_leaders(verified_candidates, selected_place_id, limit=leader_count) if names_ready else []
    evidence_analysis = None
    if names_ready:
        try:
            audits_frame, pages_frames, reviews_frame = load_evidence_frames(
                tuple([selected_place_id, *[str(item["google_place_id"]) for item in leaders_now]])
            )
            evidence_analysis = analyse_evidence(
                target_id=selected_place_id, target_name=str(business["business_name"]),
                primary_group=str(business.get("primary_group") or "generic"), leaders=leaders_now,
                audits=audits_frame, pages_by_run=pages_frames, propositions=owner_priorities_now, reviews=reviews_frame,
                type_wording=dict(existing_decisions.get("type_wording") or {}) or None,
            )
        except Exception as exc:
            st.warning("The comparison with the most visible businesses could not be run, so the report will not include recommendations from it. "
                       f"({type(exc).__name__})")
    evidence_candidates = list((evidence_analysis or {}).get("candidates") or [])
    saved_recommendation_choices = dict(existing_decisions.get("recommendation_decisions") or {})
    open_recommendations = [c for c in evidence_candidates if c["id"] not in saved_recommendation_choices]
    if open_recommendations:
        review_update_reasons.append(
            f"decide which of the {len(open_recommendations)} recommendation(s) from the evidence to include"
        )
    # Website and review evidence power every recommendation, so each layer must be present or knowingly waived.
    evidence_layer_labels = {"website": "website comparison", "reviews": "review text comparison"}
    saved_waivers = dict(existing_decisions.get("evidence_waivers") or {})
    missing_layers = {
        key: (str(((evidence_analysis or {}).get("layers") or {}).get(key, {}).get("note") or "The comparison could not be run."))
        for key in evidence_layer_labels
        if names_ready and (evidence_analysis is None or ((evidence_analysis.get("layers") or {}).get(key) or {}).get("status") != "used")
    }
    for key in missing_layers:
        if key not in saved_waivers:
            review_update_reasons.append(
                f"add the evidence for the {evidence_layer_labels[key]} (step 5, below the name matching), or accept going ahead without it"
            )
    unlinked_now = (
        undecided_questions(questions_now, owner_priorities_now, dict(existing_decisions.get("question_priority_map") or {}))
        if owner_priorities_now else []
    )
    if unlinked_now:
        review_update_reasons.append(
            "link " + ", ".join(f"Q{order}" for order in unlinked_now) + " to the owner priority each one tests"
        )
    if configuration_ready and review_update_reasons:
        review_notice.warning(
            "**This review was completed before some checks existed, so it needs one more look.** "
            "The report cannot be generated until you: " + "; ".join(review_update_reasons) + ". "
            "Make the choices in the form below, then click **Complete report review**."
        )
    st.caption(
        f"Suggested catchment for this business type: {suggested_radius:.0f} miles. "
        "Owner-stated service areas take priority when provided."
    )
    if owner_names_now:
        st.markdown("**The competitors the owner identified**")
        st.dataframe(
            pd.DataFrame([
                {
                    "Owner entry": name,
                    "Matched business": (
                        "Needs matching below" if owner_defaults[name] is None
                        else ("Not in the database" if owner_defaults[name] == "" else names_by_id.get(str(owner_defaults[name]), "Unknown"))
                    ),
                    "Benchmark result": (
                        "Identity needs confirmation" if owner_defaults[name] is None
                        else ("Not checked" if owner_defaults[name] == "" else (
                            f"Recommended {recommendation_counts.get(str(owner_defaults[name]), 0)} times"
                            if recommendation_counts.get(str(owner_defaults[name]), 0) else "Not recommended in this benchmark"))
                    ),
                }
                for name in owner_names_now
            ]),
            hide_index=True,
            use_container_width=True,
        )
    if default_cohort:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Comparison business": candidate_by_id[place_id]["business_name"],
                        "Chosen because": "Named by the owner" if place_id in owner_place_ids_now else "Most visible in the AI answers",
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
    evidence_ids = tuple(dict.fromkeys([selected_place_id, *[str(item["google_place_id"]) for item in leaders_now]]))
    st.markdown("**Evidence for the client and the most visible businesses**")
    if names_ready:
        st.caption(
            f"Evidence is collected for the client and the {len(leaders_now)} most visible business"
            f"{'es' if len(leaders_now) != 1 else ''} only, because that is what the recommendations compare with. Other "
            "comparison businesses appear in the report's counts and need no pages or reviews."
        )
    else:
        st.info(
            "Match the AI answer names and the owner's competitors below and save the review draft first. Which businesses are "
            "the most visible depends on those matches, so their websites and reviews are collected after that, not before."
        )
    st.caption(
        "**About reviews.** They do not affect the AI visibility counts: the AI platforms answer without reading "
        "reviews. Saved review text is supporting evidence only. It appears as the review counts in the report's "
        "appendix and as any customer quotations you choose. “Google reports” is the count and rating in the "
        "business's saved Google listing, so you can see whether the reviews we hold are all of them or a sample."
    )
    comparison_evidence = []
    for place_id in (evidence_ids if names_ready else ()):
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
                "google": google_review_text(record),
                "is_target": place_id == selected_place_id,
            }
        )
    if comparison_evidence:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Business": ("Your client: " if item["is_target"] else "") + item["name"],
                        "Website pages saved": str(item["pages"]) if item["has_website_audit"] else "None yet",
                        "Google reports": item["google"] or "Not recorded",
                        "Review text saved": str(item["reviews"]) if item["reviews"] else "None yet",
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
    without_reviews = [item for item in comparison_evidence if not item["reviews"]]
    if without_reviews:
        st.markdown("**Collect Google reviews for the businesses that have none saved**")
        st.caption(
            "This pays Outscraper for review text. It is used as supporting evidence for recommendations, never in the "
            "AI visibility counts. Nothing is requested until you press the button."
        )
        review_key = secret_value("OUTSCRAPER_API_KEY")
        if not review_key:
            st.info("Outscraper is not connected. Ask an administrator to add the API key, or upload a review file in step 4.")
        else:
            chosen_for_reviews = st.multiselect(
                "Businesses to collect reviews for",
                options=[item["place_id"] for item in without_reviews],
                default=[item["place_id"] for item in without_reviews],
                format_func=lambda pid: next(i["name"] for i in without_reviews if i["place_id"] == pid),
                key=f"collect_review_places_{selected_place_id}",
            )
            per_business_limit = st.selectbox(
                "Maximum reviews per business", options=[50, 100, 200], index=1,
                key=f"collect_review_limit_{selected_place_id}",
            )
            in_ceiling, projected = review_pull_within_cost_ceiling(
                requested_reviews=len(chosen_for_reviews) * int(per_business_limit), ceiling_gbp=DEFAULT_APP_COST_CEILING_GBP
            )
            st.caption(
                f"{len(chosen_for_reviews)} business(es) × up to {per_business_limit} reviews: conservative estimated maximum "
                f"cost £{projected:.2f}. The app ceiling is £{DEFAULT_APP_COST_CEILING_GBP:.2f}."
                + ("" if in_ceiling else " That is over the ceiling; choose fewer businesses or a lower limit.")
            )
            batch_key = f"report_outscraper_batch_{selected_place_id}"
            if st.button(
                "Request reviews from Outscraper", key=f"collect_reviews_go_{selected_place_id}",
                disabled=not chosen_for_reviews or not in_ceiling, use_container_width=True,
            ):
                try:
                    submitted = submit_google_reviews(
                        api_key=review_key, place_ids=list(chosen_for_reviews), reviews_limit=int(per_business_limit)
                    )
                except OutscraperError as exc:
                    st.error(f"Outscraper could not start the request: {exc}")
                else:
                    st.session_state[batch_key] = {"id": str(submitted.get("id") or ""), "places": list(chosen_for_reviews)}
                    st.success("Review collection started. Use the check button below when it has finished.")
            pending = st.session_state.get(batch_key) or {}
            if pending.get("id") and st.button("Check and import collected reviews", key=f"collect_reviews_check_{selected_place_id}",
                                              use_container_width=True):
                try:
                    response = get_request_result(api_key=review_key, request_id=pending["id"])
                    frame = flatten_google_reviews_response(response.get("data"))
                    frame = frame[frame["place_id"].fillna("").astype(str).isin(pending["places"])].copy() if not frame.empty else frame
                    finished = str(response.get("status") or "").strip().casefold() == "success"
                    if frame.empty and not finished:
                        st.info(f"The request is currently {response.get('status') or 'processing'}; check again in a moment.")
                    elif frame.empty:
                        st.warning(
                            "Outscraper finished, but returned no reviews with text for these businesses. Only reviews "
                            "with text are used as evidence; a business with only star-rating reviews and no text will "
                            "never have anything to import here. If that's a genuine limitation, accept going ahead "
                            "without review evidence for it in the section below."
                        )
                        st.session_state.pop(batch_key, None)
                    else:
                        imported = import_reviews(frame, source_file_name=api_import_source_name(pending["id"]))
                        st.session_state.pop(batch_key, None)
                        st.success(f"Imported {int(imported['processed_rows']):,} review(s) for {frame['place_id'].nunique()} business(es).")
                        st.cache_data.clear()
                        st.rerun()
                except (OutscraperError, ValueError) as exc:
                    st.error(f"The review request could not be checked: {exc}")
        if st.button("Open advanced review tools", key="open_review_tools_for_comparison"):
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
    if evidence_analysis is not None:
        st.markdown("**What the recommendations from the evidence are based on**")
        st.caption(
            "The client's saved website, and its reviews, are compared with the businesses the AI actually recommended. "
            "A competitor the owner named that the AI never recommended is not used as a leader. Recommendations only "
            "appear where the evidence supports them, and each says what was and was not detected, never why."
        )
        layer_names = {"website": "Website comparison", "propositions": "Owner priorities on the websites", "reviews": "Review text"}
        st.dataframe(
            pd.DataFrame([
                {"Layer": layer_names[key], "Status": "Used" if info["status"] == "used" else "Not available", "Detail": info["note"]}
                for key, info in evidence_analysis["layers"].items()
            ]),
            hide_index=True, use_container_width=True,
        )
        if evidence_analysis["leaders"]:
            st.dataframe(
                pd.DataFrame([
                    {"Most visible business": item["business_name"], "Recommended in": f"{item['recommendations']} answers",
                     "Website read": item["website_read"] or "Not saved", "Reviews saved": item["reviews"]}
                    for item in evidence_analysis["leaders"]
                ]),
                hide_index=True, use_container_width=True,
            )
        if any(info["status"] != "used" for info in evidence_analysis["layers"].values()):
            st.caption(
                "A layer that is not available can be added by collecting the missing website pages or review text in the "
                "evidence panel above. The report says which layers it used."
            )
    # Wording for a kind of business nobody has written specific wording for.
    type_group = str(business.get("primary_group") or "generic")
    saved_type_wording = dict(existing_decisions.get("type_wording") or {})
    saved_draft = dict(existing_decisions.get("type_wording_draft") or {})
    if saved_type_wording or saved_draft or not has_builtin_profile(type_group):
        st.markdown("**Wording for this kind of business**")
        st.caption(
            "There is no built-in wording for this kind of business, so reports use general wording (“enquire or book”, "
            "“prices or price guidance”). An AI can draft wording that fits it (how customers book, what prices are called, "
            "what reviewers of this kind of business talk about). It is only a draft: it is used in the report only after you "
            "have read it and pressed save. Saving asks for the review to be completed again."
        )
        draft_key = f"type_wording_draft_{selected_place_id}"
        working = st.session_state.get(draft_key) or saved_draft or saved_type_wording
        if saved_draft and not st.session_state.get(draft_key):
            st.caption("A draft from before is shown below (it is saved automatically as you draft, so reloading the page does not lose it).")
        claude_key = secret_value("ANTHROPIC_API_KEY")
        if not claude_key:
            st.info("The AI service is not connected, so wording can only be typed in by hand.")
        elif st.button("Draft wording with AI (one short paid request)", key=f"type_wording_go_{selected_place_id}"):
            try:
                with st.spinner("Drafting wording…"):
                    drafted = type_wording_tools.draft_type_wording(
                        type_wording_tools.call_claude(claude_key, DEFAULT_MODELS["Claude"]),
                        business_type=str(business.get("raw_category") or type_group).replace("_", " "),
                        known_for=str(saved_brief.get("known_for") or ""),
                        priorities=owner_priorities_now,
                        questions=[str(q) for q in saved_brief.get("desired_searches") or []],
                    )
            except type_wording_tools.InvalidWordingError as exc:
                st.error(f"The draft could not be used: {exc} Try again, or type the wording in by hand.")
            except Exception as exc:
                st.error(f"The AI service could not be reached ({type(exc).__name__}). Nothing was changed.")
            else:
                st.session_state[draft_key] = drafted
                # Saved immediately so the paid draft survives a reload; it is not used in the report until "Save" below.
                try:
                    save_reviewer_decisions_revision(
                        target_google_place_id=selected_place_id,
                        reviewer_decisions={**existing_decisions, "type_wording_draft": drafted}, complete=False,
                    )
                except Exception:
                    pass  # the draft still shows for this session even if the background save failed
                st.rerun()
        version = abs(hash(str(working))) % 100000
        tw_label = st.text_input("Kind of business", value=str(working.get("label") or ""), key=f"tw_label_{selected_place_id}_{version}")
        tw_booking = st.text_input("How customers book (completes “Make it obvious how to …”)", value=str(working.get("booking") or ""), key=f"tw_booking_{selected_place_id}_{version}")
        tw_pricing = st.text_input("What prices are called", value=str(working.get("pricing") or ""), key=f"tw_pricing_{selected_place_id}_{version}")
        tw_questions = st.text_input("What customers ask before they enquire", value=str(working.get("questions") or ""), key=f"tw_questions_{selected_place_id}_{version}")
        tw_details = st.text_input("What a listing or website should show", value=str(working.get("details") or ""), key=f"tw_details_{selected_place_id}_{version}")
        tw_themes = st.text_area(
            "What reviewers of this kind of business talk about (one per line: label | category | phrase; phrase; phrase)",
            value=type_wording_tools.themes_to_text(working.get("review_themes") or []), key=f"tw_themes_{selected_place_id}_{version}",
        )
        tw_checks = st.text_area(
            "Website topics to check on this business's site and its competitors' (one per line: label | phrase; phrase | url word; url word)",
            value=type_wording_tools.site_checks_to_text(working.get("site_checks") or []), key=f"tw_checks_{selected_place_id}_{version}",
            help="These are looked for in the website pages already saved, so nothing is re-crawled. A topic that is one of the owner's priorities is not recommended twice.",
        )
        save_col, clear_col = st.columns(2)
        with save_col:
            if st.button("Save this wording for the report", key=f"type_wording_save_{selected_place_id}"):
                try:
                    wording = type_wording_tools.validate_wording({
                        "label": tw_label, "booking": tw_booking, "pricing": tw_pricing, "questions": tw_questions,
                        "details": tw_details, "review_themes": type_wording_tools.themes_from_text(tw_themes),
                        "site_checks": type_wording_tools.site_checks_from_text(tw_checks),
                    })
                except type_wording_tools.InvalidWordingError as exc:
                    st.error(f"Not saved: {exc}")
                else:
                    try:
                        save_reviewer_decisions_revision(
                            target_google_place_id=selected_place_id,
                            reviewer_decisions={
                                **{k: v for k, v in existing_decisions.items() if k != "type_wording_draft"},
                                "type_wording": wording,
                            },
                            complete=False,
                        )
                    except Exception as exc:
                        st.error("The wording could not be saved.")
                        st.exception(exc)
                    else:
                        st.session_state.pop(draft_key, None)
                        st.cache_data.clear()
                        st.rerun()
        with clear_col:
            if (saved_type_wording or saved_draft) and st.button("Go back to the general wording", key=f"type_wording_clear_{selected_place_id}"):
                try:
                    save_reviewer_decisions_revision(
                        target_google_place_id=selected_place_id,
                        reviewer_decisions={k: v for k, v in existing_decisions.items() if k not in ("type_wording", "type_wording_draft")},
                        complete=False,
                    )
                except Exception as exc:
                    st.error("The change could not be saved.")
                    st.exception(exc)
                else:
                    st.session_state.pop(draft_key, None)
                    st.cache_data.clear()
                    st.rerun()
    with st.form(f"report_review_{selected_place_id}"):
        with st.expander("Optional: override the AI-selected businesses"):
            selected_cohort = st.multiselect(
                "Comparison businesses",
                options=list(candidate_by_id),
                default=default_cohort,
                max_selections=MAX_COMPARISON_BUSINESSES,
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
        # Names the AI used that may be a business in this report, and the owner's own competitor names.
        name_choices: list[dict[str, Any]] = []
        owner_place_choices: dict[str, str] = {}
        stored_links = dict(existing_decisions.get("name_links") or {})
        if any(subject.names or subject.owner_name for subject in identity_plan):
            st.markdown("**Match the names the AI used to the right businesses**")
            st.caption(
                "The AI, the owner and Google often name the same business differently, so a business can be "
                "counted under several names and look less visible than it is. Say which names are the same "
                "business. Nothing is matched until you decide, and the report cannot be completed while any "
                "choice is open."
            )
        decision_labels = {"undecided": "Not decided", "yes": "Yes, the same business", "no": "No, a different business"}
        for position, subject in enumerate(identity_plan):
            if subject.owner_name:
                st.markdown(f"**The owner named “{subject.owner_name}”**")
                candidate_ids = [str(c["google_place_id"]) for c in owner_candidate_lists[subject.owner_name]]
                current = owner_defaults[subject.owner_name]
                if current and current not in candidate_ids:
                    candidate_ids.insert(0, current)
                options = ["", *candidate_ids, "__none__"]
                index = 0 if current is None else (options.index("__none__") if current == "" else options.index(current))
                suggested = (
                    "  (suggested from the name: please check)"
                    if current and subject.owner_name not in stored_places else ""
                )
                choice = st.selectbox(
                    f"Which business in the database is this?{suggested}",
                    options=options,
                    index=index,
                    format_func=lambda value: (
                        "Choose…" if value == ""
                        else "Not in the database: keep the owner's name" if value == "__none__"
                        else business_label(businesses_by_id[value])
                    ),
                    key=f"owner_place_{selected_place_id}_{position}",
                )
                owner_place_choices[subject.owner_name] = choice
            elif subject.names and subject.outside_set:
                st.markdown(f"**Is a name in the answers really {subject.label}?**")
                st.caption(
                    f"{subject.label} is in the database but is not in this comparison. The AI used a name that looks like "
                    "it. If it is the same business, its appearances are counted for it (and it can then be added to the "
                    "comparison after you save)."
                )
            elif subject.names and subject.key != TARGET_KEY:
                st.markdown(f"**Is another name in the answers the same business as {subject.label}?**")
            elif subject.names:
                st.markdown("**Is the business under a different name in the AI answers?**")
                st.caption(
                    f"The Google listing is “{business['business_name']}”. If these names are this business, its "
                    "appearances would otherwise be left out and the report could wrongly say it did not appear."
                )
            saved_names = stored_links.get(subject.key, {}) if subject.key != TARGET_KEY else {
                "confirmed": existing_decisions.get("confirmed_target_names") or [],
                "rejected": existing_decisions.get("rejected_target_names") or [],
            }
            for flagged_position, option in enumerate(subject.names):
                saved_choice = "yes" if option["name"] in (saved_names.get("confirmed") or []) else (
                    "no" if option["name"] in (saved_names.get("rejected") or []) else "undecided")
                radio_key = (
                    f"target_name_choice_{selected_place_id}_{flagged_position}" if subject.key == TARGET_KEY
                    else f"name_choice_{selected_place_id}_{position}_{flagged_position}"
                )
                name_choices.append({
                    "subject": subject, "name": option["name"],
                    "choice": st.radio(
                        f"“{option['name']}” — named in {option['recommendations']} answer(s). {option['reason']}.",
                        options=["undecided", "yes", "no"],
                        index=["undecided", "yes", "no"].index(saved_choice),
                        format_func=decision_labels.get,
                        horizontal=True,
                        key=radio_key,
                    ),
                })
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
                suggestion_note = "" if stored_links.get(order) or not preselected else "  (suggested from the wording: please check)"
                question_choices[order] = st.selectbox(
                    f"Q{order}: {question['prompt_text']}{suggestion_note}",
                    options=link_options,
                    index=link_options.index(preselected) if preselected in link_options else 0,
                    format_func=lambda value: "Choose…" if value == "" else value,
                    key=f"question_priority_{selected_place_id}_{order}",
                )
                better = suggested_links.get(order)
                if stored_links.get(order) and better and better != stored_links[order]:
                    st.caption(
                        f":orange[Check Q{order}: it is linked to “{stored_links[order]}”, but its wording fits "
                        f"“{better}” better.]"
                    )
        recommendation_choices: dict[str, str] = {}
        recommendation_wording: dict[str, str] = {}
        if evidence_candidates:
            st.markdown("**Recommendations from the evidence**")
            st.caption(
                "Each one compares what was detected on the client's saved pages, or in its reviews, with the most visible "
                "businesses. Nothing goes into the report until you include it. You can change the wording for the client; "
                "the numbers and the evidence stay as found. The report cannot be completed while any is undecided."
            )
            saved_wording = {item["id"]: item for item in existing_decisions.get("approved_recommendations") or []}
            for position, candidate in enumerate(evidence_candidates):
                with st.container(border=True):
                    kind = "Observation from reviews" if candidate["kind"] == "finding" else "Recommendation"
                    st.markdown(
                        f"**{candidate['title']}**  \n:gray[{kind} · confidence {candidate['confidence']}"
                        + (f" · prevalence {candidate['prevalence']}" if candidate["prevalence"] else "")
                        + (" · housekeeping, not expected to change AI answers" if candidate["hygiene"] else "") + "]"
                    )
                    st.write(candidate["observation"])
                    if candidate["evidence"]:
                        st.caption("Evidence: " + "  |  ".join(
                            f"{e['business']}: {e['note']} (read {e['read_on'] or 'date not saved'})" for e in candidate["evidence"]
                        ))
                    saved_choice = saved_recommendation_choices.get(candidate["id"], "undecided")
                    recommendation_choices[candidate["id"]] = st.radio(
                        "Include in the report?",
                        options=["undecided", "include", "leave_out"],
                        index=["undecided", "include", "leave_out"].index(saved_choice if saved_choice in ("include", "leave_out") else "undecided"),
                        format_func={"undecided": "Not decided", "include": "Include", "leave_out": "Leave out"}.get,
                        horizontal=True,
                        key=f"rec_choice_{selected_place_id}_{position}",
                    )
                    if candidate["kind"] == "action":
                        recommendation_wording[candidate["id"]] = st.text_area(
                            "Wording for the client",
                            value=(saved_wording.get(candidate["id"]) or {}).get("action") or candidate["action"],
                            max_chars=380,
                            key=f"rec_wording_{selected_place_id}_{position}",
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
        waiver_choices: dict[str, bool] = {}
        if missing_layers:
            st.markdown("**Evidence the recommendations could not draw on**")
            st.caption(
                "Recommendations are grounded in the client's website and reviews compared with the most visible businesses. "
                "Add the missing evidence in step 4 if it exists. Only where it genuinely does not exist, accept going ahead "
                "without it: the report will say so."
            )
            for key, note in missing_layers.items():
                waiver_choices[key] = st.checkbox(
                    f"Go ahead without the {evidence_layer_labels[key]}. {note}",
                    value=key in saved_waivers, key=f"waive_{key}_{selected_place_id}",
                )
        review_columns = st.columns(2)
        save_draft = review_columns[0].form_submit_button("Save review draft", use_container_width=True)
        complete_review = review_columns[1].form_submit_button(
            "Complete report review",
            type="primary",
            use_container_width=True,
            disabled=len(selected_cohort) > MAX_COMPARISON_BUSINESSES,
        )
    checking = save_draft or complete_review
    open_names = [item for item in name_choices if item["choice"] == "undecided"] if checking else []
    unchosen_owners = [name for name, choice in owner_place_choices.items() if choice == ""] if checking else []
    unlinked_questions = [
        order for order, choice in question_choices.items() if not choice
    ] if checking else []
    open_recs = [cid for cid, choice in recommendation_choices.items() if choice == "undecided"] if checking else []
    open_waivers = [key for key, accepted in waiver_choices.items() if not accepted] if checking else []
    target_items = [item for item in name_choices if item["subject"].key == TARGET_KEY] if checking else []
    chosen_places = ({name: ("" if choice == "__none__" else choice) for name, choice in owner_place_choices.items() if choice != ""}
                     if checking else {})
    links: dict[str, dict[str, list[str]]] = {}
    if checking:
        for item in name_choices:
            if item["subject"].key == TARGET_KEY or item["choice"] == "undecided":
                continue
            owner = item["subject"].owner_name
            key = (chosen_places.get(owner) or owner_key(owner)) if owner else item["subject"].key
            entry = links.setdefault(key, {"confirmed": [], "rejected": []})
            entry["confirmed" if item["choice"] == "yes" else "rejected"].append(item["name"])
    conflicts = conflicting_confirmations(identity_plan, {
        "confirmed_target_names": [i["name"] for i in target_items if i["choice"] == "yes"], "name_links": links,
    }) if checking else []
    if complete_review and (open_names or unchosen_owners or unlinked_questions or open_recs or open_waivers or conflicts):
        problems = []
        if unchosen_owners:
            problems.append(
                "which business in the database these owner competitors are: " + ", ".join(f"“{n}”" for n in unchosen_owners)
            )
        if open_names:
            problems.append(
                "whether these AI answer names are the same business: "
                + ", ".join(f"“{item['name']}”" for item in open_names)
            )
        if unlinked_questions:
            problems.append(
                "which priority each of these questions tests: " + ", ".join(f"Q{order}" for order in unlinked_questions)
            )
        if open_recs:
            titles = {c["id"]: c["title"] for c in evidence_candidates}
            problems.append(
                "which recommendations from the evidence to include: " + ", ".join(f"“{titles[cid]}”" for cid in open_recs)
            )
        if open_waivers:
            problems.append(
                "the missing evidence: add it in step 4, or tick to go ahead without the "
                + " and the ".join(evidence_layer_labels[key] for key in open_waivers)
            )
        if conflicts:
            problems.append(
                "these names, each confirmed for more than one business — confirm at most one, and reject the rest: "
                + "; ".join(f"“{c['name']}” for {join_names(c['businesses'])}" for c in conflicts)
            )
        st.error(
            "Before completing the review, decide " + "; and ".join(problems)
            + ". Your other changes have not been saved."
        )
    elif checking:
        reviewer_decisions = {
            "confirmed_target_names": [i["name"] for i in target_items if i["choice"] == "yes"],
            "rejected_target_names": [i["name"] for i in target_items if i["choice"] == "no"],
            "owner_competitor_places": chosen_places,
            "name_links": links,
            "type_wording": dict(existing_decisions.get("type_wording") or {}),
            "evidence_waivers": {key: missing_layers[key] for key, accepted in waiver_choices.items() if accepted},
            "leader_count": int(leader_count),
            "recommendation_decisions": {cid: choice for cid, choice in recommendation_choices.items() if choice != "undecided"},
            "approved_recommendations": [
                {**candidate, "action": (recommendation_wording.get(candidate["id"]) or candidate["action"]).strip()[:380]}
                for candidate in evidence_candidates if recommendation_choices.get(candidate["id"]) == "include"
            ],
            "recommendation_basis": (
                {"layers": evidence_analysis["layers"], "leaders": evidence_analysis["leaders"], "basis": evidence_analysis["basis"]}
                if evidence_analysis is not None else {}
            ),
            "question_priority_map": {order: choice for order, choice in question_choices.items() if choice},
            "cohort_place_ids": selected_cohort,
            "headline": " ".join(headline.split()),
            "summary": " ".join(summary.split()),
            "action_titles": [line.strip(" \t-•") for line in action_titles.splitlines() if line.strip(" \t-•")],
            "review_quote_ids": selected_quotes,
            "review_notes": " ".join(review_notes.split()),
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
                complete=bool(complete_review) and names_ready,
            )
        except Exception as exc:
            st.error("The report review could not be saved.")
            st.exception(exc)
        else:
            st.session_state[f"review_note_{selected_place_id}"] = (
                f"Report review saved as revision {saved_review['revision']}."
                + (
                    " The name matches are saved, so the most visible businesses are now known. Collect their website pages and "
                    "reviews below, decide the recommendations, then complete the review."
                    if complete_review and not names_ready else ""
                )
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
elif configuration_ready and definition is None and review_update_reasons:
    st.warning(
        "**Generating is paused until the review in step 5 is updated.** It was completed before some checks existed. "
        "Please " + "; ".join(review_update_reasons) + ". This takes a minute and keeps the report accurate."
    )
else:
    with st.container(border=True):
        report_client_name = definition.client_name if definition else str(durable_audit["target_business_name"])
        report_run_id = definition.baseline_run_id if definition else saved_benchmark_run_id
        st.markdown(f"**Selected business:** {report_client_name}")
        st.caption(f"Saved AI Visibility run: {report_run_id}")
        report_kind = st.radio(
            "Report type",
            options=[item.key for item in REPORT_TYPES],
            format_func={item.key: item.label for item in REPORT_TYPES}.get,
            horizontal=True,
            key=f"report_kind_{selected_place_id}",
        )
        chosen_type = next(item for item in REPORT_TYPES if item.key == report_kind)
        st.caption(chosen_type.description)
        summary_is_draft = True
        if report_kind == "summary":
            summary_is_draft = st.checkbox(
                "Mark the summary as a draft",
                value=True,
                key=f"summary_draft_{selected_place_id}",
                help="Adds a small DRAFT label to each page header. Untick it once the report has been checked and signed off.",
            )
        generate = st.button(chosen_type.button, type="primary", use_container_width=True)

    summary_key = definition.key if definition else f"generic_{durable_audit['id']}"
    def generate_summary():
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

    def show_summary():
        saved_summary = st.session_state.get(SUMMARY_STATE_KEY)
        if saved_summary and saved_summary["key"] == summary_key:
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

    def generate_full():
        try:
            with st.spinner("Assembling the saved evidence and laying out the report…"):
                reviewable = (
                    build_reviewable_poc_audit(definition)
                    if definition is not None
                    else build_reviewable_generic_audit(
                        durable_audit, site_findings=site_findings_for(business, durable_audit)[1]
                    )
                )
        except (UndecidedTargetNamesError, UndecidedNamesError) as exc:
            st.warning(str(exc))
        except Exception as exc:
            st.error(
                "The report could not be generated from the configured evidence. "
                "AI Visibility was not rerun and no data was changed."
            )
            st.exception(exc)
        else:
            st.session_state[REPORT_STATE_KEY] = reviewable

    def show_full():
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

    generate_report, show_report = {"summary": (generate_summary, show_summary), "full": (generate_full, show_full)}[report_kind]
    if generate:
        generate_report()
    show_report()
