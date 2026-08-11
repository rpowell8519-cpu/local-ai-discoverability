import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import text


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from src.competitor_matching import rank_competitors
from src.competitor_reviews import (
    LABEL_TO_STATUS,
    STATUS_LABELS,
    delete_review,
    load_reviews_for_target,
    save_review,
)
from src.database import get_engine
from src.taxonomy import GROUP_LABELS


BUILD_VERSION = "Feature Matcher v3.2 / Manual Database Add v1.0"


st.set_page_config(
    page_title="Competitor Matcher",
    page_icon="🎯",
    layout="wide",
)

st.title("Competitor Matcher")
st.caption(
    "Find, explain and validate competitors using "
    "canonical groups, formats, traits and Google attributes"
)
st.caption(f"Build: {BUILD_VERSION}")


@st.cache_data(ttl=300)
def load_feature_businesses() -> pd.DataFrame:
    engine = get_engine()

    query = text(
        """
        select
            bf.google_place_id,
            bf.business_name,
            bf.raw_category,
            bf.raw_type,
            bf.raw_subtypes,
            bf.primary_group,
            bf.secondary_groups,
            bf.business_format,
            bf.traits,
            bf.about_features,
            bf.classification_confidence,
            bf.classification_reasons,

            rol.raw_data->>'latitude' as latitude,
            rol.raw_data->>'longitude' as longitude,
            rol.raw_data->>'rating' as rating,
            rol.raw_data->>'reviews' as reviews,
            rol.raw_data->>'photos_count' as photos_count,
            rol.raw_data->>'site' as site,
            rol.raw_data->>'website' as website,
            rol.raw_data->>'booking_appointment_link'
                as booking_appointment_link,
            rol.raw_data->>'reservation_links'
                as reservation_links,
            rol.raw_data->>'location_link'
                as location_link,
            rol.raw_data->>'google_maps_url'
                as google_maps_url
        from business_features bf
        left join lateral (
            select
                raw_data
            from raw_outscraper_locations
            where google_place_id = bf.google_place_id
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


@st.cache_data(ttl=30)
def load_target_reviews(
    target_google_place_id: str,
) -> pd.DataFrame:
    return load_reviews_for_target(
        target_google_place_id
    )


try:
    businesses = load_feature_businesses()
except Exception as exc:
    st.error(
        "The feature data could not be loaded. "
        "Confirm that business_features has been built."
    )
    st.exception(exc)
    st.stop()


if businesses.empty:
    st.warning(
        "No business features are available. "
        "Open Data Admin and rebuild the feature layer."
    )
    st.stop()


available_groups = sorted(
    businesses["primary_group"]
    .dropna()
    .astype(str)
    .unique()
    .tolist(),
    key=lambda key: GROUP_LABELS.get(key, key),
)


st.sidebar.header("Target business")

selected_group = st.sidebar.selectbox(
    "Canonical competitor group",
    options=available_groups,
    format_func=lambda value: GROUP_LABELS.get(
        value,
        value,
    ),
)

target_options = businesses[
    businesses["primary_group"] == selected_group
].copy()

target_options = target_options.sort_values(
    "business_name",
    na_position="last",
)

place_ids = (
    target_options["google_place_id"]
    .dropna()
    .drop_duplicates()
    .tolist()
)

name_lookup = (
    target_options
    .drop_duplicates("google_place_id")
    .set_index("google_place_id")[
        "business_name"
    ]
    .to_dict()
)

default_index = 0

for index, place_id in enumerate(place_ids):
    if (
        str(name_lookup.get(place_id, "")).lower()
        == "ciscos karma"
    ):
        default_index = index
        break

st.sidebar.caption(
    f"{len(place_ids)} businesses available "
    f"in {GROUP_LABELS.get(selected_group, selected_group)}"
)

target_place_id = st.sidebar.selectbox(
    "Target business",
    options=place_ids,
    index=default_index,
    format_func=lambda value: name_lookup.get(
        value,
        value,
    ),
)


st.sidebar.divider()
st.sidebar.header("Matching scope")

candidate_scope = st.sidebar.radio(
    "Candidate scope",
    options=[
        "Direct formats only",
        "Direct and adjacent formats",
        "Broad market alternatives",
    ],
    index=1,
    help=(
        "Direct uses closely related formats. "
        "Adjacent includes all businesses in the same "
        "canonical group plus closely related groups. "
        "Broad includes wider substitutes."
    ),
)

default_distance = {
    "bars_pubs": 4.0,
    "coffee_cafes": 3.0,
    "hair_services": 5.0,
}.get(
    selected_group,
    5.0,
)

max_distance = st.sidebar.slider(
    "Maximum distance",
    min_value=1.0,
    max_value=15.0,
    value=default_distance,
    step=0.5,
)

minimum_score = st.sidebar.slider(
    "Minimum similarity score",
    min_value=0,
    max_value=100,
    value=25,
    step=5,
)

number_to_show = st.sidebar.slider(
    "Number of matches",
    min_value=5,
    max_value=50,
    value=25,
    step=5,
)


try:
    target, ranked = rank_competitors(
        businesses=businesses,
        target_place_id=target_place_id,
        max_distance_miles=max_distance,
        candidate_scope=candidate_scope,
    )
except Exception as exc:
    st.error("Competitor matching failed.")
    st.exception(exc)
    st.stop()


try:
    reviews = load_target_reviews(
        target_place_id
    )
except Exception as exc:
    st.error(
        "Saved competitor decisions could not be loaded. "
        "Run the competitor review SQL migration first."
    )
    st.exception(exc)
    st.stop()


if reviews.empty:
    review_lookup = {}
else:
    review_lookup = (
        reviews
        .drop_duplicates(
            "candidate_google_place_id"
        )
        .set_index(
            "candidate_google_place_id"
        )
        .to_dict("index")
    )


def relationship_label(
    candidate_google_place_id: str,
) -> str:
    review = review_lookup.get(
        candidate_google_place_id,
        {},
    )

    status = review.get(
        "relationship_status"
    )

    return STATUS_LABELS.get(
        status,
        "Unreviewed",
    )


if not ranked.empty:
    ranked["Decision"] = ranked[
        "google_place_id"
    ].apply(relationship_label)


metric_columns = st.columns(7)

with metric_columns[0]:
    st.metric(
        "Target",
        target.get("business_name", "Unknown"),
    )

with metric_columns[1]:
    st.metric(
        "Group",
        GROUP_LABELS.get(
            target.get("primary_group"),
            target.get("primary_group"),
        ),
    )

with metric_columns[2]:
    st.metric(
        "Format",
        target.get("business_format", "Unknown"),
    )

with metric_columns[3]:
    st.metric(
        "Traits",
        len(target.get("traits", [])),
    )

with metric_columns[4]:
    st.metric(
        "Rating",
        target.get("rating", "—"),
    )

with metric_columns[5]:
    try:
        reviews_display = int(
            float(target.get("reviews"))
        )
    except (TypeError, ValueError):
        reviews_display = "—"

    st.metric(
        "Reviews",
        reviews_display,
    )

with metric_columns[6]:
    st.metric(
        "Reviewed matches",
        len(review_lookup),
    )


with st.expander("View target feature profile"):
    st.write("**Canonical group**")
    st.write(
        GROUP_LABELS.get(
            target.get("primary_group"),
            target.get("primary_group"),
        )
    )

    st.write("**Business format**")
    st.write(
        target.get("business_format")
        or "Not classified"
    )

    st.write("**Traits**")
    st.write(
        ", ".join(target.get("traits", []))
        or "No configured traits detected"
    )

    st.write("**Classification confidence**")
    st.write(
        target.get("classification_confidence")
    )

    st.write("**Classification reasons**")
    st.write(
        "; ".join(
            target.get(
                "classification_reasons",
                [],
            )
        )
    )


if ranked.empty:
    st.info(
        "No competitors matched the current settings."
    )
    st.stop()


filtered_ranked = ranked[
    ranked["Score"] >= minimum_score
].head(number_to_show).copy()


st.sidebar.divider()
st.sidebar.header("Review status")

decision_filter = st.sidebar.selectbox(
    "Show decisions",
    options=[
        "All",
        "Unreviewed",
        "Direct competitor",
        "Indirect competitor",
        "Possible competitor",
        "Not relevant",
    ],
)

if decision_filter != "All":
    filtered_ranked = filtered_ranked[
        filtered_ranked["Decision"]
        == decision_filter
    ].copy()


st.subheader(
    f"Showing {len(filtered_ranked)} likely competitors"
)

table_columns = [
    "Rank",
    "Business",
    "Score",
    "Decision",
    "Distance (miles)",
    "Canonical group",
    "Format",
    "Traits",
    "Rating",
    "Reviews",
    "Why matched",
]

st.dataframe(
    filtered_ranked[table_columns],
    use_container_width=True,
    hide_index=True,
    height=650,
)


st.divider()
st.subheader(
    "Add a competitor manually"
)

st.caption(
    "The matcher is a recommendation system, not a gatekeeper. "
    "Search the **entire business database** here and add a venue "
    "to the validated competitor cohort even when its category, "
    "format or similarity score placed it outside the automatic list."
)

manual_query = st.text_input(
    "Search entire database",
    placeholder=(
        "Search by business name, type, subtype, format or group..."
    ),
    key=(
        "manual_competitor_search_"
        + str(
            target_place_id
        )
    ),
)

manual_candidates = businesses[
    businesses[
        "google_place_id"
    ].astype(str)
    != str(
        target_place_id
    )
].copy()

if manual_query.strip():
    search_term = (
        manual_query
        .strip()
        .lower()
    )

    searchable_columns = [
        "business_name",
        "raw_category",
        "raw_type",
        "raw_subtypes",
        "business_format",
        "primary_group",
    ]

    search_blob = (
        manual_candidates[
            searchable_columns
        ]
        .fillna("")
        .astype(str)
        .agg(
            " | ".join,
            axis=1,
        )
        .str.lower()
    )

    manual_candidates = (
        manual_candidates[
            search_blob.str.contains(
                search_term,
                regex=False,
            )
        ]
        .copy()
    )

    manual_candidates = (
        manual_candidates
        .drop_duplicates(
            "google_place_id"
        )
        .sort_values(
            "business_name",
            na_position="last",
        )
        .head(50)
    )

    if manual_candidates.empty:
        st.info(
            "No businesses in the full database match that search."
        )
    else:
        manual_lookup = {
            str(
                row[
                    "google_place_id"
                ]
            ): row
            for row in manual_candidates.to_dict(
                "records"
            )
        }

        manual_candidate_id = st.selectbox(
            (
                f"Matching businesses "
                f"({len(manual_candidates)} shown)"
            ),
            options=list(
                manual_lookup.keys()
            ),
            format_func=lambda value: (
                str(
                    manual_lookup[
                        value
                    ].get(
                        "business_name"
                    )
                    or value
                )
                + " — "
                + str(
                    manual_lookup[
                        value
                    ].get(
                        "raw_type"
                    )
                    or manual_lookup[
                        value
                    ].get(
                        "business_format"
                    )
                    or "Unclassified"
                )
            ),
            key=(
                "manual_competitor_candidate_"
                + str(
                    target_place_id
                )
            ),
        )

        manual_candidate = (
            manual_lookup[
                str(
                    manual_candidate_id
                )
            ]
        )

        manual_existing_review = (
            review_lookup.get(
                str(
                    manual_candidate_id
                ),
                {},
            )
        )

        manual_existing_status = (
            manual_existing_review.get(
                "relationship_status"
            )
        )

        manual_existing_label = (
            STATUS_LABELS.get(
                manual_existing_status,
                "Possible competitor",
            )
        )

        detail_cols = st.columns(
            [
                2.0,
                1.1,
                1.1,
                1.0,
            ]
        )

        with detail_cols[0]:
            st.write(
                "**"
                + str(
                    manual_candidate.get(
                        "business_name"
                    )
                    or manual_candidate_id
                )
                + "**"
            )
            st.caption(
                str(
                    manual_candidate.get(
                        "raw_subtypes"
                    )
                    or manual_candidate.get(
                        "raw_type"
                    )
                    or ""
                )
            )

        with detail_cols[1]:
            st.write(
                "**Group**"
            )
            st.write(
                GROUP_LABELS.get(
                    manual_candidate.get(
                        "primary_group"
                    ),
                    manual_candidate.get(
                        "primary_group"
                    )
                    or "—",
                )
            )

        with detail_cols[2]:
            st.write(
                "**Format**"
            )
            st.write(
                manual_candidate.get(
                    "business_format"
                )
                or "—"
            )

        with detail_cols[3]:
            current_decision = (
                STATUS_LABELS.get(
                    manual_existing_status,
                    "Unreviewed",
                )
            )
            st.write(
                "**Current decision**"
            )
            st.write(
                current_decision
            )

        with st.form(
            key=(
                "manual_competitor_add_form_"
                + str(
                    target_place_id
                )
                + "_"
                + str(
                    manual_candidate_id
                )
            )
        ):
            manual_relationship = (
                st.selectbox(
                    "Relationship to target",
                    options=list(
                        LABEL_TO_STATUS.keys()
                    ),
                    index=list(
                        LABEL_TO_STATUS.keys()
                    ).index(
                        manual_existing_label
                    ),
                    key=(
                        "manual_relationship_"
                        + str(
                            manual_candidate_id
                        )
                    ),
                )
            )

            manual_notes = st.text_area(
                "Notes",
                value=(
                    manual_existing_review.get(
                        "reviewer_notes",
                        "",
                    )
                    or ""
                ),
                placeholder=(
                    "For example: known local competitor despite "
                    "being classified in another Google category."
                ),
                key=(
                    "manual_notes_"
                    + str(
                        manual_candidate_id
                    )
                ),
            )

            manual_reviewed_by = (
                st.text_input(
                    "Reviewed by",
                    value=(
                        manual_existing_review.get(
                            "reviewed_by",
                            "",
                        )
                        or ""
                    ),
                    key=(
                        "manual_reviewed_by_"
                        + str(
                            manual_candidate_id
                        )
                    ),
                )
            )

            manual_save = (
                st.form_submit_button(
                    (
                        "Add / update validated competitor"
                        if not manual_existing_review
                        else "Update competitor decision"
                    ),
                    type="primary",
                )
            )

        if manual_save:
            save_review(
                target_google_place_id=(
                    target_place_id
                ),
                candidate_google_place_id=(
                    str(
                        manual_candidate_id
                    )
                ),
                relationship_status=(
                    LABEL_TO_STATUS[
                        manual_relationship
                    ]
                ),
                reviewer_notes=(
                    manual_notes
                ),
                reviewed_by=(
                    manual_reviewed_by
                ),
            )

            load_target_reviews.clear()

            st.success(
                f"{manual_candidate.get('business_name')} "
                "has been added to the validated competitor cohort."
            )

            st.rerun()
else:
    st.info(
        "Start typing to search every business currently held "
        "in `business_features`."
    )


st.divider()
st.subheader("Inspect and classify a match")

if filtered_ranked.empty:
    st.info(
        "No matches remain under the current filters."
    )
    st.stop()


selected_candidate_id = st.selectbox(
    "Select a competitor",
    options=filtered_ranked[
        "google_place_id"
    ].tolist(),
    format_func=lambda value: filtered_ranked.loc[
        filtered_ranked["google_place_id"]
        == value,
        "Business",
    ].iloc[0],
)

selected_match = filtered_ranked[
    filtered_ranked["google_place_id"]
    == selected_candidate_id
].iloc[0]

existing_review = review_lookup.get(
    selected_candidate_id,
    {},
)

existing_status = existing_review.get(
    "relationship_status"
)

existing_label = STATUS_LABELS.get(
    existing_status,
    "Possible competitor",
)


detail_columns = st.columns(3)

with detail_columns[0]:
    st.write("### Overall match")
    st.metric(
        "Similarity",
        f"{selected_match['Score']}/100",
    )

    distance = selected_match[
        "Distance (miles)"
    ]

    st.write(
        "**Distance:** "
        + (
            f"{distance} miles"
            if pd.notna(distance)
            else "Unknown"
        )
    )
    st.write(
        f"**Format:** {selected_match['Format']}"
    )

with detail_columns[1]:
    st.write("### Shared")
    shared_traits = selected_match[
        "Shared traits"
    ]
    shared_attributes = selected_match[
        "Shared attributes"
    ]

    st.write("**Traits**")
    st.write(
        ", ".join(shared_traits)
        if shared_traits
        else "No configured shared traits"
    )

    st.write("**Google attributes**")
    st.write(
        ", ".join(shared_attributes[:10])
        if shared_attributes
        else "No comparable shared positive attributes"
    )

with detail_columns[2]:
    st.write("### Different")
    different_attributes = selected_match[
        "Different attributes"
    ]
    candidate_only_traits = selected_match[
        "Candidate-only traits"
    ]

    st.write("**Candidate-only traits**")
    st.write(
        ", ".join(candidate_only_traits)
        if candidate_only_traits
        else "None"
    )

    st.write("**Conflicting attributes**")
    st.write(
        ", ".join(different_attributes[:10])
        if different_attributes
        else "None detected"
    )


with st.form(
    key=(
        "competitor_review_"
        f"{target_place_id}_"
        f"{selected_candidate_id}"
    )
):
    st.write("### Your decision")

    relationship_label_value = st.selectbox(
        "Relationship to target",
        options=list(
            LABEL_TO_STATUS.keys()
        ),
        index=list(
            LABEL_TO_STATUS.keys()
        ).index(existing_label),
    )

    reviewer_notes = st.text_area(
        "Notes",
        value=existing_review.get(
            "reviewer_notes",
            "",
        )
        or "",
        placeholder=(
            "Why is this business a direct, indirect "
            "or irrelevant competitor?"
        ),
    )

    reviewed_by = st.text_input(
        "Reviewed by",
        value=existing_review.get(
            "reviewed_by",
            "",
        )
        or "",
        placeholder="For example: Rob",
    )

    save_decision = st.form_submit_button(
        "Save competitor decision",
        type="primary",
    )


if save_decision:
    save_review(
        target_google_place_id=target_place_id,
        candidate_google_place_id=(
            selected_candidate_id
        ),
        relationship_status=LABEL_TO_STATUS[
            relationship_label_value
        ],
        reviewer_notes=reviewer_notes,
        reviewed_by=reviewed_by,
    )

    load_target_reviews.clear()

    st.success("Competitor decision saved.")
    st.rerun()


if existing_review:
    if st.button(
        "Clear saved decision",
        type="secondary",
    ):
        delete_review(
            target_google_place_id=target_place_id,
            candidate_google_place_id=(
                selected_candidate_id
            ),
        )

        load_target_reviews.clear()

        st.success("Saved decision removed.")
        st.rerun()


with st.expander("View scoring breakdown"):
    components = selected_match["Components"]

    component_table = pd.DataFrame(
        [
            {
                "Dimension": dimension,
                "Score": score,
            }
            for dimension, score in components.items()
        ]
    )

    st.dataframe(
        component_table,
        use_container_width=True,
        hide_index=True,
    )


link_columns = st.columns(2)

website = selected_match.get("Website")
maps_url = selected_match.get("Google Maps")

with link_columns[0]:
    if website:
        st.link_button(
            "Open competitor website",
            str(website),
            use_container_width=True,
        )

with link_columns[1]:
    if maps_url:
        st.link_button(
            "Open Google Maps",
            str(maps_url),
            use_container_width=True,
        )


st.info(
    "Saved direct, indirect and possible competitors "
    "form the validated cohort that will later be used "
    "for website comparisons and AI visibility audits."
)
