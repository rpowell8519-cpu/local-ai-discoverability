from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import text


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from src.ai_competitive_diagnostic import (
    build_combined_observations,
    build_proposition_benchmark,
    build_proposition_coverage,
    jsonish,
)
from src.ai_discovery_repository import (
    get_discovery_run,
    list_discovery_runs,
)
from src.ai_enrichment_repository import (
    load_entity_aliases,
)
from src.ai_recommendation_intelligence import (
    build_business_share_table,
    build_recommendation_records,
)
from src.ai_visibility_analysis import (
    reanalyse_results,
)
from src.ai_visibility_repository import (
    get_run_results,
)
from src.database import get_engine
from src.review_analysis import (
    build_review_benchmark,
)
from src.review_profiles import (
    get_review_profile,
)
from src.review_repository import (
    get_reviews,
)
from src.vertical_audit_profiles import (
    get_audit_profile,
)
from src.website_audit_repository import (
    get_audit_pages,
    get_latest_audits,
)
from src.website_benchmark import (
    build_website_benchmark,
)


BUILD_VERSION = "AI Competitive Diagnostic v1.1.1"


st.set_page_config(
    page_title="AI Competitive Diagnostic",
    page_icon="🧭",
    layout="wide",
)

st.title("AI Competitive Diagnostic")
st.caption(
    "Compare the target with the businesses AI recommends "
    "most often and identify observable website and customer-"
    "review differences that may help explain the gap."
)
st.caption(f"Build: {BUILD_VERSION}")

st.info(
    "Select the businesses AI currently favours, complete the "
    "required evidence, then compare the target's website and "
    "customer-review signals with those AI leaders."
)

with st.expander(
    "How to interpret this diagnostic"
):
    st.write(
        "The diagnostic surfaces **observable differences**, "
        "not proven AI ranking factors. Its purpose is to "
        "identify credible, client-controllable opportunities "
        "that distinguish businesses currently winning AI "
        "recommendations."
    )

    st.write(
        "No new AI calls are made on this page. It reuses "
        "stored AI Discovery, Website Audit and Review "
        "Intelligence evidence."
    )


@st.cache_data(ttl=300)
def load_business_directory() -> pd.DataFrame:
    engine = get_engine()

    query = text(
        """
        select
            google_place_id,
            business_name,
            primary_group,
            business_format
        from business_features
        order by business_name
        """
    )

    with engine.connect() as connection:
        rows = connection.execute(
            query
        ).mappings().all()

    return pd.DataFrame(rows)


try:
    businesses = load_business_directory()
    aliases = load_entity_aliases()
except Exception as exc:
    st.error(
        "Business/entity data could not be loaded."
    )
    st.exception(exc)
    st.stop()


try:
    discovery_runs = list_discovery_runs(
        limit=50
    )
except Exception as exc:
    st.error(
        "AI Discovery Scan runs could not be loaded."
    )
    st.exception(exc)
    st.stop()


if discovery_runs.empty:
    st.info(
        "Run an AI Discovery Scan first. This diagnostic "
        "uses that scan to decide which AI competitors "
        "should be compared."
    )
    st.page_link(
        "pages/0_AI_Discovery_Scan.py",
        label="Open AI Discovery Scan",
    )
    st.stop()


# =========================================================
# 1. SELECT AI SCAN
# =========================================================

st.subheader("1. Select the AI market")

discovery_runs[
    "id"
] = discovery_runs[
    "id"
].astype(str)

run_lookup = {
    str(
        row["id"]
    ): (
        f"{row['target_business_name']} — "
        f"{row['location_context']} — "
        f"{row['started_at']}"
    )
    for row in discovery_runs.to_dict(
        "records"
    )
}

run_ids = (
    discovery_runs[
        "id"
    ].tolist()
)

selected_run_id = st.selectbox(
    "AI Discovery Scan",
    options=run_ids,
    index=0,
    format_func=lambda value: (
        run_lookup.get(
            value,
            value,
        )
    ),
)

run = get_discovery_run(
    selected_run_id
)

if not run:
    st.error(
        "The selected scan could not be loaded."
    )
    st.stop()


target_id = str(
    run[
        "target_google_place_id"
    ]
)

target_name = str(
    run[
        "target_business_name"
    ]
)

st.success(
    f"**Target business: {target_name}**"
)

st.caption(
    "All evidence and competitor comparisons on this page are "
    f"being built around **{target_name}** as the client/target."
)

primary_group = str(
    run.get(
        "primary_group"
    )
    or ""
)

if target_id.startswith(
    "discovery:"
):
    st.warning(
        "This target was scanned before being imported into "
        "the structured business dataset. To compare website "
        "and review evidence, enrich/import the target first."
    )

    st.page_link(
        "pages/0_AI_Discovery_Scan.py",
        label="Return to AI Discovery Scan",
    )
    st.stop()


target_matches = businesses[
    businesses[
        "google_place_id"
    ].astype(str)
    == target_id
]

if target_matches.empty:
    st.warning(
        "The target's Google Place entity is not currently "
        "available in business_features. Rebuild/enrich the "
        "business data before running this diagnostic."
    )
    st.stop()


# =========================================================
# 2. BUILD AI MARKET + SELECT LEADERS
# =========================================================

results = get_run_results(
    selected_run_id
)

if results.empty:
    st.warning(
        "The selected AI Discovery Scan has no stored results."
    )
    st.stop()


results = reanalyse_results(
    results,
    target_google_place_id=(
        target_id
    ),
    target_business_name=(
        target_name
    ),
    known_businesses=[
        {
            "google_place_id":
                target_id,
            "business_name":
                target_name,
        }
    ],
)

recommendations = (
    build_recommendation_records(
        results=results,
        businesses=businesses,
        aliases=aliases,
        target_google_place_id=(
            target_id
        ),
        commercial_competitor_ids=set(),
        primary_group=(
            primary_group
        ),
    )
)

market = build_business_share_table(
    recommendations
)

if market.empty:
    st.warning(
        "No numbered AI recommendation market could be extracted."
    )
    st.stop()


resolved_candidates = market[
    (
        market[
            "classification"
        ]
        == "AI-discovered"
    )
    & (
        market[
            "google_place_id"
        ].notna()
    )
].copy()

if resolved_candidates.empty:
    st.warning(
        "No AI-discovered businesses were confidently resolved "
        "to physical business entities. Resolve/enrich the AI "
        "market before building a comparative diagnostic."
    )
    st.stop()


resolved_candidates[
    "google_place_id"
] = resolved_candidates[
    "google_place_id"
].astype(str)

candidate_name_lookup = {
    str(
        row[
            "google_place_id"
        ]
    ): str(
        row[
            "business_name"
        ]
    )
    for row in resolved_candidates.to_dict(
        "records"
    )
}

candidate_detail_lookup = {
    str(
        row[
            "google_place_id"
        ]
    ): row
    for row in resolved_candidates.to_dict(
        "records"
    )
}

candidate_ids = (
    resolved_candidates[
        "google_place_id"
    ].tolist()
)

default_ids = (
    resolved_candidates
    .head(
        min(
            3,
            len(
                resolved_candidates
            ),
        )
    )[
        "google_place_id"
    ]
    .tolist()
)


st.write("### AI leaders to compare")

st.caption(
    "The diagnostic compares **physical business entities**. "
    "Brand-only or ambiguous recommendations — important for "
    "multi-location businesses such as Small Batch, Flour Pot "
    "or GAIL's — are deliberately not forced onto a particular "
    "branch."
)

selected_ids = st.multiselect(
    "Select 1–5 AI-recommended businesses",
    options=candidate_ids,
    default=default_ids,
    max_selections=5,
    format_func=lambda value: (
        candidate_name_lookup.get(
            value,
            value,
        )
        + (
            f" — "
            f"{float(candidate_detail_lookup[value]['share_of_recommendation']):.1%} share"
            if value
            in candidate_detail_lookup
            else ""
        )
    ),
)

if not selected_ids:
    st.info(
        "Select at least one resolved AI leader."
    )
    st.stop()


active_business_ids = [
    str(target_id),
    *[
        str(place_id)
        for place_id in selected_ids
    ],
]

active_business_names = {
    str(target_id):
        target_name,
    **{
        str(place_id):
            candidate_name_lookup.get(
                str(place_id),
                str(place_id),
            )
        for place_id in selected_ids
    },
}

st.session_state[
    "active_diagnostic_cohort"
] = {
    "source":
        "ai_competitive_diagnostic",
    "discovery_run_id":
        str(selected_run_id),
    "target_google_place_id":
        str(target_id),
    "target_business_name":
        target_name,
    "primary_group":
        primary_group,
    "location_context":
        str(
            run.get(
                "location_context"
            )
            or ""
        ),
    "business_ids":
        active_business_ids,
    "business_names":
        active_business_names,
}

st.caption(
    "Active diagnostic cohort: "
    f"**{target_name} + {len(selected_ids)} AI leader(s)**. "
    "This selection will follow you to Website Audits and "
    "Review Insights in this browser session."
)


leader_market = resolved_candidates[
    resolved_candidates[
        "google_place_id"
    ].isin(
        selected_ids
    )
].copy()

leader_market[
    "Share of Recommendation"
] = leader_market[
    "share_of_recommendation"
].apply(
    lambda value: (
        f"{float(value):.1%}"
    )
)

leader_market[
    "Weighted share"
] = leader_market[
    "position_weighted_share"
].apply(
    lambda value: (
        f"{float(value):.1%}"
    )
)

leader_market[
    "Avg position"
] = leader_market[
    "average_position"
].apply(
    lambda value: (
        f"{float(value):.2f}"
    )
)

st.dataframe(
    leader_market[
        [
            "business_name",
            "recommendations",
            "Share of Recommendation",
            "Weighted share",
            "Avg position",
            "providers",
        ]
    ].rename(
        columns={
            "business_name":
                "AI leader",
            "recommendations":
                "Recommendations",
            "providers":
                "Providers",
        }
    ),
    use_container_width=True,
    hide_index=True,
)


# =========================================================
# 3. DATA READINESS
# =========================================================

st.divider()
st.subheader("2. Complete the evidence")

comparison_ids = [
    target_id,
    *selected_ids,
]

business_name_lookup = {
    str(
        row[
            "google_place_id"
        ]
    ): str(
        row[
            "business_name"
        ]
    )
    for row in businesses[
        businesses[
            "google_place_id"
        ].astype(str)
        .isin(
            comparison_ids
        )
    ].to_dict(
        "records"
    )
}

try:
    audits = get_latest_audits(
        comparison_ids
    )
except Exception as exc:
    st.error(
        "Website audit data could not be loaded."
    )
    st.exception(exc)
    st.stop()


try:
    reviews = get_reviews(
        comparison_ids
    )
except Exception as exc:
    st.error(
        "Review data could not be loaded."
    )
    st.exception(exc)
    st.stop()


audit_lookup = {}

if not audits.empty:
    audits[
        "google_place_id"
    ] = audits[
        "google_place_id"
    ].astype(str)

    audit_lookup = {
        str(
            row[
                "google_place_id"
            ]
        ): row
        for row in audits.to_dict(
            "records"
        )
    }


review_counts = {}

if not reviews.empty:
    reviews[
        "google_place_id"
    ] = reviews[
        "google_place_id"
    ].astype(str)

    review_counts = (
        reviews.groupby(
            "google_place_id"
        ).size().to_dict()
    )


readiness_rows = []

for place_id in comparison_ids:
    audit = audit_lookup.get(
        str(
            place_id
        ),
        {},
    )

    readiness_rows.append(
        {
            "google_place_id":
                str(
                    place_id
                ),
            "business_name":
                business_name_lookup.get(
                    str(
                        place_id
                    ),
                    (
                        target_name
                        if str(
                            place_id
                        )
                        == target_id
                        else str(
                            place_id
                        )
                    ),
                ),
            "role":
                (
                    "Target"
                    if str(
                        place_id
                    )
                    == target_id
                    else "AI leader"
                ),
            "website_audit":
                (
                    "Yes"
                    if audit
                    else "No"
                ),
            "audit_status":
                (
                    audit.get(
                        "audit_status"
                    )
                    if audit
                    else None
                ),
            "pages_crawled":
                (
                    audit.get(
                        "pages_crawled"
                    )
                    if audit
                    else None
                ),
            "website_score":
                (
                    audit.get(
                        "website_completeness_score"
                    )
                    if audit
                    else None
                ),
            "reviews":
                int(
                    review_counts.get(
                        str(
                            place_id
                        ),
                        0,
                    )
                ),
        }
    )


readiness = pd.DataFrame(
    readiness_rows
)

readiness_display = readiness.copy()

readiness_display[
    "Website"
] = readiness_display[
    "website_audit"
].apply(
    lambda value: (
        "✓ Ready"
        if value == "Yes"
        else "○ Missing"
    )
)

readiness_display[
    "Reviews"
] = readiness_display[
    "reviews"
].apply(
    lambda value: (
        f"✓ {int(value)} stored"
        if int(value) > 0
        else "○ Missing"
    )
)

website_ready_count = int(
    (
        readiness[
            "website_audit"
        ]
        == "Yes"
    ).sum()
)

review_ready_count = int(
    (
        readiness[
            "reviews"
        ]
        > 0
    ).sum()
)

business_count = len(
    readiness
)

evidence_tasks_complete = (
    website_ready_count
    + review_ready_count
)

evidence_tasks_total = (
    business_count
    * 2
)

progress_columns = st.columns(3)

with progress_columns[0]:
    st.metric(
        "Website audits",
        f"{website_ready_count} / {business_count}",
    )

with progress_columns[1]:
    st.metric(
        "Review samples",
        f"{review_ready_count} / {business_count}",
    )

with progress_columns[2]:
    st.metric(
        "Evidence tasks complete",
        f"{evidence_tasks_complete} / {evidence_tasks_total}",
    )

st.dataframe(
    readiness_display[
        [
            "role",
            "business_name",
            "google_place_id",
            "Website",
            "pages_crawled",
            "website_score",
            "Reviews",
        ]
    ].rename(
        columns={
            "role":
                "Role",
            "business_name":
                "Business",
            "google_place_id":
                "Place ID",
            "pages_crawled":
                "Pages crawled",
            "website_score":
                "Website score",
        }
    ),
    use_container_width=True,
    hide_index=True,
)

missing_website = readiness[
    readiness[
        "website_audit"
    ]
    == "No"
]

missing_reviews = readiness[
    readiness[
        "reviews"
    ]
    == 0
]

evidence_complete = (
    missing_website.empty
    and missing_reviews.empty
)

if evidence_complete:
    st.success(
        "Evidence complete. The target and all selected AI "
        "leaders have website and review evidence, so the "
        "diagnostic below is ready to interpret."
    )
else:
    st.warning(
        "Complete the outstanding evidence tasks below. "
        "Your selected cohort is already active, so you "
        "will not need to find or select these businesses "
        "again on the linked pages."
    )

    action_columns = st.columns(2)

    with action_columns[0]:
        st.write(
            "#### Step A — Website evidence"
        )

        if missing_website.empty:
            st.success(
                "All selected websites have been audited."
            )
        else:
            missing_website_names = (
                missing_website[
                    "business_name"
                ]
                .astype(str)
                .tolist()
            )

            st.write(
                f"**{len(missing_website_names)} website "
                "audit(s) missing:** "
                + ", ".join(
                    missing_website_names
                )
            )

            st.page_link(
                "pages/5_Website_Audits.py",
                label="Run missing website audits →",
                use_container_width=True,
            )

    with action_columns[1]:
        st.write(
            "#### Step B — Customer-review evidence"
        )

        st.caption(
            f"Review collection is for **{target_name} (Target)** "
            "and the selected AI leaders. Use the **Place ID** "
            "shown below when locating each business in Outscraper."
        )

        if missing_reviews.empty:
            st.success(
                "All selected businesses have imported reviews."
            )
        else:
            missing_review_names = (
                missing_reviews[
                    "business_name"
                ]
                .astype(str)
                .tolist()
            )

            st.write(
                f"**{len(missing_review_names)} review "
                "sample(s) missing:** "
                + ", ".join(
                    missing_review_names
                )
            )

            collection_frame = (
                missing_reviews[
                    [
                        "role",
                        "business_name",
                        "google_place_id",
                    ]
                ]
                .copy()
            )

            collection_frame[
                "recommended_reviews"
            ] = 100

            collection_frame[
                "location"
            ] = str(
                run.get(
                    "location_context"
                )
                or ""
            )

            st.dataframe(
                collection_frame[
                    [
                        "role",
                        "business_name",
                        "google_place_id",
                        "location",
                        "recommended_reviews",
                    ]
                ].rename(
                    columns={
                        "role": "Role",
                        "business_name": "Business",
                        "google_place_id": "Place ID",
                        "location": "Location",
                        "recommended_reviews": "Reviews to collect",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )

            st.download_button(
                "Download Outscraper collection list",
                data=(
                    collection_frame[
                        [
                            "role",
                            "business_name",
                            "google_place_id",
                            "location",
                            "recommended_reviews",
                        ]
                    ].rename(
                        columns={
                            "role": "Role",
                            "business_name": "Business",
                            "google_place_id": "Place ID",
                            "location": "Location",
                            "recommended_reviews": "Recommended reviews",
                        }
                    )
                    .to_csv(
                        index=False
                    )
                    .encode(
                        "utf-8"
                    )
                ),
                file_name=(
                    "diagnostic_review_collection.csv"
                ),
                mime="text/csv",
                use_container_width=True,
            )

            st.page_link(
                "pages/7_Review_Insights.py",
                label="Import review export →",
                use_container_width=True,
            )




# =========================================================
# 4. WEBSITE DIFFERENCES
# =========================================================

st.divider()
st.subheader("3. Website diagnostic")

website_result = None
pages_by_place = {}

usable_audits = audits.copy()

if not usable_audits.empty:
    pages_by_run = {}

    for row in (
        usable_audits.to_dict(
            "records"
        )
    ):
        run_id = str(
            row.get(
                "id"
            )
            or ""
        )

        place_id = str(
            row.get(
                "google_place_id"
            )
            or ""
        )

        if not run_id:
            continue

        try:
            pages = get_audit_pages(
                run_id
            )
        except Exception:
            pages = pd.DataFrame()

        pages_by_run[
            run_id
        ] = pages

        pages_by_place[
            place_id
        ] = pages

    audit_profile = (
        get_audit_profile(
            primary_group
        )
    )

    website_result = (
        build_website_benchmark(
            target_google_place_id=(
                target_id
            ),
            audits=(
                usable_audits
            ),
            pages_by_run=(
                pages_by_run
            ),
            profile=(
                audit_profile
            ),
        )
    )


if (
    not website_result
    or website_result.get(
        "error"
    )
):
    st.info(
        (
            website_result.get(
                "error"
            )
            if website_result
            else (
                "Website comparison is not yet available."
            )
        )
    )
else:
    metric_columns = st.columns(4)

    with metric_columns[0]:
        target_score = (
            website_result.get(
                "target_score"
            )
        )
        st.metric(
            "Target website score",
            (
                f"{float(target_score):.0f}/100"
                if target_score
                is not None
                else "—"
            ),
        )

    with metric_columns[1]:
        median = website_result.get(
            "cohort_median"
        )
        st.metric(
            "AI-leader median",
            (
                f"{float(median):.0f}/100"
                if median
                is not None
                else "—"
            ),
        )

    with metric_columns[2]:
        rank = website_result.get(
            "target_rank"
        )
        denominator = website_result.get(
            "rank_denominator"
        )
        st.metric(
            "Target rank",
            (
                f"{rank} of {denominator}"
                if (
                    rank is not None
                    and denominator
                )
                else "—"
            ),
        )

    with metric_columns[3]:
        st.metric(
            "AI leaders audited",
            int(
                website_result.get(
                    "audited_competitors",
                    0,
                )
            ),
        )

    feature_benchmark = (
        website_result.get(
            "feature_benchmark",
            pd.DataFrame(),
        )
    )

    if not feature_benchmark.empty:
        feature_display = (
            feature_benchmark.copy()
        )

        feature_display[
            "AI-leader prevalence"
        ] = feature_display[
            "cohort_prevalence"
        ].apply(
            lambda value: (
                f"{float(value):.0%}"
                if pd.notna(
                    value
                )
                else "—"
            )
        )

        feature_display[
            "Target"
        ] = feature_display[
            "target_found"
        ].apply(
            lambda value: (
                "✓"
                if value is True
                else (
                    "—"
                    if value is False
                    else "n/a"
                )
            )
        )

        st.write(
            "### Website feature benchmark"
        )

        st.dataframe(
            feature_display[
                [
                    "category",
                    "check",
                    "Target",
                    "AI-leader prevalence",
                    "position",
                ]
            ].rename(
                columns={
                    "category":
                        "Area",
                    "check":
                        "Signal",
                    "position":
                        "Position",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )


# Proposition / customer-need coverage
propositions = [
    str(
        item
    ).strip()
    for item in jsonish(
        run.get(
            "target_propositions"
        ),
        [],
    )
    if str(
        item
    ).strip()
]

proposition_benchmark = (
    pd.DataFrame()
)

if propositions:
    st.write(
        "### Client-proposition website coverage"
    )

    st.caption(
        "This checks whether the target and selected AI-leader "
        "sites contain crawlable language related to the "
        "client propositions entered in the Discovery Scan. "
        "It is a content-coverage signal, not a quality score."
    )

    proposition_coverage = (
        build_proposition_coverage(
            propositions=(
                propositions
            ),
            pages_by_place=(
                pages_by_place
            ),
            business_names=(
                business_name_lookup
            ),
        )
    )

    proposition_benchmark = (
        build_proposition_benchmark(
            coverage=(
                proposition_coverage
            ),
            target_google_place_id=(
                target_id
            ),
        )
    )

    proposition_display = (
        proposition_benchmark.copy()
    )

    if not proposition_display.empty:
        proposition_display[
            "AI-leader prevalence"
        ] = proposition_display[
            "leader_prevalence"
        ].apply(
            lambda value: (
                f"{float(value):.0%}"
                if pd.notna(
                    value
                )
                else "—"
            )
        )

        st.dataframe(
            proposition_display[
                [
                    "proposition",
                    "target_pages",
                    "leaders_with_coverage",
                    "leader_count",
                    "AI-leader prevalence",
                    "leader_median_pages",
                    "position",
                ]
            ].rename(
                columns={
                    "proposition":
                        "Client proposition",
                    "target_pages":
                        "Target pages",
                    "leaders_with_coverage":
                        "AI leaders with coverage",
                    "leader_count":
                        "AI leaders compared",
                    "leader_median_pages":
                        "Leader median pages",
                    "position":
                        "Position",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )


# =========================================================
# 5. REVIEW DIFFERENCES
# =========================================================

st.divider()
st.subheader("4. Customer evidence")

review_result = None

target_review_count = int(
    review_counts.get(
        target_id,
        0,
    )
)

leader_review_count = sum(
    int(
        review_counts.get(
            str(
                place_id
            ),
            0,
        )
    )
    for place_id in (
        selected_ids
    )
)

if (
    target_review_count == 0
    or leader_review_count == 0
):
    st.info(
        "A review benchmark needs review data for the target "
        "and at least one selected AI leader."
    )
else:
    review_profile = (
        get_review_profile(
            primary_group
        )
    )

    review_result = (
        build_review_benchmark(
            target_google_place_id=(
                target_id
            ),
            reviews=reviews,
            business_names=(
                business_name_lookup
            ),
            profile=(
                review_profile
            ),
        )
    )

    summaries = review_result.get(
        "business_summaries",
        pd.DataFrame(),
    )

    if not summaries.empty:
        st.write(
            "### Review sample"
        )

        summary_display = (
            summaries.copy()
        )

        summary_display[
            "Sample rating"
        ] = summary_display[
            "sample_rating"
        ].apply(
            lambda value: (
                f"{float(value):.2f}"
                if pd.notna(
                    value
                )
                else "—"
            )
        )

        st.dataframe(
            summary_display[
                [
                    "business_name",
                    "reviews_analysed",
                    "Sample rating",
                    "negative_reviews",
                    "owner_responses",
                ]
            ].rename(
                columns={
                    "business_name":
                        "Business",
                    "reviews_analysed":
                        "Reviews analysed",
                    "negative_reviews":
                        "1–2 star reviews",
                    "owner_responses":
                        "Owner responses",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

    review_benchmark = (
        review_result.get(
            "benchmark",
            pd.DataFrame(),
        )
    )

    if not review_benchmark.empty:
        review_display = (
            review_benchmark.copy()
        )

        review_display[
            "Target association"
        ] = review_display[
            "target_pct"
        ].apply(
            lambda value: (
                f"{float(value):.0%}"
            )
        )

        review_display[
            "AI-leader median"
        ] = review_display[
            "cohort_median_pct"
        ].apply(
            lambda value: (
                f"{float(value):.0%}"
                if pd.notna(
                    value
                )
                else "—"
            )
        )

        st.write(
            "### Review association benchmark"
        )

        st.dataframe(
            review_display[
                [
                    "category",
                    "theme_label",
                    "Target association",
                    "AI-leader median",
                    "position",
                ]
            ].rename(
                columns={
                    "category":
                        "Area",
                    "theme_label":
                        "Customer association",
                    "position":
                        "Position",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )


# =========================================================
# 6. SYNTHESIS
# =========================================================

st.divider()
st.subheader(
    "5. Prioritised opportunities"
)

combined = (
    build_combined_observations(
        website_result=(
            website_result
        ),
        proposition_benchmark=(
            proposition_benchmark
        ),
        review_result=(
            review_result
        ),
    )
)

opportunities = combined[
    "opportunities"
]

strengths = combined[
    "strengths"
]

if opportunities.empty:
    if not evidence_complete:
        st.info(
            "Diagnostic not ready yet. There is not enough "
            "website/review evidence to identify meaningful "
            "differences. Complete the outstanding evidence "
            "tasks in section 2."
        )
    else:
        st.success(
            "Evidence is complete and no clear observable "
            "gaps were identified from the current website "
            "and review diagnostic."
        )
else:
    st.caption(
        "These are prioritised **hypotheses for action**, "
        "not claims that a particular signal caused the AI "
        "ranking. They identify differences between the target "
        "and businesses that AI is currently recommending."
    )

    st.dataframe(
        opportunities.rename(
            columns={
                "layer":
                    "Evidence layer",
                "priority":
                    "Priority",
                "signal":
                    "Observable signal",
                "observation":
                    "What we observed",
                "suggested_action":
                    "Potential action",
            }
        ),
        use_container_width=True,
        hide_index=True,
        height=600,
    )


if not strengths.empty:
    with st.expander(
        "Existing target strengths"
    ):
        st.dataframe(
            strengths.rename(
                columns={
                    "layer":
                        "Evidence layer",
                    "signal":
                        "Signal",
                    "observation":
                        "What we observed",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )


# =========================================================
# 7. SCOPE / NEXT
# =========================================================

st.divider()
st.subheader("6. Scope & methodology")

st.write(
    "This first diagnostic intentionally concentrates on "
    "**website evidence and Google-review evidence**. These "
    "are strong starting points because they are measurable, "
    "repeatable and — especially for the website — directly "
    "actionable by the client."
)

st.write(
    "The wider web will eventually matter too: social activity, "
    "other review platforms, directories, local/editorial "
    "coverage, backlinks and citations, community discussion "
    "and the sources used by search-grounded AI systems. "
    "Those should become a separate **External Authority & "
    "Citation** layer rather than being mixed into the website "
    "diagnostic before this workflow is proven."
)

st.write(
    "A safe client interpretation is therefore: **'We reviewed "
    "your AI visibility, identified the businesses AI currently "
    "favours, compared observable website and customer-review "
    "signals, and prioritised improvements within your control.'**"
)

link_columns = st.columns(3)

with link_columns[0]:
    st.page_link(
        "pages/0_AI_Discovery_Scan.py",
        label="AI Discovery Scan",
    )

with link_columns[1]:
    st.page_link(
        "pages/5_Website_Audits.py",
        label="Website Audits",
    )

with link_columns[2]:
    st.page_link(
        "pages/7_Review_Insights.py",
        label="Review Insights",
    )
