from __future__ import annotations

import json
import math
from typing import Any

import pandas as pd


USABLE_AUDIT_STATUSES = {
    "completed",
    "partial",
    "no_website",
}


def is_missing(value: Any) -> bool:
    if value is None:
        return True

    if isinstance(value, float):
        return math.isnan(value)

    return False


def parse_jsonish(
    value: Any,
    default: Any,
) -> Any:
    if isinstance(value, (dict, list)):
        return value

    if is_missing(value):
        return default

    if isinstance(value, str):
        cleaned = value.strip()

        if not cleaned:
            return default

        try:
            return json.loads(cleaned)
        except (json.JSONDecodeError, TypeError):
            return default

    return default


def to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        return value.strip().lower() in {
            "true",
            "yes",
            "1",
        }

    if is_missing(value):
        return False

    return bool(value)


def clean_url(value: Any) -> str:
    if is_missing(value):
        return ""

    return str(value).strip()


def page_label(page: dict[str, Any]) -> str:
    title = str(
        page.get("page_title")
        or ""
    ).strip()

    url = clean_url(
        page.get("final_url")
        or page.get("url")
    )

    if title and url:
        return f"{title} — {url}"

    return title or url or "Audited page"


def normalise_pages(
    pages: pd.DataFrame | list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    if pages is None:
        return []

    if isinstance(pages, pd.DataFrame):
        if pages.empty:
            return []

        records = pages.to_dict("records")
    else:
        records = list(pages)

    output = []

    for record in records:
        page = dict(record)

        page["headings"] = parse_jsonish(
            page.get("headings"),
            [],
        )
        page["schema_types"] = parse_jsonish(
            page.get("schema_types"),
            [],
        )
        page["detected_signals"] = parse_jsonish(
            page.get("detected_signals"),
            {},
        )
        page["issues"] = parse_jsonish(
            page.get("issues"),
            [],
        )

        output.append(page)

    return output


def combined_page_text(
    page: dict[str, Any],
) -> str:
    headings = " ".join(
        str(item)
        for item in page.get(
            "headings",
            [],
        )
    )

    values = [
        page.get("page_title"),
        page.get("meta_description"),
        headings,
        page.get("text_excerpt"),
    ]

    return " ".join(
        str(value or "")
        for value in values
    ).lower()


def evaluate_check(
    audit: dict[str, Any],
    pages: pd.DataFrame | list[dict[str, Any]] | None,
    check: dict[str, Any],
) -> dict[str, Any]:
    status = str(
        audit.get("audit_status")
        or ""
    )

    if status not in USABLE_AUDIT_STATUSES:
        return {
            "found": None,
            "evidence": [
                (
                    "Audit unavailable: "
                    + (
                        status
                        or "no completed audit"
                    )
                )
            ],
        }

    if status == "no_website":
        return {
            "found": False,
            "evidence": [
                "No website URL was available."
            ],
        }

    normalised_pages = normalise_pages(
        pages
    )

    evidence: list[str] = []
    found = False

    run_field = check.get("run_field")

    if run_field and to_bool(
        audit.get(run_field)
    ):
        found = True
        evidence.append(
            f"Audit detected: {check['label']}."
        )

    value_field = check.get("value_field")

    if value_field:
        value = audit.get(value_field)

        if not is_missing(value) and bool(
            str(value).strip()
        ):
            found = True
            evidence.append(
                f"Audit value: {value}."
            )

    configured_schema_types = {
        str(item)
        for item in check.get(
            "schema_types",
            [],
        )
    }

    if configured_schema_types:
        audit_schema_types = {
            str(item)
            for item in parse_jsonish(
                audit.get("schema_types"),
                [],
            )
        }

        matching_schema = sorted(
            configured_schema_types
            & audit_schema_types
        )

        if matching_schema:
            found = True
            evidence.append(
                "Schema detected: "
                + ", ".join(
                    matching_schema
                )
                + "."
            )

        if (
            not found
            and check.get(
                "allow_local_schema_fallback"
            )
            and to_bool(
                audit.get(
                    "has_local_business_schema"
                )
            )
        ):
            found = True
            evidence.append(
                "A recognised local-business "
                "schema type was detected."
            )

    page_signal = check.get(
        "page_signal"
    )

    if page_signal:
        for page in normalised_pages:
            signals = page.get(
                "detected_signals",
                {},
            )

            if to_bool(
                signals.get(page_signal)
            ):
                found = True
                evidence.append(
                    "Detected on "
                    + page_label(page)
                    + "."
                )
                break

    page_terms = [
        str(term).lower()
        for term in check.get(
            "page_terms",
            [],
        )
    ]

    if page_terms:
        for page in normalised_pages:
            text = combined_page_text(
                page
            )

            matching_term = next(
                (
                    term
                    for term in page_terms
                    if term in text
                ),
                None,
            )

            if matching_term:
                found = True
                evidence.append(
                    f"Phrase '{matching_term}' "
                    f"detected on {page_label(page)}."
                )
                break

    url_terms = [
        str(term).lower()
        for term in check.get(
            "url_terms",
            [],
        )
    ]

    if url_terms:
        for page in normalised_pages:
            url = clean_url(
                page.get("final_url")
                or page.get("url")
            ).lower()

            matching_term = next(
                (
                    term
                    for term in url_terms
                    if term in url
                ),
                None,
            )

            if matching_term:
                found = True
                evidence.append(
                    f"URL signal '{matching_term}' "
                    f"detected: {url}."
                )
                break

    return {
        "found": found,
        "evidence": evidence[:4],
    }


def evaluate_business(
    audit: dict[str, Any],
    pages: pd.DataFrame | list[dict[str, Any]] | None,
    profile: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    return {
        check["key"]: evaluate_check(
            audit,
            pages,
            check,
        )
        for check in profile["checks"]
    }


def audit_score(
    audit: dict[str, Any],
) -> float | None:
    value = audit.get(
        "website_completeness_score"
    )

    if is_missing(value):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def benchmark_position(
    target_found: bool | None,
    prevalence: float | None,
) -> str:
    if target_found is None:
        return "Unavailable"

    if prevalence is None:
        return (
            "Detected"
            if target_found
            else "Not detected"
        )

    if target_found:
        if prevalence < 0.50:
            return "Differentiator"

        return "In line / strength"

    if prevalence >= 0.60:
        return "Material gap"

    if prevalence >= 0.30:
        return "Opportunity"

    return "Low-prevalence gap"


def priority_band(
    score: float,
) -> str:
    if score >= 60:
        return "High"

    if score >= 30:
        return "Medium"

    return "Low"


def build_website_benchmark(
    *,
    target_google_place_id: str,
    audits: pd.DataFrame,
    pages_by_run: dict[str, pd.DataFrame],
    profile: dict[str, Any],
) -> dict[str, Any]:
    if audits.empty:
        return {
            "error": (
                "No website audits are available "
                "for the selected cohort."
            )
        }

    records = audits.to_dict(
        "records"
    )

    target = next(
        (
            record
            for record in records
            if str(
                record.get(
                    "google_place_id"
                )
            )
            == str(target_google_place_id)
        ),
        None,
    )

    if target is None:
        return {
            "error": (
                "The target has not yet been audited."
            )
        }

    target_status = str(
        target.get("audit_status")
        or ""
    )

    if target_status not in (
        USABLE_AUDIT_STATUSES
    ):
        return {
            "error": (
                "The target's latest audit is not "
                f"usable ({target_status or 'unknown status'})."
            )
        }

    usable_records = [
        record
        for record in records
        if str(
            record.get("audit_status")
            or ""
        )
        in USABLE_AUDIT_STATUSES
    ]

    unavailable_records = [
        record
        for record in records
        if str(
            record.get("audit_status")
            or ""
        )
        not in USABLE_AUDIT_STATUSES
    ]

    evaluations: dict[
        str,
        dict[str, dict[str, Any]],
    ] = {}

    for record in usable_records:
        run_id = str(record.get("id"))

        evaluations[
            str(record.get("google_place_id"))
        ] = evaluate_business(
            record,
            pages_by_run.get(
                run_id,
                pd.DataFrame(),
            ),
            profile,
        )

    target_evaluation = evaluations[
        str(target_google_place_id)
    ]

    competitor_records = [
        record
        for record in usable_records
        if str(
            record.get(
                "google_place_id"
            )
        )
        != str(target_google_place_id)
    ]

    feature_rows: list[dict[str, Any]] = []
    recommendations: list[
        dict[str, Any]
    ] = []
    strengths: list[dict[str, Any]] = []

    for check in profile["checks"]:
        key = check["key"]
        target_result = (
            target_evaluation[key]
        )
        target_found = target_result[
            "found"
        ]

        competitor_values = []

        for competitor in competitor_records:
            competitor_id = str(
                competitor.get(
                    "google_place_id"
                )
            )

            value = evaluations[
                competitor_id
            ][key]["found"]

            if value is not None:
                competitor_values.append(
                    bool(value)
                )

        cohort_size = len(
            competitor_values
        )

        prevalence = (
            sum(competitor_values)
            / cohort_size
            if cohort_size
            else None
        )

        found_count = (
            sum(competitor_values)
            if cohort_size
            else 0
        )

        position = benchmark_position(
            target_found,
            prevalence,
        )

        feature_rows.append(
            {
                "key": key,
                "category": check[
                    "category"
                ],
                "check": check["label"],
                "weight": check["weight"],
                "target_found": (
                    target_found
                ),
                "target_evidence": (
                    target_result[
                        "evidence"
                    ]
                ),
                "cohort_found": (
                    found_count
                ),
                "cohort_size": cohort_size,
                "cohort_prevalence": (
                    prevalence
                ),
                "position": position,
            }
        )

        if (
            target_found is False
            and prevalence is not None
            and prevalence >= 0.20
        ):
            priority_score = (
                float(check["weight"])
                * prevalence
                * 20
            )

            recommendations.append(
                {
                    "check": check[
                        "label"
                    ],
                    "category": check[
                        "category"
                    ],
                    "priority": (
                        priority_band(
                            priority_score
                        )
                    ),
                    "priority_score": round(
                        priority_score,
                        1,
                    ),
                    "cohort_prevalence": (
                        prevalence
                    ),
                    "cohort_found": (
                        found_count
                    ),
                    "cohort_size": (
                        cohort_size
                    ),
                    "recommendation": (
                        check[
                            "recommendation"
                        ]
                    ),
                }
            )

        if target_found is True:
            strengths.append(
                {
                    "check": check[
                        "label"
                    ],
                    "category": check[
                        "category"
                    ],
                    "weight": check[
                        "weight"
                    ],
                    "cohort_prevalence": (
                        prevalence
                    ),
                    "position": position,
                    "evidence": (
                        target_result[
                            "evidence"
                        ]
                    ),
                }
            )

    feature_frame = pd.DataFrame(
        feature_rows
    )

    recommendations = sorted(
        recommendations,
        key=lambda item: (
            -item["priority_score"],
            item["check"],
        ),
    )

    strengths = sorted(
        strengths,
        key=lambda item: (
            -item["weight"],
            (
                item[
                    "cohort_prevalence"
                ]
                if item[
                    "cohort_prevalence"
                ]
                is not None
                else 1.0
            ),
            item["check"],
        ),
    )

    score_rows = []

    for record in usable_records:
        score_rows.append(
            {
                "google_place_id": (
                    record.get(
                        "google_place_id"
                    )
                ),
                "business_name": (
                    record.get(
                        "business_name"
                    )
                ),
                "relationship_status": (
                    record.get(
                        "relationship_status"
                    )
                ),
                "audit_status": (
                    record.get(
                        "audit_status"
                    )
                ),
                "score": audit_score(
                    record
                ),
                "pages_crawled": (
                    record.get(
                        "pages_crawled"
                    )
                ),
                "completed_at": (
                    record.get(
                        "completed_at"
                    )
                ),
            }
        )

    score_frame = pd.DataFrame(
        score_rows
    )

    ranked_scores = score_frame[
        score_frame["score"].notna()
    ].copy()

    ranked_scores = ranked_scores.sort_values(
        [
            "score",
            "business_name",
        ],
        ascending=[
            False,
            True,
        ],
    ).reset_index(drop=True)

    ranked_scores["rank"] = (
        ranked_scores["score"]
        .rank(
            method="min",
            ascending=False,
        )
        .astype(int)
    )

    target_score = audit_score(target)

    target_rank = None

    if not ranked_scores.empty:
        target_rank_rows = ranked_scores[
            ranked_scores[
                "google_place_id"
            ].astype(str)
            == str(target_google_place_id)
        ]

        if not target_rank_rows.empty:
            target_rank = int(
                target_rank_rows.iloc[
                    0
                ]["rank"]
            )

    competitor_scores = [
        audit_score(record)
        for record in competitor_records
    ]

    competitor_scores = [
        score
        for score in competitor_scores
        if score is not None
    ]

    cohort_median = (
        float(
            pd.Series(
                competitor_scores
            ).median()
        )
        if competitor_scores
        else None
    )

    return {
        "target": target,
        "target_score": target_score,
        "target_rank": target_rank,
        "rank_denominator": len(
            ranked_scores
        ),
        "cohort_median": cohort_median,
        "audited_competitors": len(
            competitor_records
        ),
        "unavailable_records": (
            unavailable_records
        ),
        "feature_benchmark": (
            feature_frame
        ),
        "recommendations": (
            recommendations
        ),
        "strengths": strengths,
        "score_comparison": (
            ranked_scores
        ),
        "profile": profile,
    }
