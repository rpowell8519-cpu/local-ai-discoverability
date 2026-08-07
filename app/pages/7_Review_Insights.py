from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import text


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from src.database import get_engine
from src.review_analysis import (
    analyse_reviews,
    build_review_benchmark,
)
from src.review_ingestion import (
    import_reviews,
    normalise_review_frame,
    read_outscraper_reviews,
)
from src.review_profiles import (
    get_review_profile,
)
from src.review_repository import (
    get_review_counts,
    get_reviews,
    save_theme_analysis,
)
from src.taxonomy import GROUP_LABELS


BUILD_VERSION = "Review Intelligence v1.1"


st.set_page_config(
    page_title="Review Insights",
    page_icon="💬",
    layout="wide",
)

st.title("Review Intelligence")
st.caption(
    "Import Google review exports, identify recurring "
    "customer associations and compare a target with "
    "its validated competitor cohort."
)
st.caption(f"Build: {BUILD_VERSION}")


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

active_names = {
    str(key): str(value)
    for key, value in (
        active_diagnostic.get(
            "business_names",
            {},
        )
        or {}
    ).items()
}

if active_ids:
    st.info(
        "Active diagnostic cohort: "
        f"**{active_target_name or 'Target'} + "
        f"{max(len(active_ids) - 1, 0)} AI leader(s)**. "
        "Review collection/import below is scoped to "
        "the same cohort in this browser session."
    )

    st.page_link(
        "pages/9_AI_Competitive_Diagnostic.py",
        label="← Return to AI Competitive Diagnostic",
    )


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

    columns = [
        "google_place_id",
        "relationship_status",
        "business_name",
        "primary_group",
        "business_format",
    ]

    return pd.DataFrame(
        rows,
        columns=columns,
    )


import_tab, insights_tab = st.tabs(
    [
        "Import reviews",
        "Review insights & benchmark",
    ]
)


with import_tab:
    st.subheader("Import Outscraper review files")

    if active_ids:
        st.write(
            "### Active diagnostic review collection"
        )

        try:
            active_inventory = (
                get_review_counts()
            )
        except Exception:
            active_inventory = (
                pd.DataFrame()
            )

        active_count_lookup = {}

        if not active_inventory.empty:
            active_inventory[
                "google_place_id"
            ] = active_inventory[
                "google_place_id"
            ].astype(str)

            active_count_lookup = (
                active_inventory
                .set_index(
                    "google_place_id"
                )[
                    "review_count"
                ]
                .to_dict()
            )

        collection_rows = []

        for place_id in active_ids:
            stored = int(
                active_count_lookup.get(
                    str(place_id),
                    0,
                )
                or 0
            )

            collection_rows.append(
                {
                    "Business":
                        active_names.get(
                            str(place_id),
                            str(place_id),
                        ),
                    "Google Place ID":
                        str(place_id),
                    "Reviews stored":
                        stored,
                    "Recommended collection":
                        (
                            0
                            if stored >= 100
                            else max(
                                100 - stored,
                                0,
                            )
                        ),
                    "Status":
                        (
                            "Ready"
                            if stored > 0
                            else "Missing"
                        ),
                }
            )

        collection_frame = (
            pd.DataFrame(
                collection_rows
            )
        )

        st.dataframe(
            collection_frame,
            use_container_width=True,
            hide_index=True,
        )

        missing_collection = (
            collection_frame[
                collection_frame[
                    "Reviews stored"
                ]
                == 0
            ].copy()
        )

        if missing_collection.empty:
            st.success(
                "Every business in the active diagnostic "
                "cohort already has imported review evidence."
            )
        else:
            export_frame = (
                missing_collection[
                    [
                        "Business",
                        "Google Place ID",
                    ]
                ]
                .copy()
            )

            export_frame[
                "Location"
            ] = str(
                active_diagnostic.get(
                    "location_context"
                )
                or ""
            )

            export_frame[
                "Recommended reviews"
            ] = 100

            st.download_button(
                "Download Outscraper collection list",
                data=(
                    export_frame
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
            )

            st.caption(
                "Collect roughly 100 Google reviews per "
                "missing business, then upload the resulting "
                "Outscraper file(s) below."
            )

        st.divider()

    st.write(
        "Upload one or more original Outscraper Google "
        "Reviews files. Both `.xlsx` and `.csv` are "
        "supported, and a single file may contain one "
        "or many businesses."
    )

    uploaded_files = st.file_uploader(
        "Outscraper review exports",
        type=["xlsx", "csv"],
        accept_multiple_files=True,
    )

    preview_items = []

    if uploaded_files:
        for uploaded_file in uploaded_files:
            try:
                uploaded_file.seek(0)

                raw_frame = read_outscraper_reviews(
                    uploaded_file
                )

                valid_frame, invalid_frame = (
                    normalise_review_frame(
                        raw_frame
                    )
                )

                preview_items.append(
                    {
                        "file": uploaded_file,
                        "file_name":
                            uploaded_file.name,
                        "raw_frame":
                            raw_frame,
                        "valid_frame":
                            valid_frame,
                        "invalid_frame":
                            invalid_frame,
                    }
                )

            except Exception as exc:
                st.error(
                    f"{uploaded_file.name}: {exc}"
                )

    if preview_items:
        preview_rows = []

        for item in preview_items:
            valid_frame = item[
                "valid_frame"
            ]

            names = (
                valid_frame[
                    "business_name"
                ]
                .dropna()
                .astype(str)
                .drop_duplicates()
                .tolist()
            )

            preview_rows.append(
                {
                    "File":
                        item["file_name"],
                    "Rows":
                        len(
                            item[
                                "raw_frame"
                            ]
                        ),
                    "Valid reviews":
                        len(valid_frame),
                    "Invalid rows":
                        len(
                            item[
                                "invalid_frame"
                            ]
                        ),
                    "Businesses":
                        valid_frame[
                            "google_place_id"
                        ].nunique(),
                    "Business names":
                        ", ".join(
                            names[:6]
                        )
                        + (
                            "…"
                            if len(names) > 6
                            else ""
                        ),
                }
            )

        st.dataframe(
            pd.DataFrame(
                preview_rows
            ),
            use_container_width=True,
            hide_index=True,
        )

        import_button = st.button(
            "Import review files",
            type="primary",
        )

        if import_button:
            processed = 0
            invalid = 0
            business_ids = set()

            progress = st.progress(0)

            for index, item in enumerate(
                preview_items
            ):
                result = import_reviews(
                    item["raw_frame"],
                    source_file_name=(
                        item["file_name"]
                    ),
                )

                processed += int(
                    result[
                        "processed_rows"
                    ]
                )

                invalid += int(
                    result[
                        "invalid_rows"
                    ]
                )

                business_ids.update(
                    item[
                        "valid_frame"
                    ][
                        "google_place_id"
                    ]
                    .dropna()
                    .astype(str)
                    .tolist()
                )

                progress.progress(
                    (index + 1)
                    / len(preview_items)
                )

            st.cache_data.clear()

            st.success(
                f"Import complete: {processed} review "
                f"rows processed across "
                f"{len(business_ids)} business(es). "
                f"{invalid} invalid row(s) skipped."
            )

    st.divider()
    st.subheader("Reviews currently stored")

    try:
        inventory = get_review_counts()
    except Exception as exc:
        st.info(
            "The review tables are not available yet. "
            "Run the supplied SQL migration first."
        )
        st.exception(exc)
        inventory = pd.DataFrame()

    if inventory.empty:
        st.info(
            "No reviews have been imported yet."
        )
    else:
        inventory_display = (
            inventory.rename(
                columns={
                    "business_name":
                        "Business",
                    "review_count":
                        "Reviews stored",
                    "sample_rating":
                        "Sample rating",
                    "latest_review":
                        "Latest review",
                    "earliest_review":
                        "Earliest review",
                }
            )
        )

        st.dataframe(
            inventory_display[
                [
                    "Business",
                    "Reviews stored",
                    "Sample rating",
                    "Earliest review",
                    "Latest review",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )


with insights_tab:
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
        businesses[
            "primary_group"
        ]
        .dropna()
        .astype(str)
        .unique()
        .tolist(),
        key=lambda key: (
            GROUP_LABELS.get(
                key,
                key,
            )
        ),
    )

    default_group_index = (
        available_groups.index(
            "bars_pubs"
        )
        if "bars_pubs"
        in available_groups
        else 0
    )

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

    st.sidebar.header(
        "Review benchmark target"
    )

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
        key="review_group",
    )

    target_options = businesses[
        businesses[
            "primary_group"
        ]
        == selected_group
    ].copy()

    target_options = (
        target_options.sort_values(
            "business_name"
        )
    )

    target_ids = (
        target_options[
            "google_place_id"
        ]
        .dropna()
        .drop_duplicates()
        .astype(str)
        .tolist()
    )

    target_name_lookup = (
        target_options
        .drop_duplicates(
            "google_place_id"
        )
        .assign(
            google_place_id=lambda frame: (
                frame[
                    "google_place_id"
                ].astype(str)
            )
        )
        .set_index(
            "google_place_id"
        )["business_name"]
        .to_dict()
    )

    default_target_index = 0

    if active_target_id in target_ids:
        default_target_index = (
            target_ids.index(
                active_target_id
            )
        )
    else:
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
                in {
                    "the george payne pub",
                    "george payne",
                }
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
        key="review_target",
    )

    target_row = businesses[
        businesses[
            "google_place_id"
        ].astype(str)
        == str(target_id)
    ].iloc[0].to_dict()

    profile = get_review_profile(
        str(
            target_row.get(
                "primary_group"
            )
            or "generic"
        )
    )

    st.sidebar.caption(
        f"Theme profile: **{profile['label']}**"
    )

    try:
        saved_cohort = (
            load_saved_cohort(
                target_id
            )
        )
    except Exception as exc:
        st.error(
            "Saved competitor decisions could not "
            "be loaded."
        )
        st.exception(exc)
        st.stop()

    st.sidebar.divider()
    st.sidebar.header(
        "Review cohort"
    )

    review_scope_options = [
        "Target only",
        "Direct competitors",
        "Direct + indirect competitors",
        "Direct + indirect + possible",
    ]

    if active_ids:
        review_scope_options.insert(
            0,
            "Active diagnostic cohort",
        )

    cohort_scope = st.sidebar.selectbox(
        "Include",
        options=review_scope_options,
        index=0 if active_ids else 2,
        key="review_scope",
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
    elif (
        cohort_scope
        == "Direct + indirect + possible"
    ):
        included_statuses = {
            "direct",
            "indirect",
            "possible",
        }
    else:
        included_statuses = set()

    if (
        included_statuses
        and not saved_cohort.empty
    ):
        cohort = saved_cohort[
            saved_cohort[
                "relationship_status"
            ].isin(
                included_statuses
            )
        ].copy()
    else:
        cohort = saved_cohort.iloc[
            0:0
        ].copy()

    if (
        cohort_scope
        == "Active diagnostic cohort"
        and active_ids
    ):
        selected_ids = list(
            dict.fromkeys(
                active_ids
            )
        )
    else:
        selected_ids = [
            str(target_id)
        ]

        if not cohort.empty:
            selected_ids.extend(
                cohort[
                    "google_place_id"
                ]
                .dropna()
                .astype(str)
                .tolist()
            )

        selected_ids = list(
            dict.fromkeys(
                selected_ids
            )
        )

    business_names = (
        businesses
        .drop_duplicates(
            "google_place_id"
        )
        .assign(
            google_place_id=lambda frame: (
                frame[
                    "google_place_id"
                ].astype(str)
            )
        )
        .set_index(
            "google_place_id"
        )[
            "business_name"
        ]
        .to_dict()
    )

    reviews = get_reviews(
        selected_ids
    )

    if reviews.empty:
        st.info(
            "No review data is stored for this target "
            "or cohort yet. Use the Import reviews tab "
            "to upload the Outscraper export."
        )
        st.stop()

    reviews[
        "google_place_id"
    ] = reviews[
        "google_place_id"
    ].astype(str)

    loaded_ids = set(
        reviews[
            "google_place_id"
        ].unique().tolist()
    )

    missing_review_ids = [
        place_id
        for place_id in selected_ids
        if place_id
        not in loaded_ids
    ]

    if missing_review_ids:
        missing_names = [
            business_names.get(
                place_id,
                place_id,
            )
            for place_id
            in missing_review_ids
        ]

        st.warning(
            "No imported reviews were found for: "
            + ", ".join(
                missing_names
            )
            + ". Export and upload those businesses "
            "to complete the cohort benchmark."
        )

    result = build_review_benchmark(
        target_google_place_id=(
            str(target_id)
        ),
        reviews=reviews,
        business_names=(
            business_names
        ),
        profile=profile,
    )

    target_reviews = reviews[
        reviews[
            "google_place_id"
        ]
        == str(target_id)
    ].copy()

    if target_reviews.empty:
        st.info(
            "Competitor reviews are loaded, but the "
            "target itself has no imported reviews yet."
        )
        st.stop()

    target_themes = result[
        "target_themes"
    ]

    summary = result[
        "business_summaries"
    ].copy()

    st.subheader(
        "Review coverage"
    )

    coverage_columns = st.columns(5)

    with coverage_columns[0]:
        st.metric(
            "Target reviews",
            len(target_reviews),
        )

    with coverage_columns[1]:
        st.metric(
            "Cohort businesses selected",
            len(selected_ids) - 1,
        )

    with coverage_columns[2]:
        st.metric(
            "Businesses with reviews",
            len(loaded_ids),
        )

    with coverage_columns[3]:
        target_rating = (
            pd.to_numeric(
                target_reviews[
                    "review_rating"
                ],
                errors="coerce",
            ).mean()
        )

        st.metric(
            "Target sample rating",
            (
                f"{target_rating:.2f}"
                if pd.notna(
                    target_rating
                )
                else "—"
            ),
        )

    with coverage_columns[4]:
        low_rating_count = int(
            (
                pd.to_numeric(
                    target_reviews[
                        "review_rating"
                    ],
                    errors="coerce",
                )
                <= 2
            ).sum()
        )

        st.metric(
            "Target 1–2★ reviews",
            low_rating_count,
        )

    if not summary.empty:
        summary_display = (
            summary.rename(
                columns={
                    "business_name":
                        "Business",
                    "reviews_analysed":
                        "Reviews analysed",
                    "sample_rating":
                        "Sample rating",
                    "negative_reviews":
                        "1–2★ reviews",
                    "owner_responses":
                        "Owner responses",
                }
            )
        )

        st.dataframe(
            summary_display[
                [
                    "Business",
                    "Reviews analysed",
                    "Sample rating",
                    "1–2★ reviews",
                    "Owner responses",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )

    st.divider()
    st.subheader(
        "Target customer associations"
    )

    if target_themes.empty:
        st.info(
            "No configured themes were detected."
        )
    else:
        theme_display = (
            target_themes.copy()
        )

        theme_display[
            "Mention rate"
        ] = theme_display[
            "mention_pct"
        ].apply(
            lambda value: (
                f"{float(value):.0%}"
            )
        )

        theme_display = (
            theme_display[
                theme_display[
                    "mention_count"
                ]
                > 0
            ]
            .head(20)
        )

        theme_display = (
            theme_display.rename(
                columns={
                    "category":
                        "Category",
                    "theme_label":
                        "Theme",
                    "mention_count":
                        "Mentions",
                    "positive_count":
                        "Positive",
                    "neutral_count":
                        "Neutral",
                    "negative_count":
                        "Negative",
                }
            )
        )

        st.dataframe(
            theme_display[
                [
                    "Category",
                    "Theme",
                    "Mentions",
                    "Mention rate",
                    "Positive",
                    "Neutral",
                    "Negative",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )

    benchmark = result[
        "benchmark"
    ]

    st.divider()
    st.subheader(
        "Target vs competitor associations"
    )

    if (
        len(loaded_ids) <= 1
        or benchmark.empty
    ):
        st.info(
            "Import reviews for at least one selected "
            "competitor to activate cohort comparison."
        )
    else:
        benchmark_display = (
            benchmark.copy()
        )

        benchmark_display[
            "Target"
        ] = benchmark_display[
            "target_pct"
        ].apply(
            lambda value: (
                f"{float(value):.0%}"
            )
        )

        benchmark_display[
            "Cohort median"
        ] = benchmark_display[
            "cohort_median_pct"
        ].apply(
            lambda value: (
                f"{float(value):.0%}"
                if pd.notna(value)
                else "—"
            )
        )

        benchmark_display[
            "Difference"
        ] = benchmark_display[
            "delta_vs_median"
        ].apply(
            lambda value: (
                f"{float(value):+.0%}"
                if pd.notna(value)
                else "—"
            )
        )

        benchmark_display = (
            benchmark_display.rename(
                columns={
                    "category":
                        "Category",
                    "theme_label":
                        "Association",
                    "position":
                        "Interpretation",
                }
            )
        )

        st.dataframe(
            benchmark_display[
                [
                    "Category",
                    "Association",
                    "Target",
                    "Cohort median",
                    "Difference",
                    "Interpretation",
                ]
            ],
            use_container_width=True,
            hide_index=True,
            height=600,
        )

    st.divider()
    st.subheader(
        "Inspect review evidence"
    )

    detected_target_themes = (
        target_themes[
            target_themes[
                "mention_count"
            ]
            > 0
        ]
        if not target_themes.empty
        else pd.DataFrame()
    )

    if detected_target_themes.empty:
        st.info(
            "No target theme evidence is available."
        )
    else:
        theme_keys = (
            detected_target_themes[
                "theme_key"
            ].tolist()
        )

        theme_name_lookup = (
            detected_target_themes
            .set_index(
                "theme_key"
            )["theme_label"]
            .to_dict()
        )

        selected_theme_key = (
            st.selectbox(
                "Theme",
                options=theme_keys,
                format_func=lambda value: (
                    theme_name_lookup.get(
                        value,
                        value,
                    )
                ),
            )
        )

        selected_theme = (
            detected_target_themes[
                detected_target_themes[
                    "theme_key"
                ]
                == selected_theme_key
            ].iloc[0]
        )

        evidence_columns = (
            st.columns(2)
        )

        with evidence_columns[0]:
            st.write(
                "### Positive examples"
            )

            positive_examples = (
                selected_theme[
                    "positive_examples"
                ]
            )

            if positive_examples:
                for example in (
                    positive_examples
                ):
                    st.write(
                        f"- {example}"
                    )
            else:
                st.write(
                    "No 4–5★ example "
                    "in this theme."
                )

        with evidence_columns[1]:
            st.write(
                "### Negative examples"
            )

            negative_examples = (
                selected_theme[
                    "negative_examples"
                ]
            )

            if negative_examples:
                for example in (
                    negative_examples
                ):
                    st.write(
                        f"- {example}"
                    )
            else:
                st.write(
                    "No 1–2★ example "
                    "in this theme."
                )

    st.divider()

    if st.button(
        "Save analysis snapshot for loaded businesses"
    ):
        matrix = result[
            "business_theme_matrix"
        ]

        saved = 0

        for place_id in sorted(
            loaded_ids
        ):
            business_review_frame = (
                reviews[
                    reviews[
                        "google_place_id"
                    ]
                    == place_id
                ]
            )

            business_theme_frame = (
                matrix[
                    matrix[
                        "google_place_id"
                    ]
                    == place_id
                ]
                .drop(
                    columns=[
                        "google_place_id",
                        "business_name",
                    ],
                    errors="ignore",
                )
            )

            save_theme_analysis(
                google_place_id=(
                    place_id
                ),
                business_name=(
                    business_names.get(
                        place_id,
                        place_id,
                    )
                ),
                profile_key=(
                    profile["key"]
                ),
                reviews_analysed=len(
                    business_review_frame
                ),
                themes=(
                    business_theme_frame
                ),
            )

            saved += 1

        st.success(
            f"Saved {saved} review-analysis "
            "snapshot(s) to Supabase."
        )

    with st.expander(
        "Methodology and limitations"
    ):
        st.write(
            "Review Intelligence v1 uses deterministic "
            "vertical-specific phrase matching. A review "
            "can contribute to multiple themes."
        )

        st.write(
            "Positive/negative counts currently use the "
            "review's star rating as the sentiment proxy: "
            "4–5★ positive, 3★ neutral and 1–2★ negative. "
            "This is deliberately transparent and will "
            "later be supplemented by LLM-based semantic "
            "classification."
        )

        st.write(
            "Theme percentages represent the share of "
            "the imported sample mentioning a configured "
            "theme. They should be interpreted as customer "
            "associations in the sample, not as estimates "
            "of every review ever written."
        )
