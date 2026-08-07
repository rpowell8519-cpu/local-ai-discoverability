from __future__ import annotations

import json
import math
import re
from typing import Any

import pandas as pd


def jsonish(
    value: Any,
    default: Any,
) -> Any:
    if isinstance(
        value,
        (
            list,
            dict,
        ),
    ):
        return value

    if value is None:
        return default

    if isinstance(
        value,
        float,
    ) and math.isnan(value):
        return default

    if isinstance(
        value,
        str,
    ):
        cleaned = value.strip()

        if not cleaned:
            return default

        try:
            return json.loads(
                cleaned
            )
        except (
            json.JSONDecodeError,
            TypeError,
        ):
            return default

    return default


def combined_page_text(
    page: dict[str, Any],
) -> str:
    headings = jsonish(
        page.get(
            "headings"
        ),
        [],
    )

    values = [
        page.get(
            "page_title"
        ),
        page.get(
            "meta_description"
        ),
        " ".join(
            str(item)
            for item in headings
        ),
        page.get(
            "text_excerpt"
        ),
    ]

    return re.sub(
        r"\s+",
        " ",
        " ".join(
            str(value or "")
            for value in values
        ).lower(),
    ).strip()


def _term_variants(
    proposition: str,
) -> list[str]:
    text = re.sub(
        r"[^a-z0-9\s-]+",
        " ",
        str(
            proposition
            or ""
        ).lower(),
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    stop_prefixes = [
        "best ",
        "good ",
        "great ",
        "excellent ",
        "a good ",
        "the best ",
        "really good ",
    ]

    changed = True

    while changed:
        changed = False

        for prefix in (
            stop_prefixes
        ):
            if text.startswith(
                prefix
            ):
                text = text[
                    len(prefix):
                ].strip()
                changed = True

    variants = []

    if text:
        variants.append(text)

    words = text.split()

    if len(words) == 1:
        word = words[0]

        if word.endswith(
            "ies"
        ) and len(word) > 4:
            variants.append(
                word[:-3]
                + "y"
            )
        elif (
            word.endswith("s")
            and len(word) > 3
        ):
            variants.append(
                word[:-1]
            )
        else:
            variants.append(
                word + "s"
            )

    # Useful bakery/café synonym families. These are only content
    # coverage helpers, not semantic claims.
    synonym_map = {
        "pastry": [
            "pastry",
            "pastries",
            "croissant",
            "croissants",
            "viennoiserie",
        ],
        "pastries": [
            "pastry",
            "pastries",
            "croissant",
            "croissants",
            "viennoiserie",
        ],
        "cake": [
            "cake",
            "cakes",
            "bakes",
        ],
        "cakes": [
            "cake",
            "cakes",
            "bakes",
        ],
        "coffee": [
            "coffee",
            "espresso",
            "flat white",
            "cappuccino",
            "latte",
        ],
        "sourdough": [
            "sourdough",
            "artisan bread",
            "bread",
        ],
    }

    for variant in list(
        variants
    ):
        variants.extend(
            synonym_map.get(
                variant,
                [],
            )
        )

    return [
        item
        for item in dict.fromkeys(
            variants
        )
        if len(item) >= 3
    ]


def build_proposition_coverage(
    *,
    propositions: list[str],
    pages_by_place: dict[
        str,
        pd.DataFrame,
    ],
    business_names: dict[
        str,
        str,
    ],
) -> pd.DataFrame:
    rows = []

    for proposition in (
        propositions
    ):
        variants = (
            _term_variants(
                proposition
            )
        )

        for place_id, pages in (
            pages_by_place.items()
        ):
            matching_pages = []
            total_occurrences = 0

            if (
                pages is not None
                and not pages.empty
            ):
                for page in pages.to_dict(
                    "records"
                ):
                    page_text = (
                        combined_page_text(
                            page
                        )
                    )

                    occurrences = sum(
                        page_text.count(
                            variant
                        )
                        for variant
                        in variants
                    )

                    if occurrences > 0:
                        total_occurrences += (
                            occurrences
                        )

                        label = str(
                            page.get(
                                "page_title"
                            )
                            or page.get(
                                "final_url"
                            )
                            or page.get(
                                "url"
                            )
                            or "Audited page"
                        )

                        matching_pages.append(
                            label
                        )

            rows.append(
                {
                    "google_place_id":
                        str(
                            place_id
                        ),
                    "business_name":
                        business_names.get(
                            str(
                                place_id
                            ),
                            str(
                                place_id
                            ),
                        ),
                    "proposition":
                        proposition,
                    "term_variants":
                        variants,
                    "pages_mentioning":
                        len(
                            matching_pages
                        ),
                    "total_mentions":
                        int(
                            total_occurrences
                        ),
                    "evidence_pages":
                        matching_pages[:5],
                }
            )

    return pd.DataFrame(
        rows
    )


def build_proposition_benchmark(
    *,
    coverage: pd.DataFrame,
    target_google_place_id: str,
) -> pd.DataFrame:
    if coverage.empty:
        return pd.DataFrame()

    rows = []

    for proposition, frame in (
        coverage.groupby(
            "proposition",
            dropna=False,
        )
    ):
        target_rows = frame[
            frame[
                "google_place_id"
            ].astype(str)
            == str(
                target_google_place_id
            )
        ]

        competitors = frame[
            frame[
                "google_place_id"
            ].astype(str)
            != str(
                target_google_place_id
            )
        ]

        if target_rows.empty:
            target_pages = 0
            target_mentions = 0
            target_evidence = []
        else:
            target_row = (
                target_rows.iloc[0]
            )
            target_pages = int(
                target_row[
                    "pages_mentioning"
                ]
            )
            target_mentions = int(
                target_row[
                    "total_mentions"
                ]
            )
            target_evidence = (
                target_row[
                    "evidence_pages"
                ]
            )

        competitor_pages = (
            pd.to_numeric(
                competitors[
                    "pages_mentioning"
                ],
                errors="coerce",
            )
            .fillna(0)
            if not competitors.empty
            else pd.Series(
                dtype=float
            )
        )

        leaders_with_coverage = int(
            (
                competitor_pages > 0
            ).sum()
        )

        competitor_count = len(
            competitors
        )

        prevalence = (
            leaders_with_coverage
            / competitor_count
            if competitor_count
            else None
        )

        median_pages = (
            float(
                competitor_pages.median()
            )
            if competitor_count
            else None
        )

        if (
            target_pages == 0
            and prevalence is not None
            and prevalence >= 0.50
        ):
            position = (
                "Content gap"
            )
        elif (
            target_pages > 0
            and median_pages is not None
            and target_pages
            >= median_pages
        ):
            position = (
                "In line / strength"
            )
        elif target_pages > 0:
            position = (
                "Some coverage"
            )
        else:
            position = (
                "Low-signal gap"
            )

        rows.append(
            {
                "proposition":
                    proposition,
                "target_pages":
                    target_pages,
                "target_mentions":
                    target_mentions,
                "target_evidence":
                    target_evidence,
                "leaders_with_coverage":
                    leaders_with_coverage,
                "leader_count":
                    competitor_count,
                "leader_prevalence":
                    prevalence,
                "leader_median_pages":
                    median_pages,
                "position":
                    position,
            }
        )

    return pd.DataFrame(
        rows
    )


def build_review_observations(
    benchmark: pd.DataFrame,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    opportunities = []
    strengths = []

    if benchmark.empty:
        return (
            opportunities,
            strengths,
        )

    for row in benchmark.to_dict(
        "records"
    ):
        position = str(
            row.get(
                "position"
            )
            or ""
        )

        target_pct = float(
            row.get(
                "target_pct"
            )
            or 0
        )

        median = row.get(
            "cohort_median_pct"
        )

        if (
            median is None
            or (
                isinstance(
                    median,
                    float,
                )
                and math.isnan(
                    median
                )
            )
        ):
            continue

        median = float(
            median
        )

        delta = (
            target_pct
            - median
        )

        if position == (
            "Competitor association"
        ):
            if (
                median >= 0.15
                and delta <= -0.15
            ):
                priority = "High"
            elif median >= 0.08:
                priority = "Medium"
            else:
                priority = "Low"

            opportunities.append(
                {
                    "layer":
                        "Customer reviews",
                    "priority":
                        priority,
                    "signal":
                        row.get(
                            "theme_label"
                        ),
                    "observation": (
                        f"Target review association "
                        f"{target_pct:.0%} vs "
                        f"AI-leader median "
                        f"{median:.0%}."
                    ),
                    "suggested_action": (
                        "First establish whether this is "
                        "a genuine customer proposition. "
                        "If it is, ensure the website "
                        "describes it clearly using "
                        "natural, crawlable language."
                    ),
                }
            )

        elif position == (
            "Target association"
        ):
            strengths.append(
                {
                    "layer":
                        "Customer reviews",
                    "signal":
                        row.get(
                            "theme_label"
                        ),
                    "observation": (
                        f"Target association "
                        f"{target_pct:.0%} vs "
                        f"AI-leader median "
                        f"{median:.0%}."
                    ),
                }
            )

    return (
        opportunities,
        strengths,
    )


def build_combined_observations(
    *,
    website_result: dict[
        str,
        Any,
    ] | None,
    proposition_benchmark:
        pd.DataFrame,
    review_result: dict[
        str,
        Any,
    ] | None,
) -> dict[str, pd.DataFrame]:
    opportunity_rows = []
    strength_rows = []

    if (
        website_result
        and not website_result.get(
            "error"
        )
    ):
        for item in (
            website_result.get(
                "recommendations",
                [],
            )
        ):
            prevalence = item.get(
                "cohort_prevalence"
            )

            opportunity_rows.append(
                {
                    "layer":
                        "Website",
                    "priority":
                        item.get(
                            "priority",
                            "Medium",
                        ),
                    "signal":
                        item.get(
                            "check"
                        ),
                    "observation": (
                        f"Not detected on target; "
                        f"detected on "
                        f"{item.get('cohort_found', 0)} "
                        f"of "
                        f"{item.get('cohort_size', 0)} "
                        f"selected AI-leader websites"
                        + (
                            f" ({float(prevalence):.0%})."
                            if prevalence
                            is not None
                            else "."
                        )
                    ),
                    "suggested_action":
                        item.get(
                            "recommendation"
                        ),
                }
            )

        for item in (
            website_result.get(
                "strengths",
                [],
            )
        ):
            prevalence = item.get(
                "cohort_prevalence"
            )

            strength_rows.append(
                {
                    "layer":
                        "Website",
                    "signal":
                        item.get(
                            "check"
                        ),
                    "observation": (
                        str(
                            item.get(
                                "position"
                            )
                            or "Detected"
                        )
                        + (
                            f"; AI-leader prevalence "
                            f"{float(prevalence):.0%}."
                            if prevalence
                            is not None
                            else "."
                        )
                    ),
                }
            )

    if (
        proposition_benchmark
        is not None
        and not proposition_benchmark.empty
    ):
        for row in (
            proposition_benchmark
            .to_dict(
                "records"
            )
        ):
            prevalence = row.get(
                "leader_prevalence"
            )

            if row.get(
                "position"
            ) == "Content gap":
                opportunity_rows.append(
                    {
                        "layer":
                            "Website proposition coverage",
                        "priority":
                            (
                                "High"
                                if (
                                    prevalence
                                    is not None
                                    and prevalence
                                    >= 0.75
                                )
                                else "Medium"
                            ),
                        "signal":
                            row.get(
                                "proposition"
                            ),
                        "observation": (
                            "No audited target page "
                            "mentions this proposition "
                            f"while "
                            f"{row.get('leaders_with_coverage', 0)} "
                            f"of "
                            f"{row.get('leader_count', 0)} "
                            "selected AI leaders do."
                        ),
                        "suggested_action": (
                            "If this proposition is "
                            "commercially true and important, "
                            "strengthen its crawlable website "
                            "coverage through relevant page "
                            "copy, headings, menus/products "
                            "and supporting detail."
                        ),
                    }
                )

            elif row.get(
                "position"
            ) == "In line / strength":
                strength_rows.append(
                    {
                        "layer":
                            "Website proposition coverage",
                        "signal":
                            row.get(
                                "proposition"
                            ),
                        "observation": (
                            f"Detected across "
                            f"{row.get('target_pages', 0)} "
                            "audited target page(s), "
                            "at least in line with the "
                            "selected AI leaders."
                        ),
                    }
                )

    if (
        review_result
        and isinstance(
            review_result,
            dict,
        )
    ):
        review_opportunities, (
            review_strengths
        ) = (
            build_review_observations(
                review_result.get(
                    "benchmark",
                    pd.DataFrame(),
                )
            )
        )

        opportunity_rows.extend(
            review_opportunities
        )
        strength_rows.extend(
            review_strengths
        )

    priority_order = {
        "High": 0,
        "Medium": 1,
        "Low": 2,
    }

    opportunities = (
        pd.DataFrame(
            opportunity_rows
        )
    )

    if not opportunities.empty:
        opportunities[
            "_priority"
        ] = opportunities[
            "priority"
        ].map(
            priority_order
        ).fillna(9)

        opportunities = (
            opportunities.sort_values(
                [
                    "_priority",
                    "layer",
                    "signal",
                ]
            )
            .drop(
                columns=[
                    "_priority"
                ]
            )
            .reset_index(
                drop=True
            )
        )

    strengths = pd.DataFrame(
        strength_rows
    )

    return {
        "opportunities":
            opportunities,
        "strengths":
            strengths,
    }
