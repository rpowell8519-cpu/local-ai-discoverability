import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import text


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from src.competitor_matching import (
    broad_business_format,
    rank_competitors,
)
from src.database import get_engine
from src import vertical_profiles as vp


BUILD_VERSION = "Universal matcher v2.1"


st.set_page_config(
    page_title="Competitor Matcher",
    page_icon="🎯",
    layout="wide",
)

st.title("Competitor Matcher")
st.caption(
    "Find and explain the closest competitors "
    "for any business in the Brighton dataset"
)
st.caption(f"Build: {BUILD_VERSION}")


@st.cache_data(ttl=300)
def load_businesses() -> pd.DataFrame:
    engine = get_engine()

    query = text(
        """
        select
            id,
            google_place_id,
            raw_data
        from raw_outscraper_locations
        order by source_row_number
        """
    )

    with engine.connect() as connection:
        rows = connection.execute(
            query
        ).mappings().all()

    records = []

    for row in rows:
        raw_data = row["raw_data"]

        if isinstance(raw_data, str):
            raw_data = json.loads(raw_data)

        record = {
            **raw_data,
            "record_id": str(row["id"]),
        }

        record["place_id"] = (
            row["google_place_id"]
            or raw_data.get("place_id")
        )

        record["primary_type"] = (
            raw_data.get("category")
            or raw_data.get("type")
            or "Unknown"
        )

        records.append(record)

    return pd.DataFrame(records)


try:
    businesses = load_businesses()
except Exception as exc:
    st.error("The business data could not be loaded.")
    st.exception(exc)
    st.stop()


required_columns = {"place_id", "name", "primary_type"}
missing_columns = required_columns - set(businesses.columns)

if missing_columns:
    st.error(
        "Required business fields are missing: "
        + ", ".join(sorted(missing_columns))
    )
    st.stop()


businesses = businesses.dropna(
    subset=["place_id", "name"]
).copy()

available_types = sorted(
    businesses["primary_type"]
    .fillna("Unknown")
    .astype(str)
    .unique()
    .tolist()
)


st.sidebar.header("Target business")

selected_type = st.sidebar.selectbox(
    "Filter target businesses by type",
    options=["All types"] + available_types,
)

target_options = businesses.copy()

if selected_type != "All types":
    target_options = target_options[
        target_options["primary_type"]
        .astype(str)
        .eq(selected_type)
    ]

target_options = target_options.sort_values(
    "name",
    na_position="last",
)

place_ids = (
    target_options["place_id"]
    .dropna()
    .drop_duplicates()
    .tolist()
)

if not place_ids:
    st.warning(
        "No businesses match the selected target type."
    )
    st.stop()

name_lookup = (
    target_options
    .drop_duplicates("place_id")
    .set_index("place_id")["name"]
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

target_place_id = st.sidebar.selectbox(
    "Target business",
    options=place_ids,
    index=default_index,
    format_func=lambda value: name_lookup.get(
        value,
        value,
    ),
)

target_record = businesses[
    businesses["place_id"] == target_place_id
].iloc[0].to_dict()

automatic_profile = vp.get_profile_for_business(
    target_record
)


st.sidebar.divider()
st.sidebar.header("Matching logic")

profile_catalog = {
    vp.GENERIC_PROFILE["key"]: vp.GENERIC_PROFILE,
    **{
        profile["key"]: profile
        for profile in vp.VERTICAL_PROFILES.values()
    },
}

profile_choice_options = [
    "Automatic",
    *profile_catalog.keys(),
]

selected_profile_choice = st.sidebar.selectbox(
    "Vertical profile",
    options=profile_choice_options,
    format_func=lambda value: (
        f"Automatic — {automatic_profile['label']}"
        if value == "Automatic"
        else profile_catalog[value]["label"]
    ),
)

profile_override = (
    None
    if selected_profile_choice == "Automatic"
    else profile_catalog[selected_profile_choice]
)

active_profile = (
    automatic_profile
    if profile_override is None
    else profile_override
)

st.sidebar.caption(
    f"Active profile: **{active_profile['label']}**"
)

candidate_scope = st.sidebar.radio(
    "Candidate scope",
    options=[
        "Profile-relevant types",
        "Same primary type",
        "All businesses",
    ],
    index=0,
    help=(
        "Profile-relevant types uses the active "
        "vertical profile. All businesses is the "
        "broadest and potentially noisiest option."
    ),
)

default_distance = float(
    active_profile.get(
        "default_distance_miles",
        5.0,
    )
)

max_distance = st.sidebar.slider(
    "Maximum distance",
    min_value=1.0,
    max_value=15.0,
    value=min(max(default_distance, 1.0), 15.0),
    step=0.5,
)

minimum_score = st.sidebar.slider(
    "Minimum similarity score",
    min_value=0,
    max_value=100,
    value=30,
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
    target, profile, ranked = rank_competitors(
        businesses=businesses,
        target_place_id=target_place_id,
        profile_override=profile_override,
        max_distance_miles=max_distance,
        candidate_scope=candidate_scope,
    )
except Exception as exc:
    st.error("Competitor matching failed.")
    st.exception(exc)
    st.stop()


target_columns = st.columns(6)

with target_columns[0]:
    st.metric(
        "Target",
        target.get("name", "Unknown"),
    )

with target_columns[1]:
    st.metric(
        "Type",
        target.get("primary_type")
        or target.get("category")
        or target.get("type")
        or "Unknown",
    )

with target_columns[2]:
    st.metric(
        "Profile",
        profile["label"],
    )

with target_columns[3]:
    st.metric(
        "Format",
        broad_business_format(target),
    )

with target_columns[4]:
    st.metric(
        "Rating",
        target.get("rating", "—"),
    )

with target_columns[5]:
    reviews_value = target.get("reviews")
    try:
        reviews_display = int(float(reviews_value))
    except (TypeError, ValueError):
        reviews_display = "—"

    st.metric(
        "Reviews",
        reviews_display,
    )


with st.expander("View active matching criteria"):
    st.write("**Candidate types/terms**")
    st.write(
        ", ".join(profile.get("candidate_terms", []))
        or "Same-primary-type fallback"
    )

    st.write("**Excluded terms**")
    st.write(
        ", ".join(profile.get("excluded_terms", []))
        or "None configured"
    )

    st.write("**Type-specific traits**")
    st.write(
        ", ".join(profile.get("traits", {}).keys())
        or "No type-specific traits configured"
    )

    st.write("**Score weights**")

    weights_table = pd.DataFrame(
        [
            {
                "Signal": key.replace("_", " ").title(),
                "Weight": f"{value:.0%}",
            }
            for key, value in profile["weights"].items()
        ]
    )

    st.dataframe(
        weights_table,
        use_container_width=True,
        hide_index=True,
    )


if ranked.empty:
    st.info(
        "No competitors matched the current settings."
    )
    st.stop()


filtered_ranked = ranked[
    ranked["Score"] >= minimum_score
].head(number_to_show).copy()

st.subheader(
    f"Top {len(filtered_ranked)} likely competitors"
)

table_columns = [
    "Rank",
    "Business",
    "Score",
    "Distance (miles)",
    "Format",
    "Category",
    "Subtypes",
    "Rating",
    "Reviews",
    "Shared traits",
    "Why matched",
]

existing_table_columns = [
    column
    for column in table_columns
    if column in filtered_ranked.columns
]

st.dataframe(
    filtered_ranked[existing_table_columns],
    use_container_width=True,
    hide_index=True,
    height=650,
)


st.divider()
st.subheader("Inspect a match")

if filtered_ranked.empty:
    st.info(
        "Lower the minimum score to see matches."
    )
    st.stop()


selected_place_id = st.selectbox(
    "Select a competitor",
    options=filtered_ranked["place_id"].tolist(),
    format_func=lambda value: filtered_ranked.loc[
        filtered_ranked["place_id"] == value,
        "Business",
    ].iloc[0],
)

selected_match = filtered_ranked[
    filtered_ranked["place_id"]
    == selected_place_id
].iloc[0]


detail_columns = st.columns(3)

with detail_columns[0]:
    st.write("### Match")
    st.metric(
        "Similarity score",
        f"{selected_match['Score']}/100",
    )
    st.write(
        f"**Distance:** "
        f"{selected_match['Distance (miles)']} miles"
    )
    st.write(
        f"**Format:** {selected_match['Format']}"
    )

with detail_columns[1]:
    st.write("### Evidence")
    st.write(
        selected_match.get("Why matched")
        or "No explanatory signals available."
    )
    st.write(
        "**Shared traits:** "
        + (
            selected_match.get("Shared traits")
            or "None detected"
        )
    )

with detail_columns[2]:
    st.write("### Public profile")
    st.write(
        f"**Rating:** {selected_match['Rating']}"
    )
    st.write(
        f"**Reviews:** {selected_match['Reviews']}"
    )

    website = selected_match.get("Website")
    maps_url = selected_match.get("Google Maps")

    if website:
        st.link_button(
            "Open website",
            str(website),
            use_container_width=True,
        )

    if maps_url:
        st.link_button(
            "Open Google Maps",
            str(maps_url),
            use_container_width=True,
        )


with st.expander("View scoring breakdown"):
    components = selected_match.get("Components") or {}

    component_data = pd.DataFrame(
        [
            {
                "Signal": signal,
                "Component score": value,
            }
            for signal, value in components.items()
        ]
    )

    st.dataframe(
        component_data,
        use_container_width=True,
        hide_index=True,
    )


st.info(
    "This is an explainable heuristic shortlist. "
    "The next build will let you approve or reject "
    "matches and save a competitor cohort for AI audits."
)
