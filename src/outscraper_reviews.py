from __future__ import annotations

import hashlib
import json
from decimal import Decimal, ROUND_CEILING
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd


REVIEWS_ENDPOINT = (
    "https://api.outscraper.com/google-maps-reviews"
)

REQUEST_RESULT_ENDPOINT = (
    "https://api.outscraper.com/requests/{request_id}"
)


class OutscraperError(RuntimeError):
    pass


# ---------------------------------------------------------------------
# App-side cost guard
# ---------------------------------------------------------------------

# Outscraper currently publishes a medium-tier Google Reviews rate of
# USD $3 per 1,000 reviews. The app deliberately uses a conservative
# GBP conversion assumption and ignores the free tier / volume discounts
# when deciding whether an API pull is safe to submit.
#
# This makes the estimate an upper-bound guardrail rather than an invoice
# forecast.
COST_GUARD_USD_PER_1000_REVIEWS = 3.00
COST_GUARD_USD_PER_GBP = 1.20
DEFAULT_APP_COST_CEILING_GBP = 7.50


def estimate_review_pull_cost_gbp(
    *,
    requested_reviews: int,
    usd_per_1000_reviews: float = (
        COST_GUARD_USD_PER_1000_REVIEWS
    ),
    usd_per_gbp: float = (
        COST_GUARD_USD_PER_GBP
    ),
) -> float:
    requested_reviews = max(
        0,
        int(
            requested_reviews
        ),
    )

    if requested_reviews == 0:
        return 0.0

    usd_cost = (
        Decimal(
            requested_reviews
        )
        / Decimal("1000")
        * Decimal(
            str(
                usd_per_1000_reviews
            )
        )
    )

    gbp_cost = (
        usd_cost
        / Decimal(
            str(
                usd_per_gbp
            )
        )
    )

    # Round UP rather than to nearest penny so the cost guard
    # never understates the projected upper-bound cost.
    return float(
        gbp_cost.quantize(
            Decimal("0.01"),
            rounding=ROUND_CEILING,
        )
    )


def review_pull_within_cost_ceiling(
    *,
    requested_reviews: int,
    ceiling_gbp: float = (
        DEFAULT_APP_COST_CEILING_GBP
    ),
) -> tuple[
    bool,
    float,
]:
    projected_gbp = (
        estimate_review_pull_cost_gbp(
            requested_reviews=(
                requested_reviews
            )
        )
    )

    return (
        projected_gbp
        <= float(
            ceiling_gbp
        ),
        projected_gbp,
    )


def _request_json(
    url: str,
    *,
    api_key: str,
    params: dict[str, Any] | None = None,
    timeout: int = 45,
) -> tuple[int, dict[str, Any]]:
    if params:
        query_string = urlencode(
            params,
            doseq=True,
        )
        url = (
            url
            + ("&" if "?" in url else "?")
            + query_string
        )

    request = Request(
        url,
        headers={
            "X-API-KEY": api_key,
            "Accept": "application/json",
            "User-Agent": (
                "local-ai-discoverability/"
                "outscraper-reviews-v1"
            ),
        },
        method="GET",
    )

    try:
        with urlopen(
            request,
            timeout=timeout,
        ) as response:
            status_code = int(
                getattr(
                    response,
                    "status",
                    200,
                )
            )

            body = response.read().decode(
                "utf-8"
            )

    except HTTPError as exc:
        body = exc.read().decode(
            "utf-8",
            errors="replace",
        )

        try:
            payload = json.loads(
                body
            )
        except json.JSONDecodeError:
            payload = {}

        message = (
            payload.get(
                "errorMessage"
            )
            or payload.get(
                "message"
            )
            or body
            or str(exc)
        )

        raise OutscraperError(
            f"Outscraper API error "
            f"{exc.code}: {message}"
        ) from exc

    except URLError as exc:
        raise OutscraperError(
            "Could not reach Outscraper: "
            + str(
                exc.reason
            )
        ) from exc

    try:
        payload = json.loads(
            body
        )
    except json.JSONDecodeError as exc:
        raise OutscraperError(
            "Outscraper returned a non-JSON response."
        ) from exc

    return (
        status_code,
        payload,
    )


def submit_google_reviews(
    *,
    api_key: str,
    place_ids: list[str],
    reviews_limit: int = 100,
    sort: str = "most_relevant",
    language: str = "en",
    region: str = "GB",
    ignore_empty: bool = True,
) -> dict[str, Any]:
    clean_ids = list(
        dict.fromkeys(
            str(place_id).strip()
            for place_id in place_ids
            if str(place_id).strip()
        )
    )

    if not clean_ids:
        raise ValueError(
            "At least one Google Place ID is required."
        )

    if len(clean_ids) > 1000:
        raise ValueError(
            "Outscraper supports up to 1,000 queries "
            "in a single batch request."
        )

    if reviews_limit < 1:
        raise ValueError(
            "reviews_limit must be at least 1."
        )

    allowed_sort = {
        "most_relevant",
        "newest",
        "highest_rating",
        "lowest_rating",
    }

    if sort not in allowed_sort:
        raise ValueError(
            f"Unsupported review sort: {sort}"
        )

    status_code, payload = _request_json(
        REVIEWS_ENDPOINT,
        api_key=api_key,
        params={
            "query": clean_ids,
            "reviewsLimit": int(
                reviews_limit
            ),
            "limit": 1,
            "sort": sort,
            "ignoreEmpty": (
                "true"
                if ignore_empty
                else "false"
            ),
            "source": "google",
            "language": language,
            "region": region,
            "async": "true",
        },
        timeout=45,
    )

    return {
        "http_status":
            status_code,
        "id":
            payload.get(
                "id"
            ),
        "status":
            payload.get(
                "status"
            ),
        "data":
            payload.get(
                "data"
            ),
        "results_location":
            payload.get(
                "results_location"
            ),
        "raw":
            payload,
    }


def get_request_result(
    *,
    api_key: str,
    request_id: str,
) -> dict[str, Any]:
    request_id = str(
        request_id
    ).strip()

    if not request_id:
        raise ValueError(
            "request_id is required."
        )

    status_code, payload = _request_json(
        REQUEST_RESULT_ENDPOINT.format(
            request_id=request_id
        ),
        api_key=api_key,
        params={
            "flat": "false",
        },
        timeout=45,
    )

    return {
        "http_status":
            status_code,
        "id":
            payload.get(
                "id",
                request_id,
            ),
        "status":
            payload.get(
                "status"
            ),
        "data":
            payload.get(
                "data"
            ),
        "raw":
            payload,
    }


def _iter_places(
    value: Any,
):
    if isinstance(
        value,
        dict,
    ):
        if (
            "reviews_data" in value
            or "place_id" in value
        ):
            yield value
            return

        for child in value.values():
            yield from _iter_places(
                child
            )

    elif isinstance(
        value,
        list,
    ):
        for item in value:
            yield from _iter_places(
                item
            )


def _stable_review_id(
    *,
    place_id: str,
    review: dict[str, Any],
) -> str:
    explicit = (
        review.get(
            "review_id"
        )
        or review.get(
            "reviewId"
        )
    )

    if explicit:
        return str(
            explicit
        )

    seed = (
        review.get(
            "review_link"
        )
        or "|".join(
            [
                str(
                    place_id
                    or ""
                ),
                str(
                    review.get(
                        "author_id"
                    )
                    or ""
                ),
                str(
                    review.get(
                        "review_timestamp"
                    )
                    or ""
                ),
                str(
                    review.get(
                        "review_text"
                    )
                    or ""
                ),
            ]
        )
    )

    return (
        "api_"
        + hashlib.sha1(
            str(seed).encode(
                "utf-8"
            )
        ).hexdigest()
    )


def flatten_google_reviews_response(
    data: Any,
) -> pd.DataFrame:
    rows: list[
        dict[str, Any]
    ] = []

    for place in _iter_places(
        data
    ):
        place_id = str(
            place.get(
                "place_id"
            )
            or ""
        ).strip()

        business_name = str(
            place.get(
                "name"
            )
            or ""
        ).strip()

        location_link = place.get(
            "location_link"
        )

        reviews = (
            place.get(
                "reviews_data"
            )
            or []
        )

        if not isinstance(
            reviews,
            list,
        ):
            continue

        for review in reviews:
            if not isinstance(
                review,
                dict,
            ):
                continue

            row = dict(
                review
            )

            row[
                "name"
            ] = business_name

            row[
                "place_id"
            ] = place_id

            row[
                "location_link"
            ] = (
                row.get(
                    "location_link"
                )
                or location_link
            )

            row[
                "review_id"
            ] = _stable_review_id(
                place_id=place_id,
                review=review,
            )

            rows.append(
                row
            )

    columns = [
        "name",
        "place_id",
        "review_id",
        "review_text",
        "review_rating",
        "review_timestamp",
        "review_likes",
        "author_title",
        "author_id",
        "author_reviews_count",
        "author_photos_count",
        "owner_answer",
        "owner_answer_timestamp",
        "review_link",
        "location_link",
    ]

    frame = pd.DataFrame(
        rows
    )

    if frame.empty:
        return pd.DataFrame(
            columns=columns
        )

    for column in columns:
        if column not in frame.columns:
            frame[
                column
            ] = None

    return frame


def api_import_source_name(
    request_id: str,
) -> str:
    timestamp = datetime.now(
        timezone.utc
    ).strftime(
        "%Y%m%dT%H%M%SZ"
    )

    return (
        "outscraper_api_"
        + str(
            request_id
        )[:12]
        + "_"
        + timestamp
        + ".json"
    )
