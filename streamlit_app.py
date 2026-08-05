import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from src.database import get_engine


st.set_page_config(
    page_title="Local AI Discoverability",
    page_icon="📍",
    layout="wide",
)

st.title("Local AI Discoverability")
st.caption("Brighton business data explorer")


@st.cache_data(ttl=300)
def load_businesses() -> pd.DataFrame:
    engine = get_engine()

    query = text(
        """
        select
            id,
            source_row_number,
            google_place_id,
            raw_data
        from raw_outscraper_locations
        order by source_row_number
        """
    )

    with engine.connect() as connection:
        rows = connection.execute(query).mappings().all()

    records = []

    for row in rows:
        raw_data = row["raw_data"]

        if isinstance(raw_data, str):
            raw_data = json.loads(raw_data)

        records.append(
            {
                "record_id": str(row["id"]),
                "source_row_number": row["source_row_number"],
                "google_place_id": row["google_place_id"],
                **raw_data,
            }
        )

    return pd.DataFrame(records)


try:
    df = load_businesses()
except Exception as exc:
    st.error("Could not load the business data.")
    st.exception(exc)
    st.stop()


st.metric("Businesses imported", len(df))

name_column = next(
    (
        column
        for column in ["name", "business_name", "title"]
        if column in df.columns
    ),
    None,
)

type_column = next(
    (
        column
        for column in ["type", "category", "primary_category"]
        if column in df.columns
    ),
    None,
)

rating_column = next(
    (
        column
        for column in ["rating", "reviews_rating"]
        if column in df.columns
    ),
    None,
)

reviews_column = next(
    (
        column
        for column in ["reviews", "reviews_count"]
        if column in df.columns
    ),
    None,
)

address_column = next(
    (
        column
        for column in ["full_address", "address"]
        if column in df.columns
    ),
    None,
)


st.sidebar.header("Filters")

search_term = st.sidebar.text_input(
    "Search businesses",
    placeholder="Try Ciscos Karma",
)

filtered_df = df.copy()

if search_term and name_column:
    filtered_df = filtered_df[
        filtered_df[name_column]
        .fillna("")
        .astype(str)
        .str.contains(search_term, case=False, regex=False)
    ]

if type_column:
    available_types = sorted(
        filtered_df[type_column]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )

    selected_types = st.sidebar.multiselect(
        "Business type",
        available_types,
    )

    if selected_types:
        filtered_df = filtered_df[
            filtered_df[type_column].astype(str).isin(selected_types)
        ]

st.subheader(f"Showing {len(filtered_df)} businesses")

preferred_columns = [
    column
    for column in [
        name_column,
        type_column,
        rating_column,
        reviews_column,
        address_column,
        "site",
        "phone",
        "google_place_id",
    ]
    if column and column in filtered_df.columns
]

st.dataframe(
    filtered_df[preferred_columns],
    use_container_width=True,
    hide_index=True,
)

st.divider()
st.subheader("Business detail")

if name_column and not filtered_df.empty:
    business_names = (
        filtered_df[name_column]
        .dropna()
        .astype(str)
        .sort_values()
        .tolist()
    )

    selected_business = st.selectbox(
        "Select a business",
        business_names,
    )

    selected_record = filtered_df[
        filtered_df[name_column].astype(str) == selected_business
    ].iloc[0]

    detail_columns = st.columns(3)

    with detail_columns[0]:
        st.write("**Business**")
        st.write(selected_record.get(name_column))

        if type_column:
            st.write("**Type**")
            st.write(selected_record.get(type_column))

    with detail_columns[1]:
        st.write("**Rating**")
        st.write(
            selected_record.get(rating_column)
            if rating_column
            else "Not available"
        )

        st.write("**Reviews**")
        st.write(
            selected_record.get(reviews_column)
            if reviews_column
            else "Not available"
        )

    with detail_columns[2]:
        st.write("**Address**")
        st.write(
            selected_record.get(address_column)
            if address_column
            else "Not available"
        )

        st.write("**Website**")
        st.write(selected_record.get("site", "Not available"))

    with st.expander("View complete raw record"):
        st.json(
            {
                key: value
                for key, value in selected_record.to_dict().items()
                if pd.notna(value)
            }
        )
else:
    st.info("No businesses match the selected filters.")