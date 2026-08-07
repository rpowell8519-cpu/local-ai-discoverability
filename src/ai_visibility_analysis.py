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
        if not unicodedata.combining(
            character
        )
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
        if normalised.startswith(
            "the "
        )
        else normalised
    )

    if (
        without_the != normalised
        and len(without_the) >= 5
    ):
        aliases.append(
            without_the
        )

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

    for candidate in list(
        aliases
    ):
        for suffix in suffixes:
            if not candidate.endswith(
                suffix
            ):
                continue

            shortened = candidate[
                :-len(suffix)
            ].strip()

            word_count = len(
                shortened.split()
            )

            # Avoid aggressive aliases such as turning a generic
            # one-word venue name into an ambiguous short token.
            if (
                len(shortened) >= 7
                and (
                    word_count >= 2
                    or normalised.startswith(
                        "the "
                    )
                )
            ):
                aliases.append(
                    shortened
                )

    return list(
        dict.fromkeys(
            aliases
        )
    )


def find_name_position(
    response_text: str,
    business_name: str,
) -> int | None:
    normalised_response = (
        " "
        + normalise_text(
            response_text
        )
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
            positions.append(
                index
            )

    return min(
        positions
    ) if positions else None


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

        position = find_name_position(
            response_text,
            name,
        )

        if position is None:
            continue

        mentions.append(
            {
                "google_place_id":
                    place_id,
                "business_name": name,
                "character_position":
                    int(position),
            }
        )

    mentions = sorted(
        mentions,
        key=lambda item: (
            item[
                "character_position"
            ],
            item[
                "business_name"
            ],
        ),
    )

    for rank, mention in enumerate(
        mentions,
        start=1,
    ):
        mention["rank"] = rank

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
        "target_position": (
            target_mention[
                "rank"
            ]
            if target_mention
            else None
        ),
        "mentioned_competitors":
            competitors,
        "mentioned_known_businesses":
            mentions,
    }


def visibility_summary(
    results: pd.DataFrame,
) -> pd.DataFrame:
    if results.empty:
        return pd.DataFrame()

    completed = results[
        results["status"]
        == "completed"
    ].copy()

    if completed.empty:
        return pd.DataFrame()

    rows = []

    for provider, frame in (
        completed.groupby(
            "provider"
        )
    ):
        mentions = frame[
            "target_mentioned"
        ].fillna(False).astype(bool)

        positions = pd.to_numeric(
            frame[
                "target_position"
            ],
            errors="coerce",
        ).dropna()

        rows.append(
            {
                "provider": provider,
                "tests_completed":
                    len(frame),
                "target_mentions":
                    int(
                        mentions.sum()
                    ),
                "visibility_rate":
                    float(
                        mentions.mean()
                    ),
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
                            frame[
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
                            frame[
                                "output_tokens"
                            ],
                            errors="coerce",
                        )
                        .fillna(0)
                        .sum()
                    ),
            }
        )

    return pd.DataFrame(
        rows
    ).sort_values(
        "visibility_rate",
        ascending=False,
    )


def competitor_mention_summary(
    results: pd.DataFrame,
) -> pd.DataFrame:
    if results.empty:
        return pd.DataFrame()

    counts = {}

    for record in results.to_dict(
        "records"
    ):
        if record.get("status") != "completed":
            continue

        mentions = record.get(
            "mentioned_known_businesses"
        ) or []

        for mention in mentions:
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
            "mentions": count,
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
            "mentions",
            "business_name",
        ],
        ascending=[
            False,
            True,
        ],
    )
