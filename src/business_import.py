from __future__ import annotations

import io
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import text


class BusinessImportError(RuntimeError):
    pass


def _normalise_column_name(value: Any) -> str:
    return (
        str(value or "")
        .replace("\ufeff", "")
        .strip()
    )


def _json_safe(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(
        value,
        (
            str,
            int,
            bool,
        ),
    ):
        return value

    if isinstance(
        value,
        float,
    ):
        if pd.isna(
            value
        ):
            return None

        return value

    if isinstance(
        value,
        (
            datetime,
            date,
        ),
    ):
        return value.isoformat()

    if isinstance(
        value,
        dict,
    ):
        return {
            str(key):
                _json_safe(
                    nested
                )
            for key, nested in value.items()
        }

    if isinstance(
        value,
        (
            list,
            tuple,
            set,
        ),
    ):
        return [
            _json_safe(
                nested
            )
            for nested in value
        ]

    if pd.isna(
        value
    ):
        return None

    if hasattr(
        value,
        "item",
    ):
        try:
            return _json_safe(
                value.item()
            )
        except Exception:
            pass

    return str(
        value
    )


def read_business_upload(
    *,
    file_bytes: bytes,
    file_name: str,
) -> pd.DataFrame:
    suffix = Path(
        file_name
    ).suffix.lower()

    buffer = io.BytesIO(
        file_bytes
    )

    if suffix == ".csv":
        try:
            frame = pd.read_csv(
                buffer,
                dtype=object,
            )
        except Exception as exc:
            raise BusinessImportError(
                "The CSV file could not be read."
            ) from exc

    elif suffix in {
        ".xlsx",
        ".xlsm",
    }:
        try:
            frame = pd.read_excel(
                buffer,
                dtype=object,
            )
        except ImportError as exc:
            raise BusinessImportError(
                "Excel import needs the `openpyxl` package. "
                "Add `openpyxl` to requirements.txt."
            ) from exc
        except Exception as exc:
            raise BusinessImportError(
                "The Excel file could not be read."
            ) from exc

    else:
        raise BusinessImportError(
            "Use an Outscraper `.xlsx` or `.csv` file."
        )

    if frame.empty:
        raise BusinessImportError(
            "The uploaded file contains no business rows."
        )

    frame = frame.copy()

    clean_columns = [
        _normalise_column_name(
            column
        )
        for column in frame.columns
    ]

    if len(
        clean_columns
    ) != len(
        set(
            clean_columns
        )
    ):
        duplicates = sorted(
            {
                column
                for column in clean_columns
                if clean_columns.count(
                    column
                ) > 1
            }
        )

        raise BusinessImportError(
            "The file contains duplicate column names: "
            + ", ".join(
                duplicates
            )
        )

    frame.columns = (
        clean_columns
    )

    place_id_column = None

    for candidate in [
        "place_id",
        "google_place_id",
    ]:
        if candidate in frame.columns:
            place_id_column = (
                candidate
            )
            break

    if not place_id_column:
        raise BusinessImportError(
            "The file must contain a `place_id` column."
        )

    name_column = None

    for candidate in [
        "name",
        "business_name",
    ]:
        if candidate in frame.columns:
            name_column = candidate
            break

    if not name_column:
        raise BusinessImportError(
            "The file must contain a `name` column."
        )

    frame[
        "_google_place_id"
    ] = frame[
        place_id_column
    ].apply(
        lambda value: (
            ""
            if pd.isna(
                value
            )
            else str(
                value
            ).strip()
        )
    )

    frame[
        "_business_name"
    ] = frame[
        name_column
    ].apply(
        lambda value: (
            ""
            if pd.isna(
                value
            )
            else str(
                value
            ).strip()
        )
    )

    frame[
        "_source_row_number"
    ] = range(
        2,
        len(
            frame
        )
        + 2,
    )

    return frame


def prepare_business_import(
    frame: pd.DataFrame,
) -> dict[str, Any]:
    if frame.empty:
        return {
            "records": [],
            "invalid_rows": pd.DataFrame(),
            "duplicate_rows_removed": 0,
            "input_rows": 0,
        }

    working = frame.copy()

    invalid_mask = (
        working[
            "_google_place_id"
        ].eq("")
        | working[
            "_business_name"
        ].eq("")
    )

    invalid = working[
        invalid_mask
    ].copy()

    valid = working[
        ~invalid_mask
    ].copy()

    input_valid_rows = len(
        valid
    )

    # When duplicate Place IDs occur in the same upload, keep the
    # last record. This favours the later row in an Outscraper export.
    valid = valid.drop_duplicates(
        subset=[
            "_google_place_id"
        ],
        keep="last",
    )

    duplicate_rows_removed = (
        input_valid_rows
        - len(
            valid
        )
    )

    helper_columns = {
        "_google_place_id",
        "_business_name",
        "_source_row_number",
    }

    records = []

    for row in valid.to_dict(
        "records"
    ):
        raw_data = {
            key:
                _json_safe(
                    value
                )
            for key, value in row.items()
            if key
            not in helper_columns
        }

        raw_data[
            "place_id"
        ] = row[
            "_google_place_id"
        ]

        if not raw_data.get(
            "name"
        ):
            raw_data[
                "name"
            ] = row[
                "_business_name"
            ]

        records.append(
            {
                "google_place_id":
                    row[
                        "_google_place_id"
                    ],
                "business_name":
                    row[
                        "_business_name"
                    ],
                "source_row_number":
                    int(
                        row[
                            "_source_row_number"
                        ]
                    ),
                "raw_data":
                    raw_data,
            }
        )

    invalid_preview_columns = [
        column
        for column in [
            "_source_row_number",
            "_business_name",
            "_google_place_id",
            "category",
            "type",
            "address",
        ]
        if column
        in invalid.columns
    ]

    invalid_preview = (
        invalid[
            invalid_preview_columns
        ].copy()
        if invalid_preview_columns
        else pd.DataFrame()
    )

    return {
        "records":
            records,
        "invalid_rows":
            invalid_preview,
        "duplicate_rows_removed":
            duplicate_rows_removed,
        "input_rows":
            len(
                frame
            ),
    }


def fetch_existing_place_ids(
    engine,
) -> set[str]:
    query = text(
        """
        select google_place_id
        from raw_outscraper_locations
        where google_place_id is not null
        """
    )

    with engine.connect() as connection:
        rows = connection.execute(
            query
        ).scalars().all()

    return {
        str(
            value
        ).strip()
        for value in rows
        if str(
            value
            or ""
        ).strip()
    }


def preview_business_import(
    *,
    engine,
    records: list[
        dict[str, Any]
    ],
) -> dict[str, Any]:
    existing = (
        fetch_existing_place_ids(
            engine
        )
    )

    incoming_ids = {
        str(
            record[
                "google_place_id"
            ]
        )
        for record in records
    }

    update_ids = (
        incoming_ids
        & existing
    )

    new_ids = (
        incoming_ids
        - existing
    )

    return {
        "existing_ids":
            existing,
        "update_ids":
            update_ids,
        "new_ids":
            new_ids,
        "update_count":
            len(
                update_ids
            ),
        "new_count":
            len(
                new_ids
            ),
        "total_valid":
            len(
                records
            ),
    }


def _load_raw_table_columns(
    engine,
) -> dict[str, dict[str, Any]]:
    query = text(
        """
        select
            column_name,
            is_nullable,
            column_default
        from information_schema.columns
        where
            table_schema = current_schema()
            and table_name = 'raw_outscraper_locations'
        order by ordinal_position
        """
    )

    with engine.connect() as connection:
        rows = connection.execute(
            query
        ).mappings().all()

    if not rows:
        raise BusinessImportError(
            "The table `raw_outscraper_locations` "
            "could not be found."
        )

    return {
        str(
            row[
                "column_name"
            ]
        ): dict(
            row
        )
        for row in rows
    }


def _validate_supported_schema(
    columns: dict[
        str,
        dict[str, Any],
    ],
) -> None:
    required_core = {
        "google_place_id",
        "raw_data",
    }

    missing_core = (
        required_core
        - set(
            columns
        )
    )

    if missing_core:
        raise BusinessImportError(
            "The raw business table is missing required columns: "
            + ", ".join(
                sorted(
                    missing_core
                )
            )
        )

    supported_required = {
        "google_place_id",
        "raw_data",
        "import_id",
        "source_row_number",
    }

    unsupported_required = []

    for name, metadata in columns.items():
        if name in supported_required:
            continue

        nullable = str(
            metadata.get(
                "is_nullable"
            )
            or ""
        ).upper() == "YES"

        has_default = (
            metadata.get(
                "column_default"
            )
            is not None
        )

        if (
            not nullable
            and not has_default
        ):
            unsupported_required.append(
                name
            )

    if unsupported_required:
        raise BusinessImportError(
            "The importer needs values for additional required "
            "columns in `raw_outscraper_locations`: "
            + ", ".join(
                unsupported_required
            )
            + ". Share the table schema before importing."
        )


def import_business_records(
    *,
    engine,
    records: list[
        dict[str, Any]
    ],
    source_file_name: str,
) -> dict[str, Any]:
    """
    Create one proper data_imports batch, then append every uploaded
    business row to raw_outscraper_locations under that import_id.

    We deliberately preserve raw import history rather than overwriting
    earlier raw rows. Existing Google Place IDs are counted as updates at
    the entity/feature layer; genuinely new Place IDs are counted as new.
    """
    if not records:
        return {
            "inserted": 0,
            "updated": 0,
            "raw_rows_added": 0,
            "import_id": None,
            "records": [],
        }

    columns = (
        _load_raw_table_columns(
            engine
        )
    )

    _validate_supported_schema(
        columns
    )

    existing_before = (
        fetch_existing_place_ids(
            engine
        )
    )

    incoming_ids = {
        str(
            record[
                "google_place_id"
            ]
        ).strip()
        for record in records
    }

    updated_count = len(
        incoming_ids
        & existing_before
    )

    inserted_count = len(
        incoming_ids
        - existing_before
    )

    create_import_query = text(
        """
        insert into data_imports (
            source_name,
            source_file,
            collected_at,
            row_count,
            notes
        )
        values (
            :source_name,
            :source_file,
            null,
            :row_count,
            :notes
        )
        returning id
        """
    )

    insert_raw_query = text(
        """
        insert into raw_outscraper_locations (
            import_id,
            source_row_number,
            google_place_id,
            raw_data
        )
        values (
            :import_id,
            :source_row_number,
            :google_place_id,
            cast(:raw_data as jsonb)
        )
        """
    )

    with engine.begin() as connection:
        import_id = connection.execute(
            create_import_query,
            {
                "source_name":
                    "outscraper_business_upload",
                "source_file":
                    source_file_name,
                "row_count":
                    len(
                        records
                    ),
                "notes":
                    (
                        "Imported through Streamlit Data Admin "
                        "Business Import v1.1."
                    ),
            },
        ).scalar_one()

        for source_row_number, record in enumerate(
            records,
            start=1,
        ):
            connection.execute(
                insert_raw_query,
                {
                    "import_id":
                        str(
                            import_id
                        ),
                    "source_row_number":
                        int(
                            source_row_number
                        ),
                    "google_place_id":
                        str(
                            record[
                                "google_place_id"
                            ]
                        ).strip(),
                    "raw_data":
                        json.dumps(
                            record[
                                "raw_data"
                            ],
                            ensure_ascii=False,
                        ),
                },
            )

    return {
        "inserted":
            inserted_count,
        "updated":
            updated_count,
        "raw_rows_added":
            len(
                records
            ),
        "import_id":
            str(
                import_id
            ),
        "records":
            records,
    }



def business_import_preview_frame(
    records: list[
        dict[str, Any]
    ],
    *,
    existing_ids: set[
        str
    ] | None = None,
) -> pd.DataFrame:
    existing_ids = (
        existing_ids
        or set()
    )

    rows = []

    for record in records:
        raw = record[
            "raw_data"
        ]

        place_id = str(
            record[
                "google_place_id"
            ]
        )

        rows.append(
            {
                "Action":
                    (
                        "Update"
                        if place_id
                        in existing_ids
                        else "Add"
                    ),
                "Business":
                    record[
                        "business_name"
                    ],
                "Place ID":
                    place_id,
                "Category":
                    raw.get(
                        "category"
                    ),
                "Type":
                    raw.get(
                        "type"
                    ),
                "Subtypes":
                    raw.get(
                        "subtypes"
                    ),
                "Postcode":
                    raw.get(
                        "postal_code"
                    ),
                "Website":
                    raw.get(
                        "website"
                    ),
            }
        )

    return pd.DataFrame(
        rows
    )
