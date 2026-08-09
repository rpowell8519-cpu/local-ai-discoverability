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
from src.business_import import (
    BusinessImportError,
    business_import_preview_frame,
    import_business_records,
    prepare_business_import,
    preview_business_import,
    read_business_upload,
)
from src.taxonomy import GROUP_LABELS


st.set_page_config(
    page_title="Data Admin",
    page_icon="🧱",
    layout="wide",
)

st.title("Data Admin")
st.caption(
    "Import Outscraper business data, build and inspect the "
    "derived business-feature layer"
)
st.caption(
    "Build: Data Admin v1.1 / Business Import v1.0"
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


st.subheader(
    "1. Import business data"
)

st.write(
    "Upload an original or cleaned Outscraper business export. "
    "Google Place ID is used as the entity key: businesses already "
    "in the database are updated, genuinely new businesses are "
    "added, and duplicate Place IDs inside the upload are collapsed."
)

business_upload = st.file_uploader(
    "Outscraper business file",
    type=[
        "xlsx",
        "csv",
    ],
    help=(
        "The file must contain `place_id` and `name`. "
        "All other Outscraper columns are preserved in raw_data."
    ),
    key="data_admin_business_upload",
)

if business_upload is not None:
    try:
        uploaded_frame = (
            read_business_upload(
                file_bytes=(
                    business_upload.getvalue()
                ),
                file_name=(
                    business_upload.name
                ),
            )
        )

        prepared = (
            prepare_business_import(
                uploaded_frame
            )
        )

        import_records = (
            prepared[
                "records"
            ]
        )

        engine = get_engine()

        preview_stats = (
            preview_business_import(
                engine=engine,
                records=(
                    import_records
                ),
            )
        )

        metric_columns = st.columns(
            5
        )

        with metric_columns[0]:
            st.metric(
                "Rows in file",
                int(
                    prepared[
                        "input_rows"
                    ]
                ),
            )

        with metric_columns[1]:
            st.metric(
                "Valid businesses",
                int(
                    preview_stats[
                        "total_valid"
                    ]
                ),
            )

        with metric_columns[2]:
            st.metric(
                "New businesses",
                int(
                    preview_stats[
                        "new_count"
                    ]
                ),
            )

        with metric_columns[3]:
            st.metric(
                "Existing → update",
                int(
                    preview_stats[
                        "update_count"
                    ]
                ),
            )

        with metric_columns[4]:
            st.metric(
                "Duplicate rows removed",
                int(
                    prepared[
                        "duplicate_rows_removed"
                    ]
                ),
            )

        invalid_rows = (
            prepared[
                "invalid_rows"
            ]
        )

        if (
            invalid_rows is not None
            and not invalid_rows.empty
        ):
            st.warning(
                f"{len(invalid_rows)} row(s) are missing a "
                "business name or Place ID and will not be imported."
            )

            with st.expander(
                "Inspect invalid rows"
            ):
                st.dataframe(
                    invalid_rows,
                    use_container_width=True,
                    hide_index=True,
                )

        preview_frame = (
            business_import_preview_frame(
                import_records,
                existing_ids=(
                    preview_stats[
                        "existing_ids"
                    ]
                ),
            )
        )

        st.write(
            "### Import preview"
        )

        st.caption(
            "The preview shows what will happen to each Place ID. "
            "Existing entities are updated rather than duplicated."
        )

        st.dataframe(
            preview_frame,
            use_container_width=True,
            hide_index=True,
            height=420,
        )

        import_confirmation = (
            st.checkbox(
                "I understand this will add new businesses and "
                "update matching Place IDs in the shared database.",
                key="confirm_business_import",
            )
        )

        import_button = st.button(
            (
                f"Import {len(import_records)} "
                "businesses"
            ),
            type="primary",
            disabled=(
                not import_confirmation
                or not import_records
            ),
            key="run_business_import",
        )

        if import_button:
            try:
                with st.spinner(
                    "Validating features, importing businesses and "
                    "updating the derived feature layer..."
                ):
                    # Validate/classify before changing the raw table.
                    # This catches unexpected feature-extraction issues
                    # before the shared business data is mutated.
                    feature_records = []
                    feature_failures = []

                    for imported in import_records:
                        raw_record = dict(
                            imported[
                                "raw_data"
                            ]
                        )

                        raw_record[
                            "google_place_id"
                        ] = imported[
                            "google_place_id"
                        ]

                        try:
                            feature_records.append(
                                extract_business_features(
                                    raw_record
                                )
                            )
                        except Exception as exc:
                            feature_failures.append(
                                {
                                    "Business":
                                        imported[
                                            "business_name"
                                        ],
                                    "Place ID":
                                        imported[
                                            "google_place_id"
                                        ],
                                    "Error":
                                        str(
                                            exc
                                        ),
                                }
                            )

                    if feature_failures:
                        raise BusinessImportError(
                            f"{len(feature_failures)} business(es) "
                            "failed feature validation. Nothing was "
                            "imported. Inspect the file or error details."
                        )

                    import_result = (
                        import_business_records(
                            engine=engine,
                            records=(
                                import_records
                            ),
                            source_file_name=(
                                business_upload.name
                            ),
                        )
                    )

                    if feature_records:
                        upsert_business_features(
                            feature_records
                        )

                st.cache_data.clear()

                st.success(
                    f"Import complete: "
                    f"{int(import_result['inserted'])} new "
                    f"business(es), "
                    f"{int(import_result['updated'])} existing "
                    f"business(es) updated, and "
                    f"{len(feature_records)} feature record(s) "
                    "rebuilt automatically."
                )

                if feature_failures:
                    st.warning(
                        f"{len(feature_failures)} imported business(es) "
                        "could not be classified into business_features."
                    )

                    st.dataframe(
                        pd.DataFrame(
                            feature_failures
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.info(
                        "You do **not** need to press the full "
                        "`Rebuild business features` button after "
                        "this import. The imported businesses were "
                        "rebuilt automatically."
                    )


            except (
                BusinessImportError,
                Exception,
            ) as exc:
                st.error(
                    "The business import failed. No manual Supabase "
                    "work should be necessary; inspect the error below."
                )
                st.exception(
                    exc
                )

    except BusinessImportError as exc:
        st.error(
            str(
                exc
            )
        )

    except Exception as exc:
        st.error(
            "The uploaded business file could not be previewed."
        )
        st.exception(
            exc
        )


st.divider()
st.subheader(
    "2. Full feature-layer maintenance"
)

st.caption(
    "The full rebuild below is a maintenance tool for every raw "
    "business already stored in the database. Normal spreadsheet "
    "imports above rebuild their own feature records automatically."
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
st.subheader("3. Current feature summary")

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
