from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

import pandas as pd


COMMON_SUFFIXES = [
    " pub and kitchen",
    " pub and rooms",
    " public house",
    " coffee shop",
    " hair salon",
    " restaurant",
    " gastropub",
    " tavern",
    " salon",
    " cafe",
    " pub",
    " bar",
    " inn",
]

LOCATION_SUFFIXES = {
    "hove",
    "brighton",
    "brighton and hove",
}


def normalise_name(
    value: Any,
) -> str:
    text = unicodedata.normalize(
        "NFKD",
        str(value or ""),
    )
    text = "".join(
        character
        for character in text
        if not unicodedata.combining(
            character
        )
    )
    text = text.lower()
    text = text.replace("’", "'")
    text = text.replace("&", " and ")
    text = re.sub(
        r"[^a-z0-9']+",
        " ",
        text,
    )
    text = text.replace("'", "")
    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def _strip_markdown(
    value: str,
) -> str:
    text = str(value or "").strip()
    text = re.sub(
        r"^[#>*_\-\s]+",
        "",
        text,
    )
    text = re.sub(
        r"[*_`]+",
        "",
        text,
    )
    return text.strip()


def extract_business_name(
    recommendation_line: str,
) -> str:
    line = str(
        recommendation_line
        or ""
    ).strip()

    bold = re.search(
        r"\*\*([^*]+)\*\*",
        line,
    )

    if bold:
        name = bold.group(1).strip()
    else:
        line = _strip_markdown(
            line
        )

        name = re.split(
            r"\s+[—–-]\s+|\s*:\s+",
            line,
            maxsplit=1,
        )[0].strip()

    return name.strip(
        " .,:;–—-"
    )


def extract_numbered_recommendations(
    response_text: str,
) -> list[dict[str, Any]]:
    recommendations = []

    if not str(
        response_text
        or ""
    ).strip():
        return recommendations

    numbered_line = re.compile(
        r"^\s*(\d{1,2})[\.\)]\s*(.+?)\s*$"
    )

    for line in str(
        response_text
    ).splitlines():
        match = numbered_line.match(
            line
        )

        if not match:
            continue

        position = int(
            match.group(1)
        )
        raw_tail = match.group(2)

        business_name = (
            extract_business_name(
                raw_tail
            )
        )

        if not business_name:
            continue

        recommendations.append(
            {
                "position":
                    position,
                "raw_business_name":
                    business_name,
            }
        )

    return recommendations


def _candidate_name_variants(
    value: str,
) -> list[str]:
    normalised = normalise_name(
        value
    )

    if not normalised:
        return []

    variants = [
        normalised
    ]

    if normalised.startswith(
        "the "
    ):
        variants.append(
            normalised[4:].strip()
        )

    # Remove common trailing geographic qualifiers.
    comma_split = re.split(
        r"\s*,\s*",
        str(
            value
            or ""
        ),
    )

    if len(comma_split) > 1:
        tail = normalise_name(
            comma_split[-1]
        )

        if tail in LOCATION_SUFFIXES:
            variants.append(
                normalise_name(
                    ",".join(
                        comma_split[:-1]
                    )
                )
            )

    # Remove simple parenthetical geographic qualifiers.
    parenthetical = re.sub(
        r"\s*\((?:hove|brighton)\)\s*$",
        "",
        str(
            value
            or ""
        ),
        flags=re.IGNORECASE,
    )

    variants.append(
        normalise_name(
            parenthetical
        )
    )

    for candidate in list(
        variants
    ):
        for suffix in (
            COMMON_SUFFIXES
        ):
            if not candidate.endswith(
                suffix
            ):
                continue

            shortened = candidate[
                :-len(suffix)
            ].strip()

            if len(shortened) >= 4:
                variants.append(
                    shortened
                )

                if shortened.startswith(
                    "the "
                ):
                    variants.append(
                        shortened[
                            4:
                        ].strip()
                    )

    return [
        item
        for item in dict.fromkeys(
            variants
        )
        if item
    ]


def build_directory_index(
    businesses: pd.DataFrame,
) -> dict[str, Any]:
    exact = {}
    records = []

    if businesses.empty:
        return {
            "exact": exact,
            "records": records,
        }

    for record in businesses.to_dict(
        "records"
    ):
        place_id = str(
            record.get(
                "google_place_id"
            )
            or ""
        )
        business_name = str(
            record.get(
                "business_name"
            )
            or ""
        )

        if (
            not place_id
            or not business_name
        ):
            continue

        aliases = (
            _candidate_name_variants(
                business_name
            )
        )

        directory_record = {
            "google_place_id":
                place_id,
            "business_name":
                business_name,
            "primary_group":
                record.get(
                    "primary_group"
                ),
            "business_format":
                record.get(
                    "business_format"
                ),
            "aliases":
                aliases,
        }

        records.append(
            directory_record
        )

        for alias in aliases:
            exact.setdefault(
                alias,
                [],
            ).append(
                directory_record
            )

    return {
        "exact": exact,
        "records": records,
    }


def resolve_business_name(
    raw_business_name: str,
    *,
    directory_index: dict[str, Any],
    primary_group: str | None = None,
    fuzzy_threshold: float = 0.90,
    margin_threshold: float = 0.05,
) -> dict[str, Any]:
    query_variants = (
        _candidate_name_variants(
            raw_business_name
        )
    )

    exact_index = (
        directory_index.get(
            "exact",
            {},
        )
    )

    exact_matches = []

    for variant in (
        query_variants
    ):
        exact_matches.extend(
            exact_index.get(
                variant,
                [],
            )
        )

    deduped_exact = {
        match[
            "google_place_id"
        ]: match
        for match in exact_matches
    }

    exact_matches = list(
        deduped_exact.values()
    )

    if len(exact_matches) == 1:
        match = exact_matches[0]

        return {
            "resolution_status":
                "exact",
            "resolution_score":
                1.0,
            "google_place_id":
                match[
                    "google_place_id"
                ],
            "business_name":
                match[
                    "business_name"
                ],
            "primary_group":
                match.get(
                    "primary_group"
                ),
            "business_format":
                match.get(
                    "business_format"
                ),
        }

    if (
        len(exact_matches) > 1
        and primary_group
    ):
        same_group = [
            match
            for match in (
                exact_matches
            )
            if str(
                match.get(
                    "primary_group"
                )
                or ""
            )
            == str(
                primary_group
            )
        ]

        if len(
            same_group
        ) == 1:
            match = (
                same_group[0]
            )

            return {
                "resolution_status":
                    "exact_group",
                "resolution_score":
                    1.0,
                "google_place_id":
                    match[
                        "google_place_id"
                    ],
                "business_name":
                    match[
                        "business_name"
                    ],
                "primary_group":
                    match.get(
                        "primary_group"
                    ),
                "business_format":
                    match.get(
                        "business_format"
                    ),
            }

    candidates = []

    for record in (
        directory_index.get(
            "records",
            []
        )
    ):
        best_score = 0.0

        for query_variant in (
            query_variants
        ):
            for alias in (
                record[
                    "aliases"
                ]
            ):
                score = (
                    SequenceMatcher(
                        None,
                        query_variant,
                        alias,
                    ).ratio()
                )

                best_score = max(
                    best_score,
                    score,
                )

        if (
            primary_group
            and str(
                record.get(
                    "primary_group"
                )
                or ""
            )
            == str(
                primary_group
            )
        ):
            best_score = min(
                1.0,
                best_score
                + 0.015,
            )

        candidates.append(
            (
                best_score,
                record,
            )
        )

    candidates.sort(
        key=lambda item: (
            item[0],
            item[1][
                "business_name"
            ],
        ),
        reverse=True,
    )

    best_score = (
        candidates[0][0]
        if candidates
        else 0.0
    )
    second_score = (
        candidates[1][0]
        if len(candidates) > 1
        else 0.0
    )

    if (
        candidates
        and best_score
        >= fuzzy_threshold
        and (
            best_score
            - second_score
        )
        >= margin_threshold
    ):
        match = candidates[0][1]

        return {
            "resolution_status":
                "fuzzy",
            "resolution_score":
                round(
                    best_score,
                    3,
                ),
            "google_place_id":
                match[
                    "google_place_id"
                ],
            "business_name":
                match[
                    "business_name"
                ],
            "primary_group":
                match.get(
                    "primary_group"
                ),
            "business_format":
                match.get(
                    "business_format"
                ),
        }

    return {
        "resolution_status":
            "unresolved",
        "resolution_score":
            (
                round(
                    best_score,
                    3,
                )
                if candidates
                else None
            ),
        "google_place_id":
            None,
        "business_name":
            raw_business_name,
        "primary_group":
            None,
        "business_format":
            None,
    }


def build_recommendation_records(
    *,
    results: pd.DataFrame,
    businesses: pd.DataFrame,
    target_google_place_id: str,
    commercial_competitor_ids: set[
        str
    ],
    primary_group: str,
) -> pd.DataFrame:
    columns = [
        "query_id",
        "base_prompt_order",
        "repeat_index",
        "prompt_category",
        "prompt_text",
        "provider",
        "model",
        "position",
        "raw_business_name",
        "google_place_id",
        "business_name",
        "resolution_status",
        "resolution_score",
        "classification",
        "rank_weight",
    ]

    if results.empty:
        return pd.DataFrame(
            columns=columns
        )

    valid = results[
        (
            results[
                "status"
            ]
            == "completed"
        )
        & (
            results[
                "response_complete"
            ]
            .fillna(False)
            .astype(bool)
        )
    ].copy()

    directory_index = (
        build_directory_index(
            businesses
        )
    )

    rows = []

    for result in valid.to_dict(
        "records"
    ):
        recommendations = (
            extract_numbered_recommendations(
                str(
                    result.get(
                        "raw_response"
                    )
                    or ""
                )
            )
        )

        for recommendation in (
            recommendations
        ):
            resolved = (
                resolve_business_name(
                    recommendation[
                        "raw_business_name"
                    ],
                    directory_index=(
                        directory_index
                    ),
                    primary_group=(
                        primary_group
                    ),
                )
            )

            resolved_id = (
                str(
                    resolved.get(
                        "google_place_id"
                    )
                )
                if resolved.get(
                    "google_place_id"
                )
                else None
            )

            if (
                resolved_id
                == str(
                    target_google_place_id
                )
            ):
                classification = (
                    "Target"
                )
            elif (
                resolved_id
                and resolved_id
                in commercial_competitor_ids
            ):
                classification = (
                    "Commercial competitor"
                )
            elif resolved_id:
                classification = (
                    "AI-discovered"
                )
            else:
                classification = (
                    "Unresolved"
                )

            position = int(
                recommendation[
                    "position"
                ]
            )

            rows.append(
                {
                    "query_id":
                        str(
                            result.get(
                                "query_id"
                            )
                        ),
                    "base_prompt_order":
                        int(
                            result.get(
                                "base_prompt_order"
                            )
                            or result.get(
                                "prompt_order"
                            )
                            or 0
                        ),
                    "repeat_index":
                        int(
                            result.get(
                                "repeat_index"
                            )
                            or 1
                        ),
                    "prompt_category":
                        result.get(
                            "prompt_category"
                        ),
                    "prompt_text":
                        result.get(
                            "prompt_text"
                        ),
                    "provider":
                        result.get(
                            "provider"
                        ),
                    "model":
                        result.get(
                            "model"
                        ),
                    "position":
                        position,
                    "raw_business_name":
                        recommendation[
                            "raw_business_name"
                        ],
                    "google_place_id":
                        resolved_id,
                    "business_name":
                        resolved[
                            "business_name"
                        ],
                    "resolution_status":
                        resolved[
                            "resolution_status"
                        ],
                    "resolution_score":
                        resolved[
                            "resolution_score"
                        ],
                    "classification":
                        classification,
                    "rank_weight":
                        1.0
                        / max(
                            position,
                            1,
                        ),
                }
            )

    return pd.DataFrame(
        rows,
        columns=columns,
    )


def _business_group_key(
    frame: pd.DataFrame,
) -> pd.Series:
    return frame.apply(
        lambda row: (
            (
                "place:"
                + str(
                    row[
                        "google_place_id"
                    ]
                )
            )
            if pd.notna(
                row[
                    "google_place_id"
                ]
            )
            and str(
                row[
                    "google_place_id"
                ]
            )
            not in {
                "",
                "None",
                "nan",
            }
            else (
                "raw:"
                + normalise_name(
                    row[
                        "raw_business_name"
                    ]
                )
            )
        ),
        axis=1,
    )


def build_business_share_table(
    recommendations: pd.DataFrame,
) -> pd.DataFrame:
    if recommendations.empty:
        return pd.DataFrame()

    working = (
        recommendations.copy()
    )

    working[
        "business_key"
    ] = _business_group_key(
        working
    )

    total_slots = len(
        working
    )

    total_weight = float(
        working[
            "rank_weight"
        ].sum()
    )

    provider_slots = (
        working.groupby(
            "provider"
        ).size().to_dict()
    )

    rows = []

    for business_key, frame in (
        working.groupby(
            "business_key"
        )
    ):
        resolved_rows = frame[
            frame[
                "google_place_id"
            ].notna()
        ]

        if not resolved_rows.empty:
            display_name = str(
                resolved_rows.iloc[
                    0
                ][
                    "business_name"
                ]
            )
            place_id = str(
                resolved_rows.iloc[
                    0
                ][
                    "google_place_id"
                ]
            )
        else:
            display_name = str(
                frame.iloc[0][
                    "raw_business_name"
                ]
            )
            place_id = None

        classification_order = [
            "Target",
            "Commercial competitor",
            "AI-discovered",
            "Unresolved",
        ]

        classifications = (
            frame[
                "classification"
            ]
            .dropna()
            .astype(str)
            .tolist()
        )

        classification = next(
            (
                item
                for item in (
                    classification_order
                )
                if item
                in classifications
            ),
            "Unresolved",
        )

        provider_counts = (
            frame.groupby(
                "provider"
            ).size().to_dict()
        )

        recommendation_count = (
            len(frame)
        )

        rank_weight = float(
            frame[
                "rank_weight"
            ].sum()
        )

        row = {
            "google_place_id":
                place_id,
            "business_name":
                display_name,
            "classification":
                classification,
            "recommendations":
                recommendation_count,
            "share_of_recommendation":
                (
                    recommendation_count
                    / total_slots
                    if total_slots
                    else None
                ),
            "position_weighted_share":
                (
                    rank_weight
                    / total_weight
                    if total_weight
                    else None
                ),
            "average_position":
                float(
                    frame[
                        "position"
                    ].mean()
                ),
            "providers":
                int(
                    frame[
                        "provider"
                    ].nunique()
                ),
        }

        for provider in sorted(
            provider_slots
        ):
            count = int(
                provider_counts.get(
                    provider,
                    0,
                )
            )

            row[
                f"{provider}_recommendations"
            ] = count
            row[
                f"{provider}_share"
            ] = (
                count
                / provider_slots[
                    provider
                ]
                if provider_slots[
                    provider
                ]
                else None
            )

        rows.append(row)

    return pd.DataFrame(
        rows
    ).sort_values(
        [
            "recommendations",
            "position_weighted_share",
        ],
        ascending=[
            False,
            False,
        ],
    ).reset_index(
        drop=True
    )


def build_provider_share_table(
    recommendations: pd.DataFrame,
    *,
    target_google_place_id: str,
) -> pd.DataFrame:
    if recommendations.empty:
        return pd.DataFrame()

    rows = []

    for provider, frame in (
        recommendations.groupby(
            "provider"
        )
    ):
        total_slots = len(
            frame
        )
        total_weight = float(
            frame[
                "rank_weight"
            ].sum()
        )

        target = frame[
            frame[
                "google_place_id"
            ].astype(str)
            == str(
                target_google_place_id
            )
        ]

        target_count = len(
            target
        )
        target_weight = float(
            target[
                "rank_weight"
            ].sum()
        )

        rows.append(
            {
                "provider":
                    provider,
                "recommendation_slots":
                    total_slots,
                "target_recommendations":
                    target_count,
                "share_of_recommendation":
                    (
                        target_count
                        / total_slots
                        if total_slots
                        else None
                    ),
                "position_weighted_share":
                    (
                        target_weight
                        / total_weight
                        if total_weight
                        else None
                    ),
            }
        )

    total_slots = len(
        recommendations
    )
    total_weight = float(
        recommendations[
            "rank_weight"
        ].sum()
    )

    all_target = recommendations[
        recommendations[
            "google_place_id"
        ].astype(str)
        == str(
            target_google_place_id
        )
    ]

    all_target_count = len(
        all_target
    )
    all_target_weight = float(
        all_target[
            "rank_weight"
        ].sum()
    )

    rows.append(
        {
            "provider":
                "All providers",
            "recommendation_slots":
                total_slots,
            "target_recommendations":
                all_target_count,
            "share_of_recommendation":
                (
                    all_target_count
                    / total_slots
                    if total_slots
                    else None
                ),
            "position_weighted_share":
                (
                    all_target_weight
                    / total_weight
                    if total_weight
                    else None
                ),
        }
    )

    return pd.DataFrame(
        rows
    )


def build_intent_stability_table(
    results: pd.DataFrame,
) -> pd.DataFrame:
    if results.empty:
        return pd.DataFrame()

    working = results.copy()

    working[
        "base_prompt_order"
    ] = pd.to_numeric(
        working[
            "base_prompt_order"
        ],
        errors="coerce",
    ).fillna(
        working[
            "prompt_order"
        ]
        if "prompt_order"
        in working
        else 0
    )

    rows = []

    grouped = working.groupby(
        [
            "base_prompt_order",
            "prompt_text",
            "provider",
        ],
        dropna=False,
    )

    for (
        base_order,
        prompt_text,
        provider,
    ), frame in grouped:
        valid = frame[
            (
                frame[
                    "status"
                ]
                == "completed"
            )
            & (
                frame[
                    "response_complete"
                ]
                .fillna(False)
                .astype(bool)
            )
        ]

        recommendations = (
            valid[
                "target_recommended"
            ]
            .fillna(False)
            .astype(bool)
        )

        positions = pd.to_numeric(
            valid.loc[
                recommendations,
                "target_position",
            ],
            errors="coerce",
        ).dropna()

        rows.append(
            {
                "base_prompt_order":
                    int(
                        base_order
                    ),
                "prompt_text":
                    prompt_text,
                "provider":
                    provider,
                "valid_repeats":
                    len(valid),
                "target_hits":
                    int(
                        recommendations.sum()
                    ),
                "hit_rate":
                    (
                        float(
                            recommendations.mean()
                        )
                        if not valid.empty
                        else None
                    ),
                "average_position":
                    (
                        float(
                            positions.mean()
                        )
                        if not positions.empty
                        else None
                    ),
                "incomplete_or_failed":
                    len(frame)
                    - len(valid),
            }
        )

    return pd.DataFrame(
        rows
    ).sort_values(
        [
            "base_prompt_order",
            "provider",
        ]
    )
