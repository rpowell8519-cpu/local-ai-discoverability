"""Sprint 1 (multi-platform review ingestion): Yelp and TripAdvisor via Outscraper.

Covers the parts that don't need a live database - request-shape validation,
the flatten functions that map Outscraper's response onto business_reviews'
canonical row shape, and business_platform_links' input validation. The
DB-write paths (import_reviews, save_platform_link's insert) follow this
repo's existing convention of not unit-testing thin SQL-wrapper functions
directly (review_repository.py and competitor_reviews.py have none either) -
they're exercised through the Review Insights page tests instead.
"""

from __future__ import annotations

import pytest

from src.business_platform_links import save_platform_link
from src.outscraper_reviews import (
    TRIPADVISOR_REVIEWS_ENDPOINT,
    YELP_REVIEWS_ENDPOINT,
    flatten_tripadvisor_reviews_response,
    flatten_yelp_reviews_response,
    submit_tripadvisor_reviews,
    submit_yelp_reviews,
)
from src.review_ingestion import (
    SOURCE_TRIPADVISOR,
    SOURCE_YELP,
    normalise_review_frame,
)


YELP_URL = "https://www.yelp.com/biz/ciscos-karma-brighton"
TRIPADVISOR_URL = "https://www.tripadvisor.co.uk/Restaurant_Review-xyz.html"
PLACE_ID = "ChIJTEST"


def _yelp_sample(query=YELP_URL):
    return [
        {
            "query": query,
            "name": "Ciscos Karma",
            "reviews_data": [
                {
                    "review_id": "abc123",
                    "rating": 5,
                    "text": "Lovely place, great coffee.",
                    "time_created": 1758960000,
                    "user": {"name": "Jo B", "id": "u1"},
                    "url": f"{query}?hrid=abc123",
                }
            ],
        }
    ]


def _tripadvisor_sample(query=TRIPADVISOR_URL):
    return [
        {
            "query": query,
            "name": "Ciscos Karma",
            "reviews_data": [
                {
                    "review_id": "def456",
                    "rating": 4,
                    "text": "Nice brunch spot.",
                    "published_date_timestamp": 1758960000,
                    "user": {"username": "traveller99"},
                    "sub_ratings": {"food": 5, "service": 4, "value": 4},
                }
            ],
        }
    ]


# ---------------------------------------------------------------------
# submit_* request-shape validation (no network call made)
# ---------------------------------------------------------------------

class TestSubmitValidation:
    def test_yelp_submit_rejects_an_empty_url_list(self):
        with pytest.raises(ValueError, match="At least one Yelp"):
            submit_yelp_reviews(api_key="x", business_urls=[])

    def test_yelp_submit_rejects_more_than_250_urls(self):
        with pytest.raises(ValueError, match="250"):
            submit_yelp_reviews(
                api_key="x",
                business_urls=[f"https://www.yelp.com/biz/{i}" for i in range(251)],
            )

    def test_yelp_submit_rejects_an_unsupported_sort(self):
        with pytest.raises(ValueError, match="sort"):
            submit_yelp_reviews(api_key="x", business_urls=[YELP_URL], sort="popularity")

    def test_tripadvisor_submit_rejects_an_empty_url_list(self):
        with pytest.raises(ValueError, match="At least one TripAdvisor"):
            submit_tripadvisor_reviews(api_key="x", business_urls=[])

    def test_yelp_submit_hits_the_confirmed_endpoint(self, monkeypatch):
        captured = {}

        def fake_request_json(url, *, api_key, params, timeout):
            captured["url"] = url
            captured["params"] = params
            return 200, {"id": "req-1", "status": "Pending", "data": None}

        monkeypatch.setattr(
            "src.outscraper_reviews._request_json", fake_request_json
        )

        submit_yelp_reviews(api_key="x", business_urls=[YELP_URL], reviews_limit=50)

        assert captured["url"] == YELP_REVIEWS_ENDPOINT
        assert captured["params"]["query"] == [YELP_URL]
        assert captured["params"]["limit"] == 50

    def test_tripadvisor_submit_hits_the_confirmed_endpoint(self, monkeypatch):
        captured = {}

        def fake_request_json(url, *, api_key, params, timeout):
            captured["url"] = url
            captured["params"] = params
            return 200, {"id": "req-2", "status": "Pending", "data": None}

        monkeypatch.setattr(
            "src.outscraper_reviews._request_json", fake_request_json
        )

        submit_tripadvisor_reviews(api_key="x", business_urls=[TRIPADVISOR_URL])

        assert captured["url"] == TRIPADVISOR_REVIEWS_ENDPOINT
        assert captured["params"]["query"] == [TRIPADVISOR_URL]


# ---------------------------------------------------------------------
# flatten_* - mapping Outscraper's response onto the canonical row shape
# ---------------------------------------------------------------------

class TestFlattenYelp:
    def test_a_matched_business_produces_one_row_per_review(self):
        frame = flatten_yelp_reviews_response(
            _yelp_sample(), url_to_place_id={YELP_URL: PLACE_ID}
        )

        assert len(frame) == 1
        row = frame.iloc[0]
        assert row["place_id"] == PLACE_ID
        assert row["name"] == "Ciscos Karma"
        assert row["review_text"] == "Lovely place, great coffee."
        assert row["review_rating"] == 5
        assert row["author_title"] == "Jo B"

    def test_a_result_for_an_unrecognised_url_is_dropped_not_misattributed(self):
        frame = flatten_yelp_reviews_response(
            _yelp_sample(query="https://www.yelp.com/biz/some-other-business"),
            url_to_place_id={YELP_URL: PLACE_ID},
        )

        assert frame.empty

    def test_trailing_slash_differences_still_match(self):
        frame = flatten_yelp_reviews_response(
            _yelp_sample(query=YELP_URL + "/"),
            url_to_place_id={YELP_URL: PLACE_ID},
        )

        assert len(frame) == 1
        assert frame.iloc[0]["place_id"] == PLACE_ID

    def test_output_feeds_normalise_review_frame_as_a_valid_row(self):
        frame = flatten_yelp_reviews_response(
            _yelp_sample(), url_to_place_id={YELP_URL: PLACE_ID}
        )
        valid, invalid = normalise_review_frame(frame)

        assert len(valid) == 1
        assert invalid.empty


class TestFlattenTripadvisor:
    def test_a_matched_business_produces_one_row_with_sub_ratings(self):
        frame = flatten_tripadvisor_reviews_response(
            _tripadvisor_sample(), url_to_place_id={TRIPADVISOR_URL: PLACE_ID}
        )

        assert len(frame) == 1
        row = frame.iloc[0]
        assert row["place_id"] == PLACE_ID
        assert row["review_rating"] == 4
        assert row["author_title"] == "traveller99"
        assert "food" in row["sub_ratings"]

    def test_an_unrecognised_url_is_dropped(self):
        frame = flatten_tripadvisor_reviews_response(
            _tripadvisor_sample(query="https://www.tripadvisor.co.uk/Restaurant_Review-other.html"),
            url_to_place_id={TRIPADVISOR_URL: PLACE_ID},
        )

        assert frame.empty

    def test_sub_ratings_survive_normalise_review_frame_as_a_jsonb_ready_string(self):
        frame = flatten_tripadvisor_reviews_response(
            _tripadvisor_sample(), url_to_place_id={TRIPADVISOR_URL: PLACE_ID}
        )
        valid, _ = normalise_review_frame(frame)

        assert len(valid) == 1
        assert '"food"' in valid.iloc[0]["sub_ratings"]


# ---------------------------------------------------------------------
# review_ingestion source constants stay distinguishable per platform
# ---------------------------------------------------------------------

def test_the_three_review_sources_are_all_distinct():
    from src.review_ingestion import SOURCE

    assert len({SOURCE, SOURCE_YELP, SOURCE_TRIPADVISOR}) == 3


# ---------------------------------------------------------------------
# business_platform_links - input validation ahead of any DB write
# ---------------------------------------------------------------------

class TestSavePlatformLinkValidation:
    def test_rejects_an_unsupported_platform(self):
        with pytest.raises(ValueError, match="Unsupported platform"):
            save_platform_link(
                google_place_id=PLACE_ID,
                platform="facebook",
                external_url="https://facebook.com/x",
            )

    def test_rejects_a_value_that_is_not_a_url(self):
        with pytest.raises(ValueError, match="full page URL"):
            save_platform_link(
                google_place_id=PLACE_ID,
                platform="yelp",
                external_url="ciscos karma brighton",
            )

    def test_rejects_an_empty_url(self):
        with pytest.raises(ValueError, match="full page URL"):
            save_platform_link(
                google_place_id=PLACE_ID, platform="yelp", external_url="   "
            )
