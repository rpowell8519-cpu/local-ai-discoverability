from __future__ import annotations

import re
from typing import Any

import pandas as pd


def _normalise_text(value: Any) -> str:
    text = str(value or "").lower()
    text = text.replace("’", "'")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _term_pattern(term: str) -> re.Pattern:
    escaped = re.escape(
        term.lower().strip()
    )
    escaped = escaped.replace(
        r"\ ",
        r"\s+",
    )

    return re.compile(
        rf"(?<!\w){escaped}(?!\w)",
        flags=re.IGNORECASE,
    )


def _review_sentiment(
    rating: Any,
) -> str:
    try:
        numeric = int(float(rating))
    except (TypeError, ValueError):
        return "neutral"

    if numeric >= 4:
        return "positive"

    if numeric <= 2:
        return "negative"

    return "neutral"


def analyse_reviews(
    reviews: pd.DataFrame,
    profile: dict[str, Any],
    *,
    max_examples: int = 3,
) -> pd.DataFrame:
    if reviews.empty:
        return pd.DataFrame(
            columns=[
                "theme_key",
                "theme_label",
                "category",
                "mention_count",
                "mention_pct",
                "positive_count",
                "neutral_count",
                "negative_count",
                "positive_examples",
                "negative_examples",
            ]
        )

    working = reviews.copy()
    working["normalised_text"] = (
        working["review_text"]
        .fillna("")
        .apply(_normalise_text)
    )
    working["sentiment"] = (
        working["review_rating"]
        .apply(_review_sentiment)
    )

    total_reviews = len(working)
    rows = []

    for theme in profile["themes"]:
        patterns = [
            _term_pattern(term)
            for term in theme["terms"]
        ]

        mask = working[
            "normalised_text"
        ].apply(
            lambda text: any(
                pattern.search(text)
                for pattern in patterns
            )
        )

        matched = working[
            mask
        ].copy()

        mention_count = len(matched)

        positive = matched[
            matched["sentiment"]
            == "positive"
        ]

        neutral = matched[
            matched["sentiment"]
            == "neutral"
        ]

        negative = matched[
            matched["sentiment"]
            == "negative"
        ]

        positive_examples = (
            positive[
                "review_text"
            ]
            .dropna()
            .astype(str)
            .head(max_examples)
            .tolist()
        )

        negative_examples = (
            negative[
                "review_text"
            ]
            .dropna()
            .astype(str)
            .head(max_examples)
            .tolist()
        )

        rows.append(
            {
                "theme_key":
                    theme["key"],
                "theme_label":
                    theme["label"],
                "category":
                    theme["category"],
                "mention_count":
                    mention_count,
                "mention_pct": (
                    mention_count
                    / total_reviews
                ),
                "positive_count":
                    len(positive),
                "neutral_count":
                    len(neutral),
                "negative_count":
                    len(negative),
                "positive_examples":
                    positive_examples,
                "negative_examples":
                    negative_examples,
            }
        )

    frame = pd.DataFrame(rows)

    return frame.sort_values(
        [
            "mention_count",
            "positive_count",
        ],
        ascending=[
            False,
            False,
        ],
    ).reset_index(drop=True)


def build_review_benchmark(
    *,
    target_google_place_id: str,
    reviews: pd.DataFrame,
    business_names: dict[str, str],
    profile: dict[str, Any],
) -> dict[str, Any]:
    if reviews.empty:
        return {
            "target_themes":
                pd.DataFrame(),
            "business_theme_matrix":
                pd.DataFrame(),
            "benchmark":
                pd.DataFrame(),
            "business_summaries":
                pd.DataFrame(),
        }

    place_ids = (
        reviews["google_place_id"]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )

    theme_frames = {}
    summary_rows = []

    for place_id in place_ids:
        business_reviews = reviews[
            reviews[
                "google_place_id"
            ].astype(str)
            == str(place_id)
        ].copy()

        themes = analyse_reviews(
            business_reviews,
            profile,
        )

        theme_frames[
            str(place_id)
        ] = themes

        rating_series = pd.to_numeric(
            business_reviews[
                "review_rating"
            ],
            errors="coerce",
        )

        summary_rows.append(
            {
                "google_place_id":
                    str(place_id),
                "business_name":
                    business_names.get(
                        str(place_id),
                        business_reviews[
                            "business_name"
                        ].dropna().astype(
                            str
                        ).head(1).iloc[
                            0
                        ]
                        if not business_reviews[
                            "business_name"
                        ].dropna().empty
                        else str(place_id),
                    ),
                "reviews_analysed":
                    len(
                        business_reviews
                    ),
                "sample_rating":
                    (
                        float(
                            rating_series.mean()
                        )
                        if rating_series.notna().any()
                        else None
                    ),
                "negative_reviews":
                    int(
                        (
                            rating_series
                            <= 2
                        ).sum()
                    ),
                "owner_responses":
                    int(
                        business_reviews[
                            "owner_answer"
                        ]
                        .fillna("")
                        .astype(str)
                        .str.strip()
                        .ne("")
                        .sum()
                    ),
            }
        )

    target_themes = theme_frames.get(
        str(target_google_place_id),
        pd.DataFrame(),
    )

    matrix_rows = []

    for place_id, themes in (
        theme_frames.items()
    ):
        name = business_names.get(
            place_id,
            place_id,
        )

        for row in themes.to_dict(
            "records"
        ):
            matrix_rows.append(
                {
                    "google_place_id":
                        place_id,
                    "business_name":
                        name,
                    **row,
                }
            )

    matrix = pd.DataFrame(
        matrix_rows
    )

    if target_themes.empty:
        benchmark = pd.DataFrame()
    else:
        competitor_ids = [
            place_id
            for place_id in place_ids
            if str(place_id)
            != str(
                target_google_place_id
            )
        ]

        benchmark_rows = []

        for target_theme in (
            target_themes.to_dict(
                "records"
            )
        ):
            theme_key = target_theme[
                "theme_key"
            ]

            competitor_theme_rows = (
                matrix[
                    (
                        matrix[
                            "theme_key"
                        ]
                        == theme_key
                    )
                    & (
                        matrix[
                            "google_place_id"
                        ].astype(str)
                        .isin(
                            [
                                str(item)
                                for item in competitor_ids
                            ]
                        )
                    )
                ]
            )

            competitor_prevalences = (
                competitor_theme_rows[
                    "mention_pct"
                ].astype(float).tolist()
            )

            cohort_median = (
                float(
                    pd.Series(
                        competitor_prevalences
                    ).median()
                )
                if competitor_prevalences
                else None
            )

            cohort_mean = (
                float(
                    pd.Series(
                        competitor_prevalences
                    ).mean()
                )
                if competitor_prevalences
                else None
            )

            target_pct = float(
                target_theme[
                    "mention_pct"
                ]
            )

            if cohort_median is None:
                position = (
                    "No cohort data"
                )
                delta = None
            else:
                delta = (
                    target_pct
                    - cohort_median
                )

                if delta >= 0.08:
                    position = (
                        "Target association"
                    )
                elif delta <= -0.08:
                    position = (
                        "Competitor association"
                    )
                else:
                    position = (
                        "In line"
                    )

            benchmark_rows.append(
                {
                    "theme_key":
                        theme_key,
                    "theme_label":
                        target_theme[
                            "theme_label"
                        ],
                    "category":
                        target_theme[
                            "category"
                        ],
                    "target_mentions":
                        int(
                            target_theme[
                                "mention_count"
                            ]
                        ),
                    "target_pct":
                        target_pct,
                    "target_positive":
                        int(
                            target_theme[
                                "positive_count"
                            ]
                        ),
                    "target_negative":
                        int(
                            target_theme[
                                "negative_count"
                            ]
                        ),
                    "cohort_median_pct":
                        cohort_median,
                    "cohort_mean_pct":
                        cohort_mean,
                    "delta_vs_median":
                        delta,
                    "position":
                        position,
                    "positive_examples":
                        target_theme[
                            "positive_examples"
                        ],
                    "negative_examples":
                        target_theme[
                            "negative_examples"
                        ],
                }
            )

        benchmark = pd.DataFrame(
            benchmark_rows
        ).sort_values(
            [
                "target_pct",
                "target_positive",
            ],
            ascending=[
                False,
                False,
            ],
        )

    return {
        "target_themes":
            target_themes,
        "business_theme_matrix":
            matrix,
        "benchmark":
            benchmark,
        "business_summaries":
            pd.DataFrame(
                summary_rows
            ),
    }
