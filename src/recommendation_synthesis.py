from __future__ import annotations

import math
import re
from typing import Any

import pandas as pd


# ---------------------------------------------------------------------
# Vertical relevance
# ---------------------------------------------------------------------

# These are recommendation-relevance weights, not claims about AI
# ranking factors. They answer a narrower product question:
# "If this gap exists, how relevant is it to this kind of business?"
#
# Signals not explicitly listed fall back to the default map.
DEFAULT_RELEVANCE = {
    "https": 0.55,
    "homepage title": 0.75,
    "meta description": 0.60,
    "canonical url": 0.70,
    "xml sitemap": 0.70,
    "relevant local-business schema": 1.00,
    "contact information": 1.00,
    "address/location information": 1.00,
    "opening-hours information": 0.95,
    "service or offering coverage": 0.95,
    "pricing information": 0.80,
    "social-profile links": 0.35,
    "booking or reservation journey": 0.55,
    "faq content": 0.50,
}

VERTICAL_RELEVANCE = {
    "coffee_cafes": {
        "booking or reservation journey": 0.15,
        "pricing information": 0.85,
        "service or offering coverage": 1.00,
        "opening-hours information": 1.00,
        "relevant local-business schema": 1.00,
        "contact information": 1.00,
        "social-profile links": 0.35,
    },
    "bars_pubs": {
        "booking or reservation journey": 0.65,
        "pricing information": 0.70,
        "opening-hours information": 1.00,
        "relevant local-business schema": 1.00,
        "contact information": 1.00,
    },
    "restaurants": {
        "booking or reservation journey": 0.95,
        "pricing information": 0.90,
        "opening-hours information": 1.00,
        "relevant local-business schema": 1.00,
        "contact information": 1.00,
    },
    "hair_services": {
        "booking or reservation journey": 1.00,
        "pricing information": 1.00,
        "opening-hours information": 0.95,
        "relevant local-business schema": 1.00,
        "contact information": 1.00,
    },
    "beauty_wellness": {
        "booking or reservation journey": 1.00,
        "pricing information": 0.95,
        "opening-hours information": 0.95,
        "relevant local-business schema": 1.00,
        "contact information": 1.00,
    },
    "workspaces": {
        "booking or reservation journey": 0.85,
        "pricing information": 1.00,
        "opening-hours information": 0.85,
        "relevant local-business schema": 0.90,
        "contact information": 1.00,
    },
}


ENTITY_SIGNALS = {
    "relevant local-business schema",
    "contact information",
    "address/location information",
    "opening-hours information",
}

TECHNICAL_SIGNALS = {
    "canonical url",
    "xml sitemap",
    "https",
    "homepage title",
    "meta description",
}

OFFERING_SIGNALS = {
    "service or offering coverage",
    "pricing information",
}

LOW_CONFIDENCE_SIGNALS = {
    "social-profile links",
}

BOOKING_SIGNAL = (
    "booking or reservation journey"
)


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def _safe_float(
    value: Any,
    default: float | None = None,
) -> float | None:
    if value is None:
        return default

    try:
        result = float(
            value
        )
    except (
        TypeError,
        ValueError,
    ):
        return default

    if math.isnan(
        result
    ):
        return default

    return result


def _clean_signal(
    value: Any,
) -> str:
    return re.sub(
        r"\s+",
        " ",
        str(
            value
            or ""
        ).strip().lower(),
    )


def _display_signal(
    value: Any,
) -> str:
    return re.sub(
        r"\s+",
        " ",
        str(
            value
            or ""
        ).strip(),
    )


def _strip_best_prefix(
    value: Any,
) -> str:
    text = re.sub(
        r"\s+",
        " ",
        str(
            value
            or ""
        ).strip(),
    )

    text = re.sub(
        r"^(the\s+)?best\s+",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"^(good|great|excellent)\s+",
        "",
        text,
        flags=re.IGNORECASE,
    )

    return text.strip()


def _join_human(
    items: list[str],
) -> str:
    cleaned = [
        str(
            item
        ).strip()
        for item in items
        if str(
            item
        ).strip()
    ]

    if not cleaned:
        return ""

    if len(
        cleaned
    ) == 1:
        return cleaned[0]

    if len(
        cleaned
    ) == 2:
        return (
            cleaned[0]
            + " and "
            + cleaned[1]
        )

    return (
        ", ".join(
            cleaned[:-1]
        )
        + ", and "
        + cleaned[-1]
    )


def _relevance(
    *,
    primary_group: str,
    signal: str,
) -> float:
    key = _clean_signal(
        signal
    )

    vertical = (
        VERTICAL_RELEVANCE.get(
            str(
                primary_group
                or ""
            ),
            {},
        )
    )

    if key in vertical:
        return float(
            vertical[
                key
            ]
        )

    return float(
        DEFAULT_RELEVANCE.get(
            key,
            0.60,
        )
    )


def _confidence_label(
    score: float,
) -> str:
    if score >= 0.82:
        return "High"

    if score >= 0.64:
        return "Medium"

    return "Low"


def _priority_label(
    score: float,
) -> str:
    # Reserve "High" for the strongest combination of business
    # relevance and comparative evidence. This prevents technical
    # hygiene items from becoming High priority merely because all
    # three comparison sites happen to contain them.
    if score >= 88:
        return "High"

    if score >= 62:
        return "Medium"

    return "Low"


def _website_candidate_score(
    *,
    relevance: float,
    prevalence: float,
    cohort_size: int,
    controllability: float,
    proposition_relevance: float = 0.55,
) -> tuple[
    float,
    float,
]:
    sample_strength = min(
        1.0,
        max(
            0.0,
            cohort_size
            / 3.0,
        ),
    )

    evidence_strength = (
        0.70
        * prevalence
        + 0.30
        * sample_strength
    )

    score = 100 * (
        0.34
        * relevance
        + 0.26
        * evidence_strength
        + 0.18
        * controllability
        + 0.12
        * prevalence
        + 0.10
        * proposition_relevance
    )

    confidence = (
        0.65
        * evidence_strength
        + 0.35
        * relevance
    )

    return (
        float(
            score
        ),
        float(
            confidence
        ),
    )


def _proposition_score(
    *,
    prevalence: float,
    target_pages: int,
    leader_median_pages: float,
    leader_count: int,
) -> tuple[
    float,
    float,
]:
    sample_strength = min(
        1.0,
        leader_count
        / 3.0,
    )

    median = max(
        1.0,
        float(
            leader_median_pages
            or 0
        ),
    )

    relative_gap = max(
        0.0,
        min(
            1.0,
            (
                median
                - float(
                    target_pages
                )
            )
            / median,
        ),
    )

    evidence_strength = (
        0.55
        * prevalence
        + 0.25
        * sample_strength
        + 0.20
        * relative_gap
    )

    # A stated client proposition is intrinsically high relevance and
    # highly controllable on the website.
    score = 100 * (
        0.30
        * 1.00
        + 0.28
        * evidence_strength
        + 0.22
        * 1.00
        + 0.12
        * prevalence
        + 0.08
        * relative_gap
    )

    confidence = (
        0.70
        * evidence_strength
        + 0.30
        * 1.00
    )

    return (
        float(
            score
        ),
        float(
            confidence
        ),
    )


def _review_summary(
    *,
    review_result: dict[
        str,
        Any,
    ] | None,
    target_name: str,
) -> dict[
    str,
    Any,
]:
    if not review_result:
        return {}

    summaries = review_result.get(
        "business_summaries",
        pd.DataFrame(),
    )

    if (
        summaries is None
        or summaries.empty
    ):
        return {}

    frame = summaries.copy()

    target_rows = frame[
        frame[
            "business_name"
        ].astype(str)
        == str(
            target_name
        )
    ]

    if target_rows.empty:
        return {}

    target = (
        target_rows.iloc[0]
    )

    leaders = frame[
        frame[
            "business_name"
        ].astype(str)
        != str(
            target_name
        )
    ]

    if leaders.empty:
        return {}

    target_rating = _safe_float(
        target.get(
            "sample_rating"
        )
    )

    leader_rating = _safe_float(
        pd.to_numeric(
            leaders[
                "sample_rating"
            ],
            errors="coerce",
        ).median()
    )

    target_reviews = int(
        target.get(
            "reviews_analysed"
        )
        or 0
    )

    target_negative = int(
        target.get(
            "negative_reviews"
        )
        or 0
    )

    target_negative_rate = (
        target_negative
        / target_reviews
        if target_reviews
        else None
    )

    leader_negative_rates = []

    for row in leaders.to_dict(
        "records"
    ):
        reviews = int(
            row.get(
                "reviews_analysed"
            )
            or 0
        )

        negatives = int(
            row.get(
                "negative_reviews"
            )
            or 0
        )

        if reviews:
            leader_negative_rates.append(
                negatives
                / reviews
            )

    leader_negative_rate = (
        float(
            pd.Series(
                leader_negative_rates
            ).median()
        )
        if leader_negative_rates
        else None
    )

    target_owner_responses = int(
        target.get(
            "owner_responses"
        )
        or 0
    )

    target_owner_response_rate = (
        target_owner_responses
        / target_reviews
        if target_reviews
        else None
    )

    leader_owner_rates = []

    for row in leaders.to_dict(
        "records"
    ):
        reviews = int(
            row.get(
                "reviews_analysed"
            )
            or 0
        )

        responses = int(
            row.get(
                "owner_responses"
            )
            or 0
        )

        if reviews:
            leader_owner_rates.append(
                responses
                / reviews
            )

    leader_owner_response_rate = (
        float(
            pd.Series(
                leader_owner_rates
            ).median()
        )
        if leader_owner_rates
        else None
    )

    return {
        "target_rating":
            target_rating,
        "leader_rating_median":
            leader_rating,
        "target_negative_rate":
            target_negative_rate,
        "leader_negative_rate_median":
            leader_negative_rate,
        "target_owner_response_rate":
            target_owner_response_rate,
        "leader_owner_response_rate_median":
            leader_owner_response_rate,
        "target_reviews":
            target_reviews,
        "leader_count":
            len(
                leaders
            ),
    }


def _target_visibility_rate(
    results: pd.DataFrame | None,
) -> float | None:
    if (
        results is None
        or results.empty
        or "target_recommended"
        not in results.columns
    ):
        return None

    if "response_complete" in results.columns:
        valid = results[
            results[
                "response_complete"
            ].fillna(False)
        ].copy()
    else:
        valid = results.copy()

    if valid.empty:
        return None

    recommended = (
        valid[
            "target_recommended"
        ]
        .fillna(False)
        .astype(bool)
    )

    return float(
        recommended.mean()
    )


# ---------------------------------------------------------------------
# Candidate extraction
# ---------------------------------------------------------------------

def _website_candidates(
    *,
    website_result: dict[
        str,
        Any,
    ] | None,
    primary_group: str,
) -> list[
    dict[str, Any]
]:
    if (
        not website_result
        or website_result.get(
            "error"
        )
    ):
        return []

    rows = []

    for item in website_result.get(
        "recommendations",
        [],
    ):
        signal = _display_signal(
            item.get(
                "check"
            )
        )

        signal_key = _clean_signal(
            signal
        )

        prevalence = _safe_float(
            item.get(
                "cohort_prevalence"
            ),
            0.0,
        ) or 0.0

        cohort_size = int(
            item.get(
                "cohort_size"
            )
            or 0
        )

        relevance = _relevance(
            primary_group=(
                primary_group
            ),
            signal=(
                signal
            ),
        )

        controllability = (
            1.0
            if signal_key
            not in LOW_CONFIDENCE_SIGNALS
            else 0.75
        )

        score, confidence = (
            _website_candidate_score(
                relevance=relevance,
                prevalence=prevalence,
                cohort_size=cohort_size,
                controllability=(
                    controllability
                ),
            )
        )

        if (
            relevance < 0.30
            or score < 48
        ):
            disposition = (
                "Suppress"
            )
        elif (
            signal_key
            in LOW_CONFIDENCE_SIGNALS
            or score < 64
        ):
            disposition = (
                "Observe"
            )
        else:
            disposition = (
                "Recommend"
            )

        rows.append(
            {
                "kind":
                    "website",
                "signal":
                    signal,
                "signal_key":
                    signal_key,
                "relevance":
                    relevance,
                "prevalence":
                    prevalence,
                "cohort_size":
                    cohort_size,
                "cohort_found":
                    int(
                        item.get(
                            "cohort_found"
                        )
                        or 0
                    ),
                "score":
                    score,
                "confidence_score":
                    confidence,
                "confidence":
                    _confidence_label(
                        confidence
                    ),
                "priority":
                    _priority_label(
                        score
                    ),
                "disposition":
                    disposition,
                "observation":
                    (
                        f"Not detected on target; "
                        f"detected on "
                        f"{int(item.get('cohort_found') or 0)} "
                        f"of {cohort_size} selected AI-leader "
                        f"websites ({prevalence:.0%})."
                    ),
                "action":
                    str(
                        item.get(
                            "recommendation"
                        )
                        or ""
                    ),
            }
        )

    return rows


def _proposition_candidates(
    proposition_benchmark: pd.DataFrame | None,
) -> tuple[
    list[
        dict[str, Any]
    ],
    list[
        dict[str, Any]
    ],
]:
    if (
        proposition_benchmark
        is None
        or proposition_benchmark.empty
    ):
        return (
            [],
            [],
        )

    opportunities = []
    strengths = []

    for row in (
        proposition_benchmark
        .to_dict(
            "records"
        )
    ):
        proposition = _display_signal(
            row.get(
                "proposition"
            )
        )

        target_pages = int(
            row.get(
                "target_pages"
            )
            or 0
        )

        leader_count = int(
            row.get(
                "leader_count"
            )
            or 0
        )

        leaders_with_coverage = int(
            row.get(
                "leaders_with_coverage"
            )
            or 0
        )

        prevalence = _safe_float(
            row.get(
                "leader_prevalence"
            ),
            0.0,
        ) or 0.0

        median_pages = _safe_float(
            row.get(
                "leader_median_pages"
            ),
            0.0,
        ) or 0.0

        if (
            target_pages > 0
            and median_pages > 0
            and target_pages
            >= median_pages
        ):
            strengths.append(
                {
                    "category":
                        "Website proposition coverage",
                    "title":
                        (
                            f"Strong existing coverage for "
                            f"{_strip_best_prefix(proposition)}"
                        ),
                    "evidence":
                        (
                            f"Detected across {target_pages} "
                            f"target page(s) versus an "
                            f"AI-leader median of "
                            f"{median_pages:g}."
                        ),
                    "implication":
                        (
                            "Do not prescribe generic additional "
                            "content for this proposition solely "
                            "because AI visibility is weak; the "
                            "current website signal is already "
                            "at least in line with the selected "
                            "AI leaders."
                        ),
                    "confidence":
                        (
                            "High"
                            if (
                                leader_count >= 3
                                and prevalence
                                >= 0.67
                            )
                            else "Medium"
                        ),
                }
            )
            continue

        # Treat "Some coverage" as actionable when the target is
        # materially behind the leader median. This is important for
        # cases such as 1 target page vs 8 leader-median pages.
        materially_behind = (
            median_pages >= 2
            and target_pages
            < (
                0.60
                * median_pages
            )
        )

        if (
            prevalence < 0.50
            or (
                target_pages > 0
                and not materially_behind
            )
        ):
            continue

        score, confidence = (
            _proposition_score(
                prevalence=prevalence,
                target_pages=(
                    target_pages
                ),
                leader_median_pages=(
                    median_pages
                ),
                leader_count=(
                    leader_count
                ),
            )
        )

        opportunities.append(
            {
                "kind":
                    "proposition",
                "signal":
                    proposition,
                "clean_proposition":
                    _strip_best_prefix(
                        proposition
                    ),
                "score":
                    score,
                "confidence_score":
                    confidence,
                "confidence":
                    _confidence_label(
                        confidence
                    ),
                "priority":
                    _priority_label(
                        score
                    ),
                "disposition":
                    "Recommend",
                "prevalence":
                    prevalence,
                "leader_count":
                    leader_count,
                "leaders_with_coverage":
                    leaders_with_coverage,
                "target_pages":
                    target_pages,
                "leader_median_pages":
                    median_pages,
                "observation":
                    (
                        f"Target has relevant coverage on "
                        f"{target_pages} audited page(s) versus "
                        f"an AI-leader median of "
                        f"{median_pages:g}; "
                        f"{leaders_with_coverage} of "
                        f"{leader_count} leaders show coverage "
                        f"({prevalence:.0%})."
                    ),
                "action":
                    (
                        "If this proposition is commercially "
                        "true and important, strengthen its "
                        "crawlable website coverage through "
                        "relevant category/range pages, product "
                        "content, headings and supporting detail."
                    ),
            }
        )

    return (
        opportunities,
        strengths,
    )


def _review_strengths_and_observations(
    *,
    review_result: dict[
        str,
        Any,
    ] | None,
    target_name: str,
) -> tuple[
    list[
        dict[str, Any]
    ],
    list[
        dict[str, Any]
    ],
]:
    strengths = []
    observations = []

    summary = _review_summary(
        review_result=(
            review_result
        ),
        target_name=(
            target_name
        ),
    )

    if summary:
        target_rating = (
            summary.get(
                "target_rating"
            )
        )

        leader_rating = (
            summary.get(
                "leader_rating_median"
            )
        )

        if (
            target_rating is not None
            and leader_rating is not None
            and target_rating
            >= leader_rating
            + 0.15
        ):
            strengths.append(
                {
                    "category":
                        "Customer evidence",
                    "title":
                        "Strong customer satisfaction",
                    "evidence":
                        (
                            f"Target sample rating "
                            f"{target_rating:.2f} versus an "
                            f"AI-leader median of "
                            f"{leader_rating:.2f}."
                        ),
                    "implication":
                        (
                            "Poor AI visibility should not be "
                            "explained simply as a customer-"
                            "satisfaction problem. The target "
                            "already performs strongly on this "
                            "sample."
                        ),
                    "confidence":
                        "High",
                }
            )

        target_negative = (
            summary.get(
                "target_negative_rate"
            )
        )

        leader_negative = (
            summary.get(
                "leader_negative_rate_median"
            )
        )

        if (
            target_negative is not None
            and leader_negative is not None
            and target_negative
            <= leader_negative
            - 0.03
        ):
            strengths.append(
                {
                    "category":
                        "Customer evidence",
                    "title":
                        "Relatively low negative-review rate",
                    "evidence":
                        (
                            f"{target_negative:.0%} of target "
                            f"reviews are 1–2 star versus an "
                            f"AI-leader median of "
                            f"{leader_negative:.0%}."
                        ),
                    "implication":
                        (
                            "The review sample does not suggest "
                            "that poor customer experience is "
                            "the obvious explanation for the "
                            "visibility gap."
                        ),
                    "confidence":
                        "Medium",
                }
            )

        target_owner = (
            summary.get(
                "target_owner_response_rate"
            )
        )

        leader_owner = (
            summary.get(
                "leader_owner_response_rate_median"
            )
        )

        if (
            target_owner is not None
            and leader_owner is not None
            and target_owner
            >= leader_owner
            + 0.20
        ):
            observations.append(
                {
                    "category":
                        "Customer evidence",
                    "title":
                        "Target responds to reviews more actively",
                    "evidence":
                        (
                            f"Owner responses cover about "
                            f"{target_owner:.0%} of the target "
                            f"sample versus an AI-leader median "
                            f"of {leader_owner:.0%}."
                        ),
                    "interpretation":
                        (
                            "This is a positive operating signal, "
                            "but current evidence is insufficient "
                            "to treat owner-response activity as "
                            "a priority AI-discoverability lever."
                        ),
                    "confidence":
                        "Low",
                }
            )

    if (
        review_result
        and isinstance(
            review_result,
            dict,
        )
    ):
        benchmark = review_result.get(
            "benchmark",
            pd.DataFrame(),
        )

        if (
            benchmark is not None
            and not benchmark.empty
        ):
            for row in benchmark.to_dict(
                "records"
            ):
                position = str(
                    row.get(
                        "position"
                    )
                    or ""
                )

                target_pct = _safe_float(
                    row.get(
                        "target_pct"
                    ),
                    0.0,
                ) or 0.0

                median = _safe_float(
                    row.get(
                        "cohort_median_pct"
                    )
                )

                theme = _display_signal(
                    row.get(
                        "theme_label"
                    )
                )

                if median is None:
                    continue

                delta = (
                    target_pct
                    - median
                )

                if (
                    position
                    == "Target association"
                    and delta >= 0.08
                ):
                    strengths.append(
                        {
                            "category":
                                "Customer association",
                            "title":
                                f"Strong customer association: {theme}",
                            "evidence":
                                (
                                    f"Target association "
                                    f"{target_pct:.0%} versus "
                                    f"AI-leader median "
                                    f"{median:.0%}."
                                ),
                            "implication":
                                (
                                    "This is an existing customer "
                                    "strength to protect and, where "
                                    "commercially relevant, ensure "
                                    "is represented clearly online."
                                ),
                            "confidence":
                                (
                                    "High"
                                    if delta >= 0.15
                                    else "Medium"
                                ),
                        }
                    )

                elif (
                    position
                    == "Competitor association"
                    and median >= 0.10
                    and delta <= -0.10
                ):
                    observations.append(
                        {
                            "category":
                                "Customer association",
                            "title":
                                f"Weaker customer association: {theme}",
                            "evidence":
                                (
                                    f"Target association "
                                    f"{target_pct:.0%} versus "
                                    f"AI-leader median "
                                    f"{median:.0%}."
                                ),
                            "interpretation":
                                (
                                    "This may represent a genuine "
                                    "market-perception difference, "
                                    "not merely a website problem. "
                                    "Before creating content, confirm "
                                    "that this is a proposition the "
                                    "business genuinely wants and has "
                                    "a right to claim."
                                ),
                            "confidence":
                                (
                                    "Medium"
                                    if (
                                        median >= 0.15
                                        and delta <= -0.15
                                    )
                                    else "Low"
                                ),
                        }
                    )

    return (
        strengths,
        observations,
    )


# ---------------------------------------------------------------------
# Action grouping
# ---------------------------------------------------------------------

def _entity_action(
    candidates: list[
        dict[str, Any]
    ],
    *,
    primary_group: str,
) -> dict[
    str,
    Any
]:
    present = {
        row[
            "signal_key"
        ]: row
        for row in candidates
    }

    ordered_keys = [
        "relevant local-business schema",
        "contact information",
        "address/location information",
        "opening-hours information",
    ]

    evidence_parts = []

    for key in ordered_keys:
        row = present.get(
            key
        )

        if not row:
            continue

        evidence_parts.append(
            (
                f"{row['signal']} "
                f"({row['cohort_found']}/"
                f"{row['cohort_size']} AI leaders)"
            )
        )

    score = max(
        row[
            "score"
        ]
        for row in candidates
    )

    confidence_score = sum(
        row[
            "confidence_score"
        ]
        for row in candidates
    ) / len(
        candidates
    )

    return {
        "priority":
            _priority_label(
                score
            ),
        "score":
            round(
                score,
                1,
            ),
        "title":
            "Strengthen machine-readable local entity information",
        "why":
            (
                "The target exposes less explicit machine-readable "
                "and crawlable business information than the "
                "selected AI leaders."
            ),
        "evidence":
            (
                "Missing or weaker signals: "
                + _join_human(
                    evidence_parts
                )
                + "."
            ),
        "action":
            (
                "Implement the most appropriate specific Schema.org "
                "LocalBusiness subtype for this business where "
                "technically valid, and make the business name, "
                "contact details, address, opening hours and location "
                "information explicit in crawlable HTML. Keep those "
                "details consistent with the Google Business Profile."
            ),
        "confidence":
            _confidence_label(
                confidence_score
            ),
        "evidence_layer":
            "Website / entity clarity",
    }


def _proposition_action(
    candidates: list[
        dict[str, Any]
    ],
) -> dict[
    str,
    Any
]:
    names = [
        row[
            "clean_proposition"
        ]
        for row in candidates
    ]

    evidence = []

    for row in candidates:
        evidence.append(
            (
                f"{row['clean_proposition']}: "
                f"{row['target_pages']} target page(s) "
                f"vs leader median "
                f"{row['leader_median_pages']:g}"
            )
        )

    score = max(
        row[
            "score"
        ]
        for row in candidates
    )

    confidence_score = sum(
        row[
            "confidence_score"
        ]
        for row in candidates
    ) / len(
        candidates
    )

    return {
        "priority":
            _priority_label(
                score
            ),
        "score":
            round(
                score,
                1,
            ),
        "title":
            (
                "Deepen crawlable content for "
                + _join_human(
                    names
                )
            ),
        "why":
            (
                "These are stated client propositions, but the "
                "target's audited website coverage is materially "
                "thinner than the selected AI leaders."
            ),
        "evidence":
            (
                _join_human(
                    evidence
                )
                + "."
            ),
        "action":
            (
                "Create or strengthen useful category/range pages "
                "and supporting product content. Use natural "
                "headings, descriptive copy, product/range detail "
                "and internally linked pages rather than simply "
                "repeating keywords."
            ),
        "confidence":
            _confidence_label(
                confidence_score
            ),
        "evidence_layer":
            "Website / proposition coverage",
    }


def _offering_action(
    candidates: list[
        dict[str, Any]
    ],
) -> dict[
    str,
    Any
]:
    signals = [
        row[
            "signal"
        ]
        for row in candidates
    ]

    score = max(
        row[
            "score"
        ]
        for row in candidates
    )

    confidence_score = sum(
        row[
            "confidence_score"
        ]
        for row in candidates
    ) / len(
        candidates
    )

    return {
        "priority":
            _priority_label(
                score
            ),
        "score":
            round(
                score,
                1,
            ),
        "title":
            "Make products, services and practical buying information clearer",
        "why":
            (
                "Selected AI leaders expose practical offering "
                "information more consistently than the target."
            ),
        "evidence":
            (
                "Relevant gaps include "
                + _join_human(
                    signals
                )
                + "."
            ),
        "action":
            (
                "Ensure products/ranges, indicative pricing where "
                "appropriate, menus or service details are available "
                "as crawlable website content rather than being "
                "hidden only in images, social posts or third-party "
                "systems."
            ),
        "confidence":
            _confidence_label(
                confidence_score
            ),
        "evidence_layer":
            "Website / offering clarity",
    }


def _technical_action(
    candidates: list[
        dict[str, Any]
    ],
) -> dict[
    str,
    Any
]:
    signals = [
        row[
            "signal"
        ]
        for row in candidates
    ]

    score = max(
        row[
            "score"
        ]
        for row in candidates
    )

    confidence_score = sum(
        row[
            "confidence_score"
        ]
        for row in candidates
    ) / len(
        candidates
    )

    return {
        "priority":
            _priority_label(
                score
            ),
        "score":
            round(
                score,
                1,
            ),
        "title":
            "Tighten technical discoverability hygiene",
        "why":
            (
                "The target is missing technical signals that "
                "are consistently present across the selected "
                "AI-leader websites."
            ),
        "evidence":
            (
                "Relevant gaps include "
                + _join_human(
                    signals
                )
                + "."
            ),
        "action":
            (
                "Fix the identified technical items using normal "
                "web/SEO best practice. These are supporting "
                "discoverability signals rather than standalone "
                "claims about AI ranking."
            ),
        "confidence":
            _confidence_label(
                confidence_score
            ),
        "evidence_layer":
            "Website / technical foundation",
    }


def _single_action(
    row: dict[
        str,
        Any
    ],
) -> dict[
    str,
    Any
]:
    return {
        "priority":
            row[
                "priority"
            ],
        "score":
            round(
                row[
                    "score"
                ],
                1,
            ),
        "title":
            row[
                "signal"
            ],
        "why":
            row[
                "observation"
            ],
        "evidence":
            row[
                "observation"
            ],
        "action":
            row[
                "action"
            ],
        "confidence":
            row[
                "confidence"
            ],
        "evidence_layer":
            "Website",
    }


# ---------------------------------------------------------------------
# Public synthesis
# ---------------------------------------------------------------------

def build_recommendation_synthesis(
    *,
    primary_group: str,
    target_name: str,
    website_result: dict[
        str,
        Any,
    ] | None,
    proposition_benchmark:
        pd.DataFrame | None,
    review_result: dict[
        str,
        Any,
    ] | None,
    results: pd.DataFrame | None = None,
    max_actions: int = 6,
) -> dict[str, Any]:
    website = _website_candidates(
        website_result=(
            website_result
        ),
        primary_group=(
            primary_group
        ),
    )

    proposition_opportunities, (
        proposition_strengths
    ) = _proposition_candidates(
        proposition_benchmark
    )

    review_strengths, (
        review_observations
    ) = (
        _review_strengths_and_observations(
            review_result=(
                review_result
            ),
            target_name=(
                target_name
            ),
        )
    )

    recommended_website = [
        row
        for row in website
        if row[
            "disposition"
        ]
        == "Recommend"
    ]

    observed_website = [
        row
        for row in website
        if row[
            "disposition"
        ]
        == "Observe"
    ]

    suppressed_website = [
        row
        for row in website
        if row[
            "disposition"
        ]
        == "Suppress"
    ]

    actions = []

    entity_rows = [
        row
        for row in recommended_website
        if row[
            "signal_key"
        ]
        in ENTITY_SIGNALS
    ]

    if entity_rows:
        actions.append(
            _entity_action(
                entity_rows,
                primary_group=(
                    primary_group
                ),
            )
        )

    if proposition_opportunities:
        actions.append(
            _proposition_action(
                proposition_opportunities
            )
        )

    offering_rows = [
        row
        for row in recommended_website
        if row[
            "signal_key"
        ]
        in OFFERING_SIGNALS
    ]

    if offering_rows:
        actions.append(
            _offering_action(
                offering_rows
            )
        )

    technical_rows = [
        row
        for row in recommended_website
        if row[
            "signal_key"
        ]
        in TECHNICAL_SIGNALS
    ]

    if technical_rows:
        actions.append(
            _technical_action(
                technical_rows
            )
        )

    already_grouped = (
        ENTITY_SIGNALS
        | OFFERING_SIGNALS
        | TECHNICAL_SIGNALS
    )

    for row in recommended_website:
        if row[
            "signal_key"
        ] in already_grouped:
            continue

        actions.append(
            _single_action(
                row
            )
        )

    actions = sorted(
        actions,
        key=lambda row: (
            -float(
                row[
                    "score"
                ]
            ),
            row[
                "title"
            ],
        ),
    )[
        :max(
            1,
            int(
                max_actions
            ),
        )
    ]

    # Existing website strengths.
    strengths = list(
        proposition_strengths
    )

    if (
        website_result
        and not website_result.get(
            "error"
        )
    ):
        target_score = _safe_float(
            website_result.get(
                "target_score"
            )
        )

        cohort_median = _safe_float(
            website_result.get(
                "cohort_median"
            )
        )

        if (
            target_score is not None
            and cohort_median is not None
            and target_score
            >= cohort_median
        ):
            strengths.append(
                {
                    "category":
                        "Website",
                    "title":
                        "Overall website completeness is competitive",
                    "evidence":
                        (
                            f"Target score {target_score:.0f}/100 "
                            f"versus AI-leader median "
                            f"{cohort_median:.0f}/100."
                        ),
                    "implication":
                        (
                            "The opportunity is likely to be more "
                            "specific than a wholesale website rebuild."
                        ),
                    "confidence":
                        "High",
                }
            )

    strengths.extend(
        review_strengths
    )

    observations = list(
        review_observations
    )

    for row in observed_website:
        observations.append(
            {
                "category":
                    "Website",
                "title":
                    row[
                        "signal"
                    ],
                "evidence":
                    row[
                        "observation"
                    ],
                "interpretation":
                    (
                        "This is an observable difference, but "
                        "business relevance and/or current evidence "
                        "is not strong enough to make it a priority "
                        "recommendation."
                    ),
                "confidence":
                    row[
                        "confidence"
                    ],
            }
        )

    for row in suppressed_website:
        observations.append(
            {
                "category":
                    "Suppressed difference",
                "title":
                    row[
                        "signal"
                    ],
                "evidence":
                    row[
                        "observation"
                    ],
                "interpretation":
                    (
                        "Detected competitor difference, but "
                        "suppressed from the action plan because it "
                        "is not sufficiently relevant to this "
                        "business vertical."
                    ),
                "confidence":
                    row[
                        "confidence"
                    ],
            }
        )

    visibility_rate = (
        _target_visibility_rate(
            results
        )
    )

    review_summary = (
        _review_summary(
            review_result=(
                review_result
            ),
            target_name=(
                target_name
            ),
        )
    )

    website_score = (
        _safe_float(
            website_result.get(
                "target_score"
            )
        )
        if website_result
        else None
    )

    leader_website_median = (
        _safe_float(
            website_result.get(
                "cohort_median"
            )
        )
        if website_result
        else None
    )

    headline = (
        "The diagnostic has identified specific, "
        "client-controllable website opportunities."
        if actions
        else (
            "The current evidence does not identify a strong "
            "client-controllable website gap."
        )
    )

    strategic_insight = None

    if (
        visibility_rate is not None
        and visibility_rate <= 0.05
        and review_summary
    ):
        target_rating = (
            review_summary.get(
                "target_rating"
            )
        )

        leader_rating = (
            review_summary.get(
                "leader_rating_median"
            )
        )

        if (
            target_rating is not None
            and leader_rating is not None
            and target_rating >= leader_rating
        ):
            strategic_insight = (
                "Customer satisfaction appears stronger than "
                "AI visibility. The current evidence therefore "
                "supports focusing first on how clearly the "
                "business and its propositions are represented "
                "online, rather than assuming poor customer "
                "experience is the primary problem."
            )

    action_frame = pd.DataFrame(
        actions,
        columns=[
            "priority",
            "score",
            "title",
            "why",
            "evidence",
            "action",
            "confidence",
            "evidence_layer",
        ],
    )

    strength_frame = pd.DataFrame(
        strengths,
        columns=[
            "category",
            "title",
            "evidence",
            "implication",
            "confidence",
        ],
    )

    observation_frame = pd.DataFrame(
        observations,
        columns=[
            "category",
            "title",
            "evidence",
            "interpretation",
            "confidence",
        ],
    )

    technical_evidence = pd.DataFrame(
        website,
        columns=[
            "signal",
            "relevance",
            "prevalence",
            "score",
            "confidence",
            "priority",
            "disposition",
            "observation",
            "action",
        ],
    )

    return {
        "headline":
            headline,
        "strategic_insight":
            strategic_insight,
        "visibility_rate":
            visibility_rate,
        "website_score":
            website_score,
        "leader_website_median":
            leader_website_median,
        "review_summary":
            review_summary,
        "actions":
            action_frame,
        "strengths":
            strength_frame,
        "observations":
            observation_frame,
        "technical_evidence":
            technical_evidence,
    }
