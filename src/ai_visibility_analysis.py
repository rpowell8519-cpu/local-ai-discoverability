from __future__ import annotations

import re
import unicodedata
from typing import Any

import pandas as pd


def normalise_text(value: Any) -> str:
    text = unicodedata.normalize(
        "NFKD",
        str(value or ""),
    )
    text = "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    )
    text = text.lower()
    text = text.replace("'", "")
    text = text.replace("’", "")
    text = text.replace("&", " and ")
    text = re.sub(
        r"[^a-z0-9]+",
        " ",
        text,
    )
    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def name_aliases(
    business_name: str,
) -> list[str]:
    normalised = normalise_text(
        business_name
    )

    if not normalised:
        return []

    aliases = [normalised]

    without_the = (
        normalised[4:].strip()
        if normalised.startswith("the ")
        else normalised
    )

    if (
        without_the != normalised
        and len(without_the) >= 5
    ):
        aliases.append(without_the)

    suffixes = [
        " pub and kitchen",
        " pub and rooms",
        " coffee shop",
        " hair salon",
        " restaurant",
        " salon",
        " pub",
        " bar",
        " cafe",
    ]

    for candidate in list(aliases):
        for suffix in suffixes:
            if not candidate.endswith(suffix):
                continue

            shortened = candidate[
                :-len(suffix)
            ].strip()

            word_count = len(
                shortened.split()
            )

            if (
                len(shortened) >= 7
                and (
                    word_count >= 2
                    or normalised.startswith("the ")
                )
            ):
                aliases.append(shortened)

    return list(dict.fromkeys(aliases))


def _contains_alias(
    text: str,
    aliases: list[str],
) -> bool:
    padded = (
        " "
        + normalise_text(text)
        + " "
    )

    return any(
        (
            " "
            + alias
            + " "
        )
        in padded
        for alias in aliases
    )


def find_name_position(
    response_text: str,
    business_name: str,
) -> int | None:
    normalised_response = (
        " "
        + normalise_text(response_text)
        + " "
    )

    positions = []

    for alias in name_aliases(
        business_name
    ):
        pattern = (
            " "
            + alias
            + " "
        )

        index = (
            normalised_response.find(
                pattern
            )
        )

        if index >= 0:
            positions.append(index)

    return min(positions) if positions else None


def find_recommendation_position(
    response_text: str,
    business_name: str,
) -> int | None:
    aliases = name_aliases(
        business_name
    )

    if not aliases:
        return None

    numbered_line = re.compile(
        r"^\s*(?:#{1,6}\s*)?"
        r"(\d+)[\.\)]\s*(.+)$"
    )

    for line in str(
        response_text or ""
    ).splitlines():
        match = numbered_line.match(
            line
        )

        if not match:
            continue

        item_number = int(
            match.group(1)
        )
        item_text = match.group(2)

        if _contains_alias(
            item_text,
            aliases,
        ):
            return item_number

    return None


def analyse_visibility_response(
    *,
    response_text: str,
    target_google_place_id: str,
    target_business_name: str,
    known_businesses: list[
        dict[str, str]
    ],
) -> dict[str, Any]:
    mentions = []

    for business in known_businesses:
        place_id = str(
            business.get(
                "google_place_id"
            )
            or ""
        )
        name = str(
            business.get(
                "business_name"
            )
            or ""
        )

        if not place_id or not name:
            continue

        character_position = (
            find_name_position(
                response_text,
                name,
            )
        )

        if character_position is None:
            continue

        recommendation_position = (
            find_recommendation_position(
                response_text,
                name,
            )
        )

        mentions.append(
            {
                "google_place_id":
                    place_id,
                "business_name":
                    name,
                "character_position":
                    int(
                        character_position
                    ),
                "recommendation_position":
                    recommendation_position,
                "recommended":
                    (
                        recommendation_position
                        is not None
                    ),
            }
        )

    mentions = sorted(
        mentions,
        key=lambda item: (
            (
                item[
                    "recommendation_position"
                ]
                if item[
                    "recommendation_position"
                ]
                is not None
                else 999
            ),
            item[
                "character_position"
            ],
            item[
                "business_name"
            ],
        ),
    )

    target_mention = next(
        (
            mention
            for mention in mentions
            if mention[
                "google_place_id"
            ]
            == str(
                target_google_place_id
            )
        ),
        None,
    )

    competitors = [
        mention
        for mention in mentions
        if mention[
            "google_place_id"
        ]
        != str(
            target_google_place_id
        )
    ]

    return {
        "target_mentioned": (
            target_mention is not None
        ),
        "target_recommended": (
            bool(
                target_mention
                and target_mention[
                    "recommended"
                ]
            )
        ),
        "target_position": (
            target_mention[
                "recommendation_position"
            ]
            if target_mention
            else None
        ),
        "mentioned_competitors":
            competitors,
        "mentioned_known_businesses":
            mentions,
    }


def reanalyse_results(
    results: pd.DataFrame,
    *,
    target_google_place_id: str,
    target_business_name: str,
    known_businesses: list[
        dict[str, str]
    ],
) -> pd.DataFrame:
    if results.empty:
        return results

    frame = results.copy()

    for index, row in frame.iterrows():
        if (
            row.get("status")
            != "completed"
            or not str(
                row.get(
                    "raw_response"
                )
                or ""
            ).strip()
        ):
            continue

        analysis = (
            analyse_visibility_response(
                response_text=str(
                    row[
                        "raw_response"
                    ]
                ),
                target_google_place_id=(
                    target_google_place_id
                ),
                target_business_name=(
                    target_business_name
                ),
                known_businesses=(
                    known_businesses
                ),
            )
        )

        frame.at[
            index,
            "target_mentioned",
        ] = analysis[
            "target_mentioned"
        ]

        frame.at[
            index,
            "target_recommended",
        ] = analysis[
            "target_recommended"
        ]

        frame.at[
            index,
            "target_position",
        ] = analysis[
            "target_position"
        ]

        frame.at[
            index,
            "mentioned_competitors",
        ] = analysis[
            "mentioned_competitors"
        ]

        frame.at[
            index,
            "mentioned_known_businesses",
        ] = analysis[
            "mentioned_known_businesses"
        ]

    return frame


def visibility_summary(
    results: pd.DataFrame,
) -> pd.DataFrame:
    if results.empty:
        return pd.DataFrame()

    rows = []

    providers = sorted(
        results[
            "provider"
        ]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )

    for provider in providers:
        provider_frame = results[
            results[
                "provider"
            ]
            == provider
        ].copy()

        valid = provider_frame[
            (
                provider_frame[
                    "status"
                ]
                == "completed"
            )
            & (
                provider_frame[
                    "response_complete"
                ]
                .fillna(False)
                .astype(bool)
            )
        ].copy()

        incomplete = provider_frame[
            (
                provider_frame[
                    "status"
                ]
                == "completed"
            )
            & (
                ~provider_frame[
                    "response_complete"
                ]
                .fillna(False)
                .astype(bool)
            )
        ]

        failed = provider_frame[
            provider_frame[
                "status"
            ]
            == "failed"
        ]

        recommended = (
            valid[
                "target_recommended"
            ]
            .fillna(False)
            .astype(bool)
        )

        positions = pd.to_numeric(
            valid[
                "target_position"
            ],
            errors="coerce",
        ).dropna()

        visibility_rate = (
            float(
                recommended.mean()
            )
            if not valid.empty
            else None
        )

        rows.append(
            {
                "provider":
                    provider,
                "valid_responses":
                    len(valid),
                "incomplete_responses":
                    len(incomplete),
                "failed_responses":
                    len(failed),
                "target_recommendations":
                    int(
                        recommended.sum()
                    ),
                "visibility_rate":
                    visibility_rate,
                "average_position":
                    (
                        float(
                            positions.mean()
                        )
                        if not positions.empty
                        else None
                    ),
                "input_tokens":
                    int(
                        pd.to_numeric(
                            provider_frame[
                                "input_tokens"
                            ],
                            errors="coerce",
                        )
                        .fillna(0)
                        .sum()
                    ),
                "output_tokens":
                    int(
                        pd.to_numeric(
                            provider_frame[
                                "output_tokens"
                            ],
                            errors="coerce",
                        )
                        .fillna(0)
                        .sum()
                    ),
                "reasoning_tokens":
                    int(
                        pd.to_numeric(
                            provider_frame[
                                "reasoning_tokens"
                            ],
                            errors="coerce",
                        )
                        .fillna(0)
                        .sum()
                    ),
            }
        )

    return pd.DataFrame(rows)


def competitor_mention_summary(
    results: pd.DataFrame,
) -> pd.DataFrame:
    if results.empty:
        return pd.DataFrame()

    valid = results[
        (
            results["status"]
            == "completed"
        )
        & (
            results[
                "response_complete"
            ]
            .fillna(False)
            .astype(bool)
        )
    ]

    counts = {}

    for record in valid.to_dict(
        "records"
    ):
        mentions = record.get(
            "mentioned_known_businesses"
        ) or []

        for mention in mentions:
            if not mention.get(
                "recommended"
            ):
                continue

            place_id = str(
                mention.get(
                    "google_place_id"
                )
            )
            name = str(
                mention.get(
                    "business_name"
                )
            )

            key = (
                place_id,
                name,
            )

            counts[key] = (
                counts.get(
                    key,
                    0,
                )
                + 1
            )

    rows = [
        {
            "google_place_id":
                place_id,
            "business_name":
                name,
            "recommendations":
                count,
        }
        for (
            place_id,
            name,
        ), count in counts.items()
    ]

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(
        rows
    ).sort_values(
        [
            "recommendations",
            "business_name",
        ],
        ascending=[
            False,
            True,
        ],
    )
