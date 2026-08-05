import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import text


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from src.database import get_engine
from src.feature_extraction import (
    extract_business_features,
)
from src.taxonomy import GROUP_LABELS


st.set_page_config(
    page_title="Data Admin",
    page_icon="🧱",
    layout="wide",
)

st.title("Data Admin")
st.caption(
    "Build and inspect the derived business-feature layer"
)


def fetch_raw_businesses() -> list[dict]:
    engine = get_engine()

    query = text(
        """
        select
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

        record = dict(raw_data)
        record["google_place_id"] = (
            row["google_place_id"]
            or raw_data.get("place_id")
        )

        records.append(record)

    return records


def upsert_business_features(
    records: list[dict],
) -> None:
    engine = get_engine()

    query = text(
        """
        insert into business_features (
            google_place_id,
            business_name,
            raw_category,
            raw_type,
            raw_subtypes,
            primary_group,
            secondary_groups,
            business_format,
            traits,
            about_features,
            classification_confidence,
            classification_reasons,
            source_snapshot,
            generated_at,
            updated_at
        )
        values (
            :google_place_id,
            :business_name,
            :raw_category,
            :raw_type,
            cast(:raw_subtypes as jsonb),
            :primary_group,
            cast(:secondary_groups as jsonb),
            :business_format,
            cast(:traits as jsonb),
            cast(:about_features as jsonb),
            :classification_confidence,
            cast(:classification_reasons as jsonb),
            cast(:source_snapshot as jsonb),
            now(),
            now()
        )
        on conflict (google_place_id)
        do update set
            business_name = excluded.business_name,
            raw_category = excluded.raw_category,
            raw_type = excluded.raw_type,
            raw_subtypes = excluded.raw_subtypes,
            primary_group = excluded.primary_group,
            secondary_groups = excluded.secondary_groups,
            business_format = excluded.business_format,
            traits = excluded.traits,
            about_features = excluded.about_features,
            classification_confidence =
                excluded.classification_confidence,
            classification_reasons =
                excluded.classification_reasons,
            source_snapshot = excluded.source_snapshot,
            generated_at = now(),
            updated_at = now()
        """
    )

    serialised = [
        {
            **record,
            "raw_subtypes": json.dumps(
                record["raw_subtypes"]
            ),
            "secondary_groups": json.dumps(
                record["secondary_groups"]
            ),
            "traits": json.dumps(
                record["traits"]
            ),
            "about_features": json.dumps(
                record["about_features"]
            ),
            "classification_reasons": json.dumps(
                record["classification_reasons"]
            ),
            "source_snapshot": json.dumps(
                record["source_snapshot"]
            ),
        }
        for record in records
    ]

    batch_size = 200

    with engine.begin() as connection:
        for start in range(
            0,
            len(serialised),
            batch_size,
        ):
            connection.execute(
                query,
                serialised[
                    start:start + batch_size
                ],
            )


def load_feature_summary() -> pd.DataFrame:
    engine = get_engine()

    query = text(
        """
        select
            primary_group,
            count(*) as businesses,
            round(
                avg(classification_confidence),
                3
            ) as average_confidence
        from business_features
        group by primary_group
        order by businesses desc
        """
    )

    with engine.connect() as connection:
        rows = connection.execute(
            query
        ).mappings().all()

    return pd.DataFrame(rows)


def load_feature_preview() -> pd.DataFrame:
    engine = get_engine()

    query = text(
        """
        select
            business_name,
            primary_group,
            business_format,
            traits,
            classification_confidence,
            raw_category,
            raw_type
        from business_features
        order by
            primary_group,
            business_name
        limit 100
        """
    )

    with engine.connect() as connection:
        rows = connection.execute(
            query
        ).mappings().all()

    return pd.DataFrame(rows)


st.warning(
    "Run the supplied SQL migration in Supabase "
    "before using the rebuild button."
)

confirmation = st.checkbox(
    "I understand this will rebuild the derived "
    "features for every imported business."
)

if st.button(
    "Rebuild business features",
    type="primary",
    disabled=not confirmation,
):
    try:
        with st.spinner(
            "Reading raw businesses and extracting features..."
        ):
            raw_records = fetch_raw_businesses()

            feature_records = []
            failures = []

            for record in raw_records:
                try:
                    feature_records.append(
                        extract_business_features(
                            record
                        )
                    )
                except Exception as exc:
                    failures.append(
                        {
                            "business": record.get("name"),
                            "error": str(exc),
                        }
                    )

            upsert_business_features(
                feature_records
            )

        st.success(
            f"Built {len(feature_records)} feature records."
        )

        if failures:
            st.warning(
                f"{len(failures)} records could not be processed."
            )
            st.dataframe(
                pd.DataFrame(failures),
                use_container_width=True,
                hide_index=True,
            )

        counts = Counter(
            record["primary_group"]
            for record in feature_records
        )

        count_table = pd.DataFrame(
            [
                {
                    "Group": GROUP_LABELS.get(
                        group,
                        group,
                    ),
                    "Businesses": count,
                }
                for group, count in counts.most_common()
            ]
        )

        st.dataframe(
            count_table,
            use_container_width=True,
            hide_index=True,
        )

    except Exception as exc:
        st.error(
            "The feature build failed. Confirm that "
            "the business_features table exists."
        )
        st.exception(exc)


st.divider()
st.subheader("Current feature summary")

try:
    summary = load_feature_summary()

    if summary.empty:
        st.info(
            "No business features have been built yet."
        )
    else:
        summary["Group"] = summary[
            "primary_group"
        ].map(GROUP_LABELS).fillna(
            summary["primary_group"]
        )

        st.dataframe(
            summary[
                [
                    "Group",
                    "businesses",
                    "average_confidence",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )

        st.subheader("Preview")

        preview = load_feature_preview()

        if not preview.empty:
            preview["Group"] = preview[
                "primary_group"
            ].map(GROUP_LABELS).fillna(
                preview["primary_group"]
            )

            st.dataframe(
                preview[
                    [
                        "business_name",
                        "Group",
                        "business_format",
                        "traits",
                        "classification_confidence",
                        "raw_category",
                        "raw_type",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )

except Exception:
    st.info(
        "The business_features table is not available yet. "
        "Run the SQL migration first."
    )
