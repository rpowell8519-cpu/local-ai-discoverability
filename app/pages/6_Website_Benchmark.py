from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import text


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from src.database import get_engine
from src.taxonomy import GROUP_LABELS
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


BUILD_VERSION = "Website Benchmark v1.0.1"


st.set_page_config(
    page_title="Website Benchmark",
    page_icon="📊",
    layout="wide",
)

st.title("Website Benchmark & Gap Analysis")
st.caption(
    "Compare a target's latest website audit with "
    "its validated competitor cohort."
)
st.caption(f"Build: {BUILD_VERSION}")


@st.cache_data(ttl=300)
def load_businesses() -> pd.DataFrame:
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
            bf.business_format
        from competitor_relationship_reviews crr
        join business_features bf
          on bf.google_place_id =
             crr.candidate_google_place_id
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

    cohort_columns = [
        "google_place_id",
        "relationship_status",
        "business_name",
        "primary_group",
        "business_format",
    ]

    return pd.DataFrame(
        rows,
        columns=cohort_columns,
    )


@st.cache_data(ttl=300)
def load_pages(
    audit_run_id: str,
) -> pd.DataFrame:
    return get_audit_pages(
        audit_run_id
    )


def relationship_label(
    value: object,
) -> str:
    labels = {
        "target": "Target",
        "direct": "Direct",
        "indirect": "Indirect",
        "possible": "Possible",
        "not_relevant": "Not relevant",
    }

    return labels.get(
        str(value or ""),
        str(value or "Unknown").title(),
    )


def detected_label(
    value: object,
) -> str:
    if value is None:
        return "Unavailable"

    return (
        "Detected"
        if bool(value)
        else "Not detected"
    )


def prevalence_label(
    prevalence: object,
    found: object,
    size: object,
) -> str:
    if prevalence is None or pd.isna(
        prevalence
    ):
        return "No audited cohort"

    return (
        f"{float(prevalence):.0%} "
        f"({int(found)}/{int(size)})"
    )


try:
    businesses = load_businesses()
except Exception as exc:
    st.error(
        "Business features could not be loaded."
    )
    st.exception(exc)
    st.stop()


if businesses.empty:
    st.warning(
        "No business features are available."
    )
    st.stop()


available_groups = sorted(
    businesses["primary_group"]
    .dropna()
    .astype(str)
    .unique()
    .tolist(),
    key=lambda key: GROUP_LABELS.get(
        key,
        key,
    ),
)

default_group_index = (
    available_groups.index(
        "hair_services"
    )
    if "hair_services"
    in available_groups
    else 0
)


st.sidebar.header("Benchmark target")

selected_group = st.sidebar.selectbox(
    "Canonical group",
    options=available_groups,
    index=default_group_index,
    format_func=lambda value: (
        GROUP_LABELS.get(
            value,
            value,
        )
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

for index, place_id in enumerate(
    target_ids
):
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

profile = get_audit_profile(
    str(
        target_row.get(
            "primary_group"
        )
    )
)

st.sidebar.caption(
    f"Profile: **{profile['label']}**"
)


try:
    saved_cohort = load_saved_cohort(
        target_id
    )
except Exception as exc:
    st.error(
        "The saved competitor cohort could not "
        "be loaded."
    )
    st.exception(exc)
    st.stop()


st.sidebar.divider()
st.sidebar.header("Benchmark cohort")

cohort_scope = st.sidebar.selectbox(
    "Include",
    options=[
        "Direct competitors",
        "Direct + indirect competitors",
        "Direct + indirect + possible",
    ],
    index=1,
)

if cohort_scope == "Direct competitors":
    included_statuses = {
        "direct",
    }
elif (
    cohort_scope
    == "Direct + indirect competitors"
):
    included_statuses = {
        "direct",
        "indirect",
    }
else:
    included_statuses = {
        "direct",
        "indirect",
        "possible",
    }


if saved_cohort.empty:
    selected_cohort = (
        saved_cohort.copy()
    )
else:
    selected_cohort = saved_cohort[
        saved_cohort[
            "relationship_status"
        ].isin(
            included_statuses
        )
    ].copy()


selected_cohort_ids = (
    selected_cohort.get(
        "google_place_id",
        pd.Series(dtype="object"),
    )
    .dropna()
    .astype(str)
    .tolist()
)

selected_ids = [
    str(target_id),
    *selected_cohort_ids,
]

selected_ids = list(
    dict.fromkeys(selected_ids)
)

st.sidebar.caption(
    f"{len(selected_cohort)} validated "
    "competitor(s) selected"
)


try:
    latest_audits = get_latest_audits(
        selected_ids
    )
except Exception as exc:
    st.error(
        "Website audits could not be loaded. "
        "Confirm that the website-audit tables exist."
    )
    st.exception(exc)
    st.stop()


relationship_map = {
    str(target_id): "target",
}

if not selected_cohort.empty:
    relationship_map.update(
        selected_cohort
        .set_index("google_place_id")[
            "relationship_status"
        ]
        .astype(str)
        .to_dict()
    )


business_name_map = (
    businesses
    .drop_duplicates(
        "google_place_id"
    )
    .set_index("google_place_id")[
        "business_name"
    ]
    .to_dict()
)


if not latest_audits.empty:
    latest_audits = (
        latest_audits.copy()
    )

    latest_audits[
        "relationship_status"
    ] = latest_audits[
        "google_place_id"
    ].astype(str).map(
        relationship_map
    )

    latest_audits[
        "business_name"
    ] = latest_audits.apply(
        lambda row: (
            row.get(
                "business_name"
            )
            or business_name_map.get(
                row.get(
                    "google_place_id"
                ),
                "Unknown business",
            )
        ),
        axis=1,
    )


audited_ids = set(
    latest_audits[
        "google_place_id"
    ].astype(str).tolist()
) if not latest_audits.empty else set()

missing_ids = [
    place_id
    for place_id in selected_ids
    if str(place_id)
    not in audited_ids
]

missing_names = [
    business_name_map.get(
        place_id,
        place_id,
    )
    for place_id in missing_ids
]


pages_by_run: dict[
    str,
    pd.DataFrame,
] = {}

if not latest_audits.empty:
    for audit_run_id in latest_audits[
        "id"
    ].dropna().astype(str).tolist():
        pages_by_run[
            audit_run_id
        ] = load_pages(
            audit_run_id
        )


result = build_website_benchmark(
    target_google_place_id=target_id,
    audits=latest_audits,
    pages_by_run=pages_by_run,
    profile=profile,
)


st.subheader("Benchmark coverage")

coverage_columns = st.columns(4)

with coverage_columns[0]:
    st.metric(
        "Validated competitors",
        len(selected_cohort),
    )

with coverage_columns[1]:
    st.metric(
        "Latest audits found",
        max(
            len(latest_audits) - 1,
            0,
        )
        if not latest_audits.empty
        else 0,
    )

with coverage_columns[2]:
    st.metric(
        "Missing audits",
        len(missing_names),
    )

with coverage_columns[3]:
    st.metric(
        "Benchmark checks",
        len(profile["checks"]),
    )


if missing_names:
    st.warning(
        "No stored website audit was found for: "
        + ", ".join(
            missing_names
        )
        + ". Run these businesses through "
        "Website Audits to include them."
    )


if "error" in result:
    st.info(result["error"])
    st.write(
        "Open **Website Audits**, audit the target "
        "and selected competitors, then return here."
    )
    st.stop()


unavailable_records = result[
    "unavailable_records"
]

if unavailable_records:
    unavailable_names = [
        str(
            record.get(
                "business_name"
            )
            or "Unknown business"
        )
        + " ("
        + str(
            record.get(
                "audit_status"
            )
            or "unknown"
        )
        + ")"
        for record in unavailable_records
    ]

    st.warning(
        "Some latest audits were not usable: "
        + ", ".join(
            unavailable_names
        )
        + "."
    )


st.divider()
st.subheader("Overall website position")

summary_columns = st.columns(5)

with summary_columns[0]:
    target_score = result[
        "target_score"
    ]

    st.metric(
        "Target score",
        (
            f"{target_score:.0f}/100"
            if target_score
            is not None
            else "—"
        ),
    )

with summary_columns[1]:
    cohort_median = result[
        "cohort_median"
    ]

    score_delta = (
        target_score
        - cohort_median
        if (
            target_score
            is not None
            and cohort_median
            is not None
        )
        else None
    )

    st.metric(
        "Cohort median",
        (
            f"{cohort_median:.0f}/100"
            if cohort_median
            is not None
            else "—"
        ),
        delta=(
            f"{score_delta:+.0f} vs median"
            if score_delta
            is not None
            else None
        ),
    )

with summary_columns[2]:
    target_rank = result[
        "target_rank"
    ]
    rank_denominator = result[
        "rank_denominator"
    ]

    st.metric(
        "Target rank",
        (
            f"{target_rank} of "
            f"{rank_denominator}"
            if target_rank
            is not None
            else "—"
        ),
    )

with summary_columns[3]:
    st.metric(
        "Audited competitors",
        result[
            "audited_competitors"
        ],
    )

with summary_columns[4]:
    high_priorities = sum(
        1
        for recommendation
        in result[
            "recommendations"
        ]
        if recommendation[
            "priority"
        ]
        == "High"
    )

    st.metric(
        "High-priority gaps",
        high_priorities,
    )


score_frame = result[
    "score_comparison"
].copy()

if not score_frame.empty:
    score_frame[
        "Relationship"
    ] = score_frame[
        "relationship_status"
    ].apply(
        relationship_label
    )

    score_display = score_frame[
        [
            "rank",
            "business_name",
            "Relationship",
            "score",
            "pages_crawled",
            "audit_status",
            "completed_at",
        ]
    ].rename(
        columns={
            "rank": "Rank",
            "business_name": "Business",
            "score": "Website score",
            "pages_crawled": (
                "Pages crawled"
            ),
            "audit_status": "Status",
            "completed_at": "Audited",
        }
    )

    st.dataframe(
        score_display,
        use_container_width=True,
        hide_index=True,
    )


st.divider()
st.subheader("Feature benchmark")

feature_frame = result[
    "feature_benchmark"
].copy()

feature_frame["Target"] = feature_frame[
    "target_found"
].apply(
    detected_label
)

feature_frame[
    "Cohort prevalence"
] = feature_frame.apply(
    lambda row: prevalence_label(
        row[
            "cohort_prevalence"
        ],
        row["cohort_found"],
        row["cohort_size"],
    ),
    axis=1,
)

feature_frame["Evidence"] = feature_frame[
    "target_evidence"
].apply(
    lambda values: (
        " ".join(values)
        if values
        else "No supporting evidence detected."
    )
)

feature_display = feature_frame[
    [
        "category",
        "check",
        "Target",
        "Cohort prevalence",
        "position",
        "Evidence",
    ]
].rename(
    columns={
        "category": "Dimension",
        "check": "Check",
        "position": "Position",
    }
)

st.dataframe(
    feature_display,
    use_container_width=True,
    hide_index=True,
    height=650,
)


st.divider()
st.subheader("Prioritised gaps")

recommendations = result[
    "recommendations"
]

if not recommendations:
    st.success(
        "No evidence-led cohort gaps met the "
        "recommendation threshold."
    )
else:
    for recommendation in recommendations[
        :10
    ]:
        priority = recommendation[
            "priority"
        ]

        prevalence = recommendation[
            "cohort_prevalence"
        ]

        heading = (
            f"{priority} priority — "
            f"{recommendation['check']}"
        )

        body = (
            recommendation[
                "recommendation"
            ]
            + " Detected on "
            + str(
                recommendation[
                    "cohort_found"
                ]
            )
            + " of "
            + str(
                recommendation[
                    "cohort_size"
                ]
            )
            + " audited competitor websites "
            + f"({prevalence:.0%}), but not "
            + "detected on the target's sampled pages."
        )

        if priority == "High":
            st.error(
                f"**{heading}**\n\n{body}"
            )
        elif priority == "Medium":
            st.warning(
                f"**{heading}**\n\n{body}"
            )
        else:
            st.info(
                f"**{heading}**\n\n{body}"
            )


st.divider()
st.subheader("Detected strengths")

strengths = result[
    "strengths"
]

if not strengths:
    st.info(
        "No strengths were detected in the "
        "target's latest audit."
    )
else:
    for strength in strengths[:8]:
        prevalence = strength[
            "cohort_prevalence"
        ]

        comparison_text = (
            (
                f" Detected on "
                f"{prevalence:.0%} of the "
                "audited cohort."
            )
            if prevalence
            is not None
            else ""
        )

        evidence_text = (
            " ".join(
                strength["evidence"]
            )
            if strength[
                "evidence"
            ]
            else "Detected in the audit."
        )

        st.success(
            f"**{strength['check']}** — "
            f"{strength['position']}."
            f"{comparison_text}\n\n"
            f"{evidence_text}"
        )


with st.expander(
    "Methodology and limitations"
):
    st.write(
        "Recommendations are generated only when "
        "a feature was not detected on the target's "
        "latest sampled crawl and was detected on at "
        "least 20% of usable competitor audits."
    )

    st.write(
        "Priority combines the check's vertical "
        "importance with its prevalence across the "
        "audited competitor cohort."
    )

    st.write(
        "The crawler currently samples a capped number "
        "of pages. 'Not detected' does not prove that "
        "content is absent from the entire website. "
        "JavaScript-rendered or blocked content may also "
        "be under-represented."
    )

    st.write(
        "This remains an owned-website benchmark, "
        "not a complete AI-discoverability score."
    )
