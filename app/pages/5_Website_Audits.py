from __future__ import annotations

import hashlib
import sys
import uuid
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import text


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from src.database import get_engine
from src.taxonomy import GROUP_LABELS
from src.website_audit import audit_website
from src.website_audit_repository import (
    create_audit_run,
    finish_audit_run,
    get_audit_pages,
    get_latest_audit,
    get_latest_audits,
    save_audit_page,
)


BUILD_VERSION = "Website Footprint Audit v1.1.3 / Latest Raw URL v1.0"


CRAWL_PRESETS = {
    "Quick — up to 5 pages": {
        "max_pages": 5,
        "minimum_reuse_pages": 3,
        "description": (
            "Fast check for the homepage and highest-"
            "priority commercial pages."
        ),
    },
    "Standard — adaptive, up to 20 pages": {
        "max_pages": 20,
        "minimum_reuse_pages": 8,
        "description": (
            "Recommended. Uses the sitemap and internal "
            "links to prioritise services, menus, pricing, "
            "FAQs, booking, team, events and contact pages."
        ),
    },
    "Deep — adaptive, up to 50 pages": {
        "max_pages": 50,
        "minimum_reuse_pages": 15,
        "description": (
            "For larger sites or final validation. May "
            "take several minutes across a cohort."
        ),
    },
}


st.set_page_config(
    page_title="Website Audits",
    page_icon="🌐",
    layout="wide",
)

st.title("Website Footprint Audits")
st.caption(
    "Audit the owned-web footprint of a target business "
    "and its validated competitor cohort."
)
st.caption(f"Build: {BUILD_VERSION}")


@st.cache_data(ttl=300)
def load_businesses() -> pd.DataFrame:
    engine = get_engine()

    query = text(
        """
        select
            bf.google_place_id,
            bf.business_name,
            bf.primary_group,
            bf.business_format,
            coalesce(
                nullif(
                    rol.raw_data->>'website',
                    ''
                ),
                nullif(
                    rol.raw_data->>'site',
                    ''
                )
            ) as website_url
        from business_features bf
        left join lateral (
            select
                raw_data
            from raw_outscraper_locations
            where google_place_id =
                  bf.google_place_id
            order by
                created_at desc,
                id desc
            limit 1
        ) rol on true
        order by bf.business_name
        """
    )

    with engine.connect() as connection:
        rows = connection.execute(
            query
        ).mappings().all()

    return pd.DataFrame(rows)


@st.cache_data(ttl=60)
def load_saved_cohort(
    target_google_place_id: str,
) -> pd.DataFrame:
    engine = get_engine()

    query = text(
        """
        select
            crr.candidate_google_place_id
                as google_place_id,
            crr.relationship_status,
            bf.business_name,
            bf.primary_group,
            bf.business_format,
            coalesce(
                nullif(
                    rol.raw_data->>'website',
                    ''
                ),
                nullif(
                    rol.raw_data->>'site',
                    ''
                )
            ) as website_url
        from competitor_relationship_reviews crr
        join business_features bf
          on bf.google_place_id =
             crr.candidate_google_place_id
        left join lateral (
            select
                raw_data
            from raw_outscraper_locations
            where google_place_id =
                  crr.candidate_google_place_id
            order by
                created_at desc,
                id desc
            limit 1
        ) rol on true
        where
            crr.target_google_place_id =
                :target_google_place_id
        order by
            crr.relationship_status,
            bf.business_name
        """
    )

    with engine.connect() as connection:
        rows = connection.execute(
            query,
            {
                "target_google_place_id":
                    target_google_place_id,
            },
        ).mappings().all()

    return pd.DataFrame(rows)


def yes_no(value: object) -> str:
    return "Yes" if bool(value) else "No"


def recent_enough(
    audit: dict,
    reuse_days: int,
    minimum_pages: int,
) -> bool:
    if not audit or reuse_days <= 0:
        return False

    try:
        pages_crawled = int(
            audit.get("pages_crawled")
            or 0
        )
    except (TypeError, ValueError):
        pages_crawled = 0

    if pages_crawled < minimum_pages:
        return False

    completed_at = audit.get("completed_at")

    if completed_at is None or pd.isna(completed_at):
        return False

    completed = pd.Timestamp(completed_at)

    if completed.tzinfo is None:
        completed = completed.tz_localize("UTC")
    else:
        completed = completed.tz_convert("UTC")

    cutoff = (
        pd.Timestamp.now(tz="UTC")
        - pd.Timedelta(days=reuse_days)
    )

    return completed >= cutoff


try:
    businesses = load_businesses()
except Exception as exc:
    st.error(
        "Business data could not be loaded."
    )
    st.exception(exc)
    st.stop()


if businesses.empty:
    st.warning(
        "No feature records are available."
    )
    st.stop()


active_diagnostic = (
    st.session_state.get(
        "active_diagnostic_cohort",
        {},
    )
)

active_ids = [
    str(place_id)
    for place_id in (
        active_diagnostic.get(
            "business_ids",
            [],
        )
        or []
    )
]

active_target_id = str(
    active_diagnostic.get(
        "target_google_place_id"
    )
    or ""
)

active_target_name = str(
    active_diagnostic.get(
        "target_business_name"
    )
    or ""
)

if active_ids:
    st.info(
        "Active diagnostic cohort: "
        f"**{active_target_name or 'Target'} + "
        f"{max(len(active_ids) - 1, 0)} AI leader(s)**. "
        "The audit scope has been preselected from "
        "AI Competitive Diagnostic."
    )

    st.page_link(
        "pages/9_AI_Competitive_Diagnostic.py",
        label="← Return to AI Competitive Diagnostic",
    )


available_groups = sorted(
    businesses["primary_group"]
    .dropna()
    .astype(str)
    .unique()
    .tolist(),
    key=lambda key: GROUP_LABELS.get(key, key),
)


st.sidebar.header("Audit target")

default_group_index = 0

if active_target_id:
    active_target_rows = businesses[
        businesses[
            "google_place_id"
        ].astype(str)
        == active_target_id
    ]

    if not active_target_rows.empty:
        active_group = str(
            active_target_rows.iloc[0][
                "primary_group"
            ]
            or ""
        )

        if active_group in available_groups:
            default_group_index = (
                available_groups.index(
                    active_group
                )
            )

selected_group = st.sidebar.selectbox(
    "Canonical group",
    options=available_groups,
    index=default_group_index,
    format_func=lambda value: GROUP_LABELS.get(
        value,
        value,
    ),
)

target_options = businesses[
    businesses["primary_group"]
    == selected_group
].copy()

target_options = target_options.sort_values(
    "business_name"
)

target_ids = (
    target_options["google_place_id"]
    .dropna()
    .drop_duplicates()
    .tolist()
)

target_name_lookup = (
    target_options
    .drop_duplicates("google_place_id")
    .set_index("google_place_id")[
        "business_name"
    ]
    .to_dict()
)

default_target_index = 0

target_id_strings = [
    str(place_id)
    for place_id in target_ids
]

if active_target_id in target_id_strings:
    default_target_index = (
        target_id_strings.index(
            active_target_id
        )
    )
else:
    for index, place_id in enumerate(target_ids):
        if (
            str(
                target_name_lookup.get(
                    place_id,
                    "",
                )
            ).lower()
            == "ciscos karma"
        ):
            default_target_index = index
            break

target_id = st.sidebar.selectbox(
    "Target business",
    options=target_ids,
    index=default_target_index,
    format_func=lambda value: (
        target_name_lookup.get(
            value,
            value,
        )
    ),
)

target_row = businesses[
    businesses["google_place_id"]
    == target_id
].iloc[0].to_dict()


try:
    saved_cohort = load_saved_cohort(
        target_id
    )
except Exception as exc:
    st.error(
        "The saved competitor cohort could not be "
        "loaded. Confirm the competitor review table exists."
    )
    st.exception(exc)
    st.stop()


st.sidebar.divider()
st.sidebar.header("Audit scope")

scope_options = [
    "Target only",
    "Target + direct competitors",
    "Target + direct and indirect",
    "Target + direct, indirect and possible",
    "Manual selection",
]

if active_ids:
    scope_options.insert(
        0,
        "Active diagnostic cohort",
    )

scope = st.sidebar.selectbox(
    "Businesses to audit",
    options=scope_options,
    index=0,
)

all_business_options = (
    businesses
    .drop_duplicates("google_place_id")
    .sort_values("business_name")
)

all_ids = all_business_options[
    "google_place_id"
].tolist()

all_name_lookup = (
    all_business_options
    .set_index("google_place_id")[
        "business_name"
    ]
    .to_dict()
)

manual_ids: list[str] = []

if scope == "Manual selection":
    manual_default = (
        [
            place_id
            for place_id in all_ids
            if str(place_id)
            in set(active_ids)
        ]
        if active_ids
        else [target_id]
    )

    manual_ids = st.sidebar.multiselect(
        "Select businesses",
        options=all_ids,
        default=manual_default,
        format_func=lambda value: (
            all_name_lookup.get(
                value,
                value,
            )
        ),
    )


selected_ids = [target_id]

if (
    scope
    == "Active diagnostic cohort"
):
    selected_ids = [
        place_id
        for place_id in all_ids
        if str(place_id)
        in set(active_ids)
    ]

if scope == "Target + direct competitors":
    statuses = {"direct"}
elif scope == "Target + direct and indirect":
    statuses = {
        "direct",
        "indirect",
    }
elif (
    scope
    == "Target + direct, indirect and possible"
):
    statuses = {
        "direct",
        "indirect",
        "possible",
    }
else:
    statuses = set()

if statuses and not saved_cohort.empty:
    selected_ids.extend(
        saved_cohort[
            saved_cohort[
                "relationship_status"
            ].isin(statuses)
        ]["google_place_id"].tolist()
    )

if scope == "Manual selection":
    selected_ids = manual_ids

selected_ids = list(
    dict.fromkeys(selected_ids)
)

selected_businesses = businesses[
    businesses["google_place_id"]
    .isin(selected_ids)
].copy()

selected_businesses = selected_businesses.sort_values(
    "business_name"
)


st.sidebar.caption(
    f"{len(selected_businesses)} businesses selected"
)

reuse_days = st.sidebar.slider(
    "Reuse audits completed within",
    min_value=0,
    max_value=30,
    value=7,
    step=1,
    format="%d days",
    help=(
        "Set to 0 to always run a fresh audit."
    ),
)

crawl_preset_name = st.sidebar.selectbox(
    "Crawl depth",
    options=list(CRAWL_PRESETS),
    index=1,
)

crawl_preset = CRAWL_PRESETS[
    crawl_preset_name
]

max_pages = int(
    crawl_preset["max_pages"]
)

minimum_reuse_pages = int(
    crawl_preset[
        "minimum_reuse_pages"
    ]
)

st.sidebar.caption(
    crawl_preset["description"]
)

adaptive_stop = st.sidebar.checkbox(
    "Stop early when priority coverage is complete",
    value=True,
    help=(
        "After enough pages have been sampled, the "
        "crawler may stop before the cap when it has "
        "covered most high-value page categories and "
        "no high-priority URLs remain."
    ),
)

timeout_seconds = st.sidebar.slider(
    "Request timeout",
    min_value=5,
    max_value=20,
    value=10,
    step=1,
)


st.subheader("Selected audit cohort")

st.caption(
    f"Crawl plan: {crawl_preset_name}. "
    f"Maximum {max_pages} pages per website"
    + (
        ", with adaptive early stopping."
        if adaptive_stop
        else "."
    )
)

cohort_display = selected_businesses[
    [
        "business_name",
        "business_format",
        "website_url",
    ]
].copy()

cohort_display.columns = [
    "Business",
    "Format",
    "Website",
]

st.dataframe(
    cohort_display,
    use_container_width=True,
    hide_index=True,
)


missing_websites = selected_businesses[
    selected_businesses["website_url"]
    .fillna("")
    .astype(str)
    .str.strip()
    .eq("")
]

if not missing_websites.empty:
    st.warning(
        f"{len(missing_websites)} selected business(es) "
        "do not have a website URL in the source data."
    )


run_button_label = (
    "Run website audits for active diagnostic cohort"
    if (
        scope
        == "Active diagnostic cohort"
    )
    else "Run website audits"
)

run_audits = st.button(
    run_button_label,
    type="primary",
    disabled=selected_businesses.empty,
)


if run_audits:
    audit_batch_id = str(uuid.uuid4())
    progress = st.progress(0)
    status_box = st.empty()

    completed = 0
    reused = 0
    failed = 0

    rows = selected_businesses.to_dict(
        "records"
    )

    for index, business in enumerate(rows):
        business_name = str(
            business.get("business_name")
            or "Unknown business"
        )

        status_box.write(
            f"Auditing **{business_name}**..."
        )

        existing = get_latest_audit(
            str(
                business.get(
                    "google_place_id"
                )
            )
        )

        if recent_enough(
            existing,
            reuse_days,
            minimum_reuse_pages,
        ):
            reused += 1
            progress.progress(
                (index + 1) / len(rows)
            )
            continue

        run_id = create_audit_run(
            audit_batch_id=audit_batch_id,
            google_place_id=str(
                business.get(
                    "google_place_id"
                )
            ),
            business_name=business_name,
            requested_url=business.get(
                "website_url"
            ),
        )

        website_url = str(
            business.get("website_url")
            or ""
        ).strip()

        if not website_url:
            finish_audit_run(
                audit_run_id=run_id,
                result={
                    "audit_status":
                        "no_website",
                    "issues": [
                        "No website URL in source data"
                    ],
                    "website_completeness_score":
                        0,
                    "error_message":
                        "No website URL in source data",
                },
            )
            failed += 1
            progress.progress(
                (index + 1) / len(rows)
            )
            continue

        try:
            result, pages = audit_website(
                website_url=website_url,
                business_group=str(
                    business.get(
                        "primary_group"
                    )
                    or "generic"
                ),
                max_pages=max_pages,
                timeout_seconds=(
                    timeout_seconds
                ),
                adaptive_stop=(
                    adaptive_stop
                ),
            )

            for page in pages:
                save_audit_page(
                    audit_run_id=run_id,
                    page=page,
                )

            finish_audit_run(
                audit_run_id=run_id,
                result=result,
            )

            if result.get(
                "audit_status"
            ) in {
                "completed",
                "partial",
            }:
                completed += 1
            else:
                failed += 1

        except Exception as exc:
            finish_audit_run(
                audit_run_id=run_id,
                result={
                    "audit_status": "failed",
                    "issues": [str(exc)],
                    "website_completeness_score":
                        0,
                    "error_message": str(exc),
                },
            )
            failed += 1

        progress.progress(
            (index + 1) / len(rows)
        )

    status_box.empty()

    st.success(
        f"Audit complete: {completed} freshly audited, "
        f"{reused} recent audits reused, "
        f"{failed} unavailable or failed."
    )

    st.cache_data.clear()
    st.rerun()


st.divider()
st.subheader("Latest audit comparison")


try:
    latest = get_latest_audits(
        selected_ids
    )
except Exception as exc:
    st.info(
        "No website-audit table is available yet. "
        "Run the supplied SQL migration first."
    )
    st.exception(exc)
    st.stop()


if latest.empty:
    st.info(
        "No audits have been run for the selected "
        "businesses yet."
    )
    st.stop()


comparison = latest.copy()

comparison["Score"] = comparison[
    "website_completeness_score"
]

comparison["Status"] = comparison[
    "audit_status"
]

comparison["HTTPS"] = comparison[
    "is_https"
].apply(yes_no)

comparison["Local schema"] = comparison[
    "has_local_business_schema"
].apply(yes_no)

comparison["Services"] = comparison[
    "has_service_pages"
].apply(yes_no)

comparison["Pricing"] = comparison[
    "has_pricing_page"
].apply(yes_no)

comparison["FAQ"] = comparison[
    "has_faq_content"
].apply(yes_no)

comparison["Booking"] = comparison[
    "has_booking_link"
].apply(yes_no)

comparison["Social links"] = comparison[
    "has_social_links"
].apply(yes_no)

comparison_columns = [
    "business_name",
    "Score",
    "Status",
    "pages_crawled",
    "HTTPS",
    "Local schema",
    "Services",
    "Pricing",
    "FAQ",
    "Booking",
    "Social links",
    "completed_at",
]

comparison_display = comparison[
    comparison_columns
].rename(
    columns={
        "business_name": "Business",
        "pages_crawled": "Pages crawled",
        "completed_at": "Audited",
    }
)

st.dataframe(
    comparison_display,
    use_container_width=True,
    hide_index=True,
)


st.divider()
st.subheader("Inspect an audit")

# Normalise database UUIDs to strings. A fresh crawl creates new audit
# IDs, so the selectbox key also changes when the latest-audit set changes.
# This prevents Streamlit from retaining a stale selection from the
# previous comparison table.
comparison = comparison.copy()
comparison["audit_id_string"] = (
    comparison["id"]
    .astype(str)
)

audit_ids = comparison[
    "audit_id_string"
].tolist()

audit_name_lookup = (
    comparison
    .set_index(
        "audit_id_string"
    )["business_name"]
    .to_dict()
)

audit_selection_signature = (
    hashlib.sha1(
        "|".join(
            audit_ids
        ).encode("utf-8")
    )
    .hexdigest()[:12]
)

selected_audit_id = st.selectbox(
    "Business audit",
    options=audit_ids,
    format_func=lambda value: (
        audit_name_lookup.get(
            value,
            value,
        )
    ),
    key=(
        "website_audit_inspector_"
        f"{audit_selection_signature}"
    ),
)

selected_rows = comparison[
    comparison[
        "audit_id_string"
    ]
    == str(selected_audit_id)
]

# Defensive fallback: even if widget/session state becomes stale during a
# rerun, always display a current audit rather than raising IndexError.
if selected_rows.empty:
    selected_audit = (
        comparison.iloc[0]
    )
    selected_audit_id = str(
        selected_audit[
            "audit_id_string"
        ]
    )
else:
    selected_audit = (
        selected_rows.iloc[0]
    )


metric_columns = st.columns(5)

with metric_columns[0]:
    st.metric(
        "Website completeness",
        (
            f"{selected_audit['Score']}/100"
            if pd.notna(
                selected_audit["Score"]
            )
            else "—"
        ),
    )

with metric_columns[1]:
    st.metric(
        "Status",
        selected_audit["Status"],
    )

with metric_columns[2]:
    st.metric(
        "Pages crawled",
        selected_audit[
            "pages_crawled"
        ],
    )

with metric_columns[3]:
    st.metric(
        "Schema types",
        len(
            selected_audit[
                "schema_types"
            ]
            or []
        ),
    )

with metric_columns[4]:
    st.metric(
        "Issues",
        len(
            selected_audit["issues"]
            or []
        ),
    )


st.write("### Evidence")

evidence = {
    "HTTPS": selected_audit["is_https"],
    "Homepage title": selected_audit[
        "has_title"
    ],
    "Meta description": selected_audit[
        "has_meta_description"
    ],
    "Canonical URL": selected_audit[
        "has_canonical"
    ],
    "Local business schema": selected_audit[
        "has_local_business_schema"
    ],
    "Contact signals": selected_audit[
        "has_contact_signals"
    ],
    "Address signals": selected_audit[
        "has_address_signals"
    ],
    "Service coverage": selected_audit[
        "has_service_pages"
    ],
    "Menu page": selected_audit[
        "has_menu_page"
    ],
    "Pricing page": selected_audit[
        "has_pricing_page"
    ],
    "FAQ content": selected_audit[
        "has_faq_content"
    ],
    "Booking link": selected_audit[
        "has_booking_link"
    ],
    "Social links": selected_audit[
        "has_social_links"
    ],
}

evidence_frame = pd.DataFrame(
    [
        {
            "Check": label,
            "Found": yes_no(value),
        }
        for label, value in evidence.items()
    ]
)

st.dataframe(
    evidence_frame,
    use_container_width=True,
    hide_index=True,
)


issues = selected_audit["issues"] or []

if issues:
    st.write("### Issues")

    for issue in issues:
        st.write(f"- {issue}")


pages = get_audit_pages(
    str(
        selected_audit[
            "audit_id_string"
        ]
    )
)

if not pages.empty:
    with st.expander(
        "View crawled pages"
    ):
        page_display = pages[
            [
                "final_url",
                "http_status",
                "page_title",
                "meta_description",
                "schema_types",
                "issues",
            ]
        ].rename(
            columns={
                "final_url": "URL",
                "http_status": "HTTP",
                "page_title": "Title",
                "meta_description":
                    "Meta description",
                "schema_types": "Schema",
                "issues": "Issues",
            }
        )

        st.dataframe(
            page_display,
            use_container_width=True,
            hide_index=True,
        )


final_url = selected_audit.get(
    "final_url"
)

if final_url:
    st.link_button(
        "Open audited website",
        str(final_url),
    )


st.info(
    "This is a website-footprint completeness score, "
    "not yet a full AI-discoverability score. "
    "The adaptive crawler prioritises commercially "
    "useful pages rather than simply following the "
    "first links it encounters."
)
