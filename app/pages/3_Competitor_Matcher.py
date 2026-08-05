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
    is_eligible_hair_business,
    rank_competitors,
)
from src.database import get_engine


st.set_page_config(
    page_title="Competitor Matcher",
    page_icon="🎯",
    layout="wide",
)

st.title("Competitor Matcher")
st.caption(
    "Rank likely competitors using the Brighton "
    "Google Maps dataset"
)


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

        records.append(record)

    return pd.DataFrame(records)


try:
    businesses = load_businesses()
except Exception as exc:
    st.error("The business data could not be loaded.")
    st.exception(exc)
    st.stop()


eligible_mask = businesses.apply(
    lambda row: is_eligible_hair_business(
        row.to_dict()
    ),
    axis=1,
)

target_options = businesses[
    eligible_mask
].copy()

target_options = target_options.sort_values(
    "name",
    na_position="last",
)

if target_options.empty:
    st.warning(
        "No eligible hair businesses were found."
    )
    st.stop()


place_ids = target_options[
    "place_id"
].dropna().tolist()

target_name_lookup = (
    target_options
    .dropna(subset=["place_id"])
    .drop_duplicates("place_id")
    .set_index("place_id")["name"]
    .to_dict()
)

default_index = 0

for index, place_id in enumerate(place_ids):
    if (
        str(target_name_lookup.get(place_id, "")).lower()
        == "ciscos karma"
    ):
        default_index = index
        break


st.sidebar.header("Match settings")

target_place_id = st.sidebar.selectbox(
    "Target business",
    options=place_ids,
    index=default_index,
    format_func=lambda value: target_name_lookup.get(
        value,
        value,
    ),
)

max_distance = st.sidebar.slider(
    "Maximum distance",
    min_value=1.0,
    max_value=10.0,
    value=5.0,
    step=0.5,
    help=(
        "Candidates beyond this straight-line "
        "distance are excluded."
    ),
)

include_barbers = st.sidebar.checkbox(
    "Include barber-led businesses",
    value=False,
)

minimum_score = st.sidebar.slider(
    "Minimum similarity score",
    min_value=0,
    max_value=100,
    value=35,
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
        include_barbers=include_barbers,
    )
except Exception as exc:
    st.error("Competitor matching failed.")
    st.exception(exc)
    st.stop()


target_columns = st.columns(5)

with target_columns[0]:
    st.metric(
        "Target",
        target.get("name", "Unknown"),
    )

with target_columns[1]:
    st.metric(
        "Category",
        target.get("category")
        or target.get("type")
        or "Unknown",
    )

with target_columns[2]:
    st.metric(
        "Format",
        broad_business_format(target),
    )

with target_columns[3]:
    st.metric(
        "Rating",
        target.get("rating", "—"),
    )

with target_columns[4]:
    reviews_value = target.get("reviews")
    st.metric(
        "Reviews",
        "—" if pd.isna(reviews_value) else int(
            float(reviews_value)
        ),
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
    "Shared services",
    "Why matched",
]

st.dataframe(
    filtered_ranked[table_columns],
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
        selected_match["Why matched"]
        or "No explanatory signals available."
    )
    st.write(
        "**Shared services:** "
        + (
            selected_match["Shared services"]
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

    if selected_match.get("Website"):
        st.link_button(
            "Open website",
            selected_match["Website"],
            use_container_width=True,
        )

    if selected_match.get("Google Maps"):
        st.link_button(
            "Open Google Maps",
            selected_match["Google Maps"],
            use_container_width=True,
        )


with st.expander("View scoring breakdown"):
    component_data = pd.DataFrame(
        [
            {
                "Signal": signal,
                "Component score": value,
            }
            for signal, value in (
                selected_match["Components"]
            ).items()
        ]
    )

    st.dataframe(
        component_data,
        use_container_width=True,
        hide_index=True,
    )


st.info(
    "This is an explainable heuristic score, "
    "not a claim of proven competitive equivalence. "
    "The next step is to approve or reject the strongest "
    "matches and use those decisions to improve the model."
)
