import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import text


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from src.database import get_engine


st.set_page_config(
    page_title="Salon Review",
    page_icon="✂️",
    layout="wide",
)

st.title("Salon Review")
st.caption("Review and classify Brighton salon candidates")


@st.cache_data(ttl=300)
def load_salon_candidates() -> pd.DataFrame:
    engine = get_engine()

    query = text(
        """
        select
            id,
            google_place_id,
            raw_data
        from raw_outscraper_locations
        where
            lower(coalesce(raw_data->>'type', '')) like '%hair%'
            or lower(coalesce(raw_data->>'subtypes', '')) like '%hair%'
            or lower(coalesce(raw_data->>'query', '')) like '%hair%'
        order by
            coalesce((raw_data->>'reviews')::integer, 0) desc
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
                "google_place_id": row["google_place_id"],
                "name": raw_data.get("name"),
                "type": raw_data.get("type"),
                "subtypes": raw_data.get("subtypes"),
                "rating": raw_data.get("rating"),
                "reviews": raw_data.get("reviews"),
                "address": raw_data.get("full_address")
                or raw_data.get("address"),
                "website": raw_data.get("site"),
            }
        )

    return pd.DataFrame(records)


try:
    salons = load_salon_candidates()
except Exception as exc:
    st.error("Salon candidates could not be loaded.")
    st.exception(exc)
    st.stop()


st.metric("Salon candidates", len(salons))

search_term = st.text_input(
    "Search salons",
    placeholder="For example: Ciscos Karma",
)

filtered_salons = salons.copy()

if search_term:
    filtered_salons = filtered_salons[
        filtered_salons["name"]
        .fillna("")
        .str.contains(search_term, case=False, regex=False)
    ]

st.dataframe(
    filtered_salons[
        [
            "name",
            "type",
            "subtypes",
            "rating",
            "reviews",
            "address",
            "website",
        ]
    ],
    use_container_width=True,
    hide_index=True,
)
