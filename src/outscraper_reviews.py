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

# Endpoint paths confirmed against Outscraper's own Python client source
# (github.com/outscraper/outscraper-python, outscraper/client.py) rather than
# guessed - note the two do NOT share a URL shape (Yelp uses a slash,
# TripAdvisor a hyphen).
YELP_REVIEWS_ENDPOINT = (
    "https://api.outscraper.com/yelp/reviews"
)

TRIPADVISOR_REVIEWS_ENDPOINT = (
    "https://api.outscraper.com/tripadvisor-reviews"
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


def submit_yelp_reviews(
    *,
    api_key: str,
    business_urls: list[str],
    reviews_limit: int = 100,
    sort: str = "relevance_desc",
    ignore_empty: bool = True,
) -> dict[str, Any]:
    """Submit a Yelp reviews pull.

    Unlike Google, Yelp has no Google Place ID to query by - `business_urls`
    must be each business's actual Yelp page URL (or Outscraper business
    slug), sourced from business_platform_links. Callers are responsible for
    keeping track of which URL belongs to which google_place_id so the
    result can be attributed correctly once it comes back.
    """

    clean_urls = list(
        dict.fromkeys(
            str(url).strip()
            for url in business_urls
            if str(url).strip()
        )
    )

    if not clean_urls:
        raise ValueError(
            "At least one Yelp business URL is required."
        )

    if len(clean_urls) > 250:
        raise ValueError(
            "Outscraper supports up to 250 Yelp queries "
            "in a single batch request."
        )

    if reviews_limit < 1:
        raise ValueError(
            "reviews_limit must be at least 1."
        )

    allowed_sort = {
        "relevance_desc",
        "date_desc",
        "date_asc",
        "rating_desc",
        "rating_asc",
        "elites_desc",
    }

    if sort not in allowed_sort:
        raise ValueError(f"Unsupported review sort: {sort}")

    status_code, payload = _request_json(
        YELP_REVIEWS_ENDPOINT,
        api_key=api_key,
        params={
            "query": clean_urls,
            "limit": int(reviews_limit),
            "sort": sort,
            "ignoreEmpty": (
                "true" if ignore_empty else "false"
            ),
            "async": "true",
        },
        timeout=45,
    )

    return {
        "http_status": status_code,
        "id": payload.get("id"),
        "status": payload.get("status"),
        "data": payload.get("data"),
        "results_location": payload.get("results_location"),
        "raw": payload,
    }


def submit_tripadvisor_reviews(
    *,
    api_key: str,
    business_urls: list[str],
    reviews_limit: int = 100,
    language: str = "default",
) -> dict[str, Any]:
    """Submit a TripAdvisor reviews pull.

    Same caveat as submit_yelp_reviews: `business_urls` are TripAdvisor page
    URLs, not Google Place IDs - the caller attributes results back to a
    business itself.
    """

    clean_urls = list(
        dict.fromkeys(
            str(url).strip()
            for url in business_urls
            if str(url).strip()
        )
    )

    if not clean_urls:
        raise ValueError(
            "At least one TripAdvisor business URL is required."
        )

    if len(clean_urls) > 250:
        raise ValueError(
            "Outscraper supports up to 250 TripAdvisor queries "
            "in a single batch request."
        )

    if reviews_limit < 1:
        raise ValueError(
            "reviews_limit must be at least 1."
        )

    status_code, payload = _request_json(
        TRIPADVISOR_REVIEWS_ENDPOINT,
        api_key=api_key,
        params={
            "query": clean_urls,
            "limit": int(reviews_limit),
            "language": language,
            "async": "true",
        },
        timeout=45,
    )

    return {
        "http_status": status_code,
        "id": payload.get("id"),
        "status": payload.get("status"),
        "data": payload.get("data"),
        "results_location": payload.get("results_location"),
        "raw": payload,
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


def _resolve_place_id(
    place: dict[str, Any],
    *,
    url_to_place_id: dict[str, str],
) -> str | None:
    """Match a Yelp/TripAdvisor result block back to a google_place_id.

    Neither platform's response carries a Google Place ID - the only way to
    attribute a result to a business is by the URL that was submitted for
    it, which Outscraper echoes back under one of a few possible keys
    depending on the endpoint. Every candidate is tried; if none match, the
    caller drops the block rather than risk crediting the wrong business.
    """

    candidates = [
        place.get("query"),
        place.get("url"),
        place.get("link"),
        place.get("business_link"),
        place.get("location_link"),
    ]

    for candidate in candidates:
        candidate = str(candidate or "").strip().rstrip("/")

        if not candidate:
            continue

        for known_url, place_id in url_to_place_id.items():
            if candidate == known_url.strip().rstrip("/"):
                return place_id

    return None


def flatten_yelp_reviews_response(
    data: Any,
    *,
    url_to_place_id: dict[str, str],
) -> pd.DataFrame:
    """Map a Yelp reviews response onto the same canonical row shape as
    flatten_google_reviews_response.

    NOTE: Outscraper does not publish the exact Yelp response field names in
    their docs. The field names below are best-effort based on their other
    review endpoints' conventions and Yelp's own public data shape, and
    should be checked against one real pull before relying on them - any
    review whose text/rating can't be found here is dropped by
    normalise_review_frame's validity check rather than imported wrong, so a
    wrong guess fails safe (fewer rows imported), not silently.
    """

    rows: list[dict[str, Any]] = []

    for place in _iter_places(data):
        place_id = _resolve_place_id(
            place, url_to_place_id=url_to_place_id
        )

        if not place_id:
            continue

        business_name = str(
            place.get("name") or place.get("business_name") or ""
        ).strip()

        reviews = (
            place.get("reviews_data")
            or place.get("reviews")
            or []
        )

        if not isinstance(reviews, list):
            continue

        for review in reviews:
            if not isinstance(review, dict):
                continue

            author = review.get("user") or {}
            if not isinstance(author, dict):
                author = {}

            row = dict(review)
            row["name"] = business_name
            row["place_id"] = place_id
            row["review_text"] = (
                review.get("review_text")
                or review.get("text")
                or review.get("comment")
            )
            row["review_rating"] = (
                review.get("review_rating")
                or review.get("rating")
            )
            row["review_timestamp"] = (
                review.get("review_timestamp")
                or review.get("time_created_timestamp")
            )
            row["author_title"] = (
                review.get("author_title")
                or author.get("name")
                or review.get("user_name")
            )
            row["author_id"] = (
                review.get("author_id")
                or author.get("id")
            )
            row["review_link"] = (
                review.get("review_link") or review.get("url")
            )
            row["location_link"] = place.get("url") or place.get("query")
            row["review_id"] = _stable_review_id(
                place_id=place_id, review=review
            )

            rows.append(row)

    columns = [
        "name", "place_id", "review_id", "review_text", "review_rating",
        "review_timestamp", "review_likes", "author_title", "author_id",
        "author_reviews_count", "author_photos_count", "owner_answer",
        "owner_answer_timestamp", "review_link", "location_link",
    ]

    frame = pd.DataFrame(rows)

    if frame.empty:
        return pd.DataFrame(columns=columns)

    for column in columns:
        if column not in frame.columns:
            frame[column] = None

    return frame


def flatten_tripadvisor_reviews_response(
    data: Any,
    *,
    url_to_place_id: dict[str, str],
) -> pd.DataFrame:
    """Map a TripAdvisor reviews response onto the canonical row shape, plus
    a `sub_ratings` column (Food/Service/Value etc.) that business_reviews
    carries as jsonb for platforms that have them.

    Same field-name caveat as flatten_yelp_reviews_response: best-effort
    pending one real verification pull.
    """

    rows: list[dict[str, Any]] = []

    for place in _iter_places(data):
        place_id = _resolve_place_id(
            place, url_to_place_id=url_to_place_id
        )

        if not place_id:
            continue

        business_name = str(
            place.get("name") or place.get("business_name") or ""
        ).strip()

        reviews = (
            place.get("reviews_data")
            or place.get("reviews")
            or []
        )

        if not isinstance(reviews, list):
            continue

        for review in reviews:
            if not isinstance(review, dict):
                continue

            author = review.get("user") or {}
            if not isinstance(author, dict):
                author = {}

            sub_ratings = (
                review.get("sub_ratings")
                or review.get("ratings")
                or review.get("subratings")
            )

            row = dict(review)
            row["name"] = business_name
            row["place_id"] = place_id
            row["review_text"] = (
                review.get("review_text") or review.get("text")
            )
            row["review_rating"] = (
                review.get("review_rating") or review.get("rating")
            )
            row["review_timestamp"] = (
                review.get("review_timestamp")
                or review.get("published_date_timestamp")
            )
            row["author_title"] = (
                review.get("author_title")
                or author.get("username")
                or review.get("username")
            )
            row["author_id"] = (
                review.get("author_id") or author.get("id")
            )
            row["review_link"] = (
                review.get("review_link") or review.get("url")
            )
            row["location_link"] = place.get("url") or place.get("query")
            row["sub_ratings"] = (
                json.dumps(sub_ratings)
                if isinstance(sub_ratings, dict)
                else None
            )
            row["review_id"] = _stable_review_id(
                place_id=place_id, review=review
            )

            rows.append(row)

    columns = [
        "name", "place_id", "review_id", "review_text", "review_rating",
        "review_timestamp", "review_likes", "author_title", "author_id",
        "author_reviews_count", "author_photos_count", "owner_answer",
        "owner_answer_timestamp", "review_link", "location_link",
        "sub_ratings",
    ]

    frame = pd.DataFrame(rows)

    if frame.empty:
        return pd.DataFrame(columns=columns)

    for column in columns:
        if column not in frame.columns:
            frame[column] = None

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
