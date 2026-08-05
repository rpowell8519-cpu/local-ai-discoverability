import json
import sys
from pathlib import Path
from typing import Any

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


def parse_json_value(value: Any) -> Any:
    """Parse JSON stored as text where possible."""
    if value is None:
        return None

    if isinstance(value, (list, dict)):
        return value

    if isinstance(value, str):
        value = value.strip()

        if not value:
            return None

        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value

    return value


def display_subtypes(value: Any) -> str:
    """Convert subtype data into readable text."""
    parsed = parse_json_value(value)

    if isinstance(parsed, list):
        return ", ".join(str(item) for item in parsed)

    if isinstance(parsed, dict):
        return ", ".join(str(item) for item in parsed.values())

    if parsed is None:
        return ""

    return str(parsed)


def safe_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


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

    df = pd.DataFrame(records)

    if "rating" in df.columns:
        df["rating"] = safe_numeric(df["rating"])

    if "reviews" in df.columns:
        df["reviews"] = safe_numeric(df["reviews"])

    if "subtypes" in df.columns:
        df["subtypes_display"] = df["subtypes"].apply(display_subtypes)
    else:
        df["subtypes_display"] = ""

    return df


try:
    df = load_businesses()
except Exception as exc:
    st.error("The business data could not be loaded.")
    st.exception(exc)
    st.stop()


# ---------------------------------------------------------
# COLUMN MAPPING
# ---------------------------------------------------------

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

address_column = next(
    (
        column
        for column in ["full_address", "address"]
        if column in df.columns
    ),
    None,
)

website_column = next(
    (
        column
        for column in ["site", "website", "website_url"]
        if column in df.columns
    ),
    None,
)

maps_column = next(
    (
        column
        for column in ["google_maps_url", "location_link"]
        if column in df.columns
    ),
    None,
)


# ---------------------------------------------------------
# SUMMARY METRICS
# ---------------------------------------------------------

metric_columns = st.columns(4)

with metric_columns[0]:
    st.metric("Businesses", len(df))

with metric_columns[1]:
    rated_count = int(df["rating"].notna().sum()) if "rating" in df else 0
    st.metric("With ratings", rated_count)

with metric_columns[2]:
    website_count = (
        int(df[website_column].notna().sum())
        if website_column
        else 0
    )
    st.metric("With websites", website_count)

with metric_columns[3]:
    average_rating = (
        round(df["rating"].mean(), 2)
        if "rating" in df and df["rating"].notna().any()
        else 0
    )
    st.metric("Average rating", average_rating)


# ---------------------------------------------------------
# FILTERS
# ---------------------------------------------------------

st.sidebar.header("Filters")

search_term = st.sidebar.text_input(
    "Business name",
    placeholder="For example: Ciscos Karma",
)

selected_types = []

if type_column:
    available_types = sorted(
        df[type_column]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )

    selected_types = st.sidebar.multiselect(
        "Primary type",
        options=available_types,
    )

available_subtypes = sorted(
    {
        subtype.strip()
        for value in df["subtypes_display"].dropna()
        for subtype in str(value).split(",")
        if subtype.strip()
    }
)

selected_subtypes = st.sidebar.multiselect(
    "Subtype",
    options=available_subtypes,
)

minimum_rating = st.sidebar.slider(
    "Minimum rating",
    min_value=0.0,
    max_value=5.0,
    value=0.0,
    step=0.1,
)

maximum_review_value = (
    int(df["reviews"].max())
    if "reviews" in df and df["reviews"].notna().any()
    else 0
)

minimum_reviews = st.sidebar.number_input(
    "Minimum review count",
    min_value=0,
    max_value=max(maximum_review_value, 1),
    value=0,
    step=10,
)

website_only = st.sidebar.checkbox(
    "Only businesses with a website"
)

operational_only = st.sidebar.checkbox(
    "Only operational businesses",
    value=True,
)


# ---------------------------------------------------------
# APPLY FILTERS
# ---------------------------------------------------------

filtered_df = df.copy()

if search_term and name_column:
    filtered_df = filtered_df[
        filtered_df[name_column]
        .fillna("")
        .astype(str)
        .str.contains(search_term, case=False, regex=False)
    ]

if selected_types and type_column:
    filtered_df = filtered_df[
        filtered_df[type_column].astype(str).isin(selected_types)
    ]

if selected_subtypes:
    subtype_pattern = "|".join(
        selected_subtypes
    )

    filtered_df = filtered_df[
        filtered_df["subtypes_display"]
        .fillna("")
        .str.contains(
            subtype_pattern,
            case=False,
            regex=True,
        )
    ]

if "rating" in filtered_df.columns:
    filtered_df = filtered_df[
        filtered_df["rating"].fillna(0) >= minimum_rating
    ]

if "reviews" in filtered_df.columns:
    filtered_df = filtered_df[
        filtered_df["reviews"].fillna(0) >= minimum_reviews
    ]

if website_only and website_column:
    filtered_df = filtered_df[
        filtered_df[website_column]
        .fillna("")
        .astype(str)
        .str.strip()
        .ne("")
    ]

if operational_only and "business_status" in filtered_df.columns:
    filtered_df = filtered_df[
        filtered_df["business_status"]
        .fillna("")
        .astype(str)
        .str.lower()
        .eq("operational")
    ]


# ---------------------------------------------------------
# RESULTS TABLE
# ---------------------------------------------------------

st.subheader(f"Showing {len(filtered_df)} businesses")

display_columns = [
    column
    for column in [
        name_column,
        type_column,
        "subtypes_display",
        "rating",
        "reviews",
        address_column,
        website_column,
    ]
    if column and column in filtered_df.columns
]

column_names = {
    name_column: "Business",
    type_column: "Type",
    "subtypes_display": "Subtypes",
    "rating": "Rating",
    "reviews": "Reviews",
    address_column: "Address",
    website_column: "Website",
}

results_df = filtered_df[display_columns].rename(
    columns=column_names
)

st.dataframe(
    results_df,
    use_container_width=True,
    hide_index=True,
    height=450,
)


# ---------------------------------------------------------
# BUSINESS DETAIL
# ---------------------------------------------------------

st.divider()
st.subheader("Business detail")

if name_column and not filtered_df.empty:
    business_options = (
        filtered_df[[name_column, "record_id"]]
        .dropna(subset=[name_column])
        .sort_values(name_column)
    )

    selected_record_id = st.selectbox(
        "Select a business",
        options=business_options["record_id"].tolist(),
        format_func=lambda record_id: business_options.loc[
            business_options["record_id"] == record_id,
            name_column,
        ].iloc[0],
    )

    selected_record = filtered_df[
        filtered_df["record_id"] == selected_record_id
    ].iloc[0]

    detail_columns = st.columns(3)

    with detail_columns[0]:
        st.write("### Business")
        st.write(selected_record.get(name_column, "Not available"))

        st.write("**Primary type**")
        st.write(
            selected_record.get(type_column, "Not available")
            if type_column
            else "Not available"
        )

        st.write("**Subtypes**")
        st.write(
            selected_record.get(
                "subtypes_display",
                "Not available",
            )
            or "Not available"
        )

    with detail_columns[1]:
        st.write("### Google profile")

        st.write("**Rating**")
        st.write(selected_record.get("rating", "Not available"))

        st.write("**Reviews**")
        st.write(selected_record.get("reviews", "Not available"))

        st.write("**Status**")
        st.write(
            selected_record.get(
                "business_status",
                "Not available",
            )
        )

    with detail_columns[2]:
        st.write("### Contact")

        st.write("**Address**")
        st.write(
            selected_record.get(
                address_column,
                "Not available",
            )
            if address_column
            else "Not available"
        )

        st.write("**Telephone**")
        st.write(selected_record.get("phone", "Not available"))

        website = (
            selected_record.get(website_column)
            if website_column
            else None
        )

        if website:
            st.link_button(
                "Open website",
                str(website),
                use_container_width=True,
            )

        maps_url = (
            selected_record.get(maps_column)
            if maps_column
            else None
        )

        if maps_url:
            st.link_button(
                "Open Google Maps",
                str(maps_url),
                use_container_width=True,
            )

    with st.expander("View complete raw record"):
        raw_record = {}

        for key, value in selected_record.to_dict().items():
            if value is None:
                continue

            if isinstance(value, float) and pd.isna(value):
                continue

            raw_record[key] = value

        st.json(raw_record)

else:
    st.info("No businesses match the selected filters.")
