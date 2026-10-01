"""Sprint 1 (multi-platform review ingestion): Yelp and TripAdvisor via Outscraper.

Covers the parts that don't need a live database - request-shape validation,
the flatten functions that map Outscraper's response onto business_reviews'
canonical row shape, and business_platform_links' input validation. The
DB-write paths (import_reviews, save_platform_link's insert) follow this
repo's existing convention of not unit-testing thin SQL-wrapper functions
directly (review_repository.py and competitor_reviews.py have none either) -
they're exercised through the Review Insights page tests instead.

The Yelp fixture below is the REAL response shape (field names and nesting),
confirmed against a live pull for Ciscos Karma on 2026-09-28 via the app's
debug expander - not a guess. It's a flat `[[review, review, ...]]`: every
review carries its own `query`/`business_name` directly, with no per-business
wrapper holding a `reviews_data` list (unlike Google's shape). The first
version of this ingestion shipped guessing the Google-style wrapper existed,
which silently matched nothing - see AGENTS.md's multi-platform section.

TripAdvisor's exact field names are still unconfirmed, so its fixture stays
a best-effort shape exercising the same shape-agnostic matching path.
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


YELP_URL = "https://m.yelp.com/biz/ciscos-karma-brighton"
TRIPADVISOR_URL = (
    "https://www.tripadvisor.co.uk/Attraction_Review-g186273-d5569984-"
    "Reviews-Ciscos_Karma-Brighton_East_Sussex_England.html"
)
PLACE_ID = "ChIJTEST"


def _real_yelp_review(review_id, text, *, query=YELP_URL, rating=5, timestamp=1399830275):
    """Shaped exactly like Outscraper's real /yelp/reviews response."""

    return {
        "query": query,
        "business_name": "Ciscos Karma",
        "reviews_per_score": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 3},
        "review_rating": rating,
        "review_text": text,
        "review_photos": [],
        "review_tags": {"helpful": 1, "thanks": 0, "love_this": 0, "oh_no": 0},
        "datetime_utc": "05/11/2014 17:44:35",
        "timestamp": timestamp,
        "review_id": review_id,
        "author_title": "Susan M.",
        "author_image": "https://s3-media0.fl.yelpcdn.com/photo/example/180s.jpg",
        "author_friend_count": 4,
        "author_photo_count": 1,
        "author_reviews_count": 19,
        "author_location": "Brighton, United Kingdom",
        "author_id": "PV1S47LgEut2oWB256TeRw",
        "author_link": "https://www.yelp.com/user_details?userid=PV1S47LgEut2oWB256TeRw",
        "owner_reply": None,
        "owner_reply_title": None,
        "owner_reply_datetime_utc": None,
        "owner_reply_timestamp": None,
        "next_page_cursor": None,
    }


def _yelp_sample(query=YELP_URL):
    return [[_real_yelp_review("abc123", "Lovely place, great coffee.", query=query)]]


def _real_tripadvisor_review(review_link_id, text, rating, *, query=TRIPADVISOR_URL):
    """Shaped exactly like Outscraper's real /tripadvisor-reviews response
    (confirmed 2026-09-28, Ciscos Karma). Unlike Yelp: no business_name
    field at all; `rating` is the business's overall rating (not this
    review's own - that's `review_rating`); the owner reply lives under
    `owner_response`/`owner_response_date`, not owner_reply/owner_answer;
    there's a real per-review permalink (`review_link`), which Yelp lacks.
    """

    return {
        "query": query,
        "reviews": 3,
        "rating": 4,
        "review_link": (
            "https://www.tripadvisor.co.uk/ShowUserReviews-g186273-d5569984-"
            f"{review_link_id}-Ciscos_Karma-Brighton_East_Sussex_England.html"
        ),
        "review_title": "A title",
        "review_text": text,
        "review_date": "2023-12-28",
        "review_timestamp": 1703721600,
        "author_title": "Sarah B",
        "author_image": "https://example.com/avatar.jpg",
        "review_rating": rating,
        "review_media": [],
        "owner_title": "",
        "owner_response": "",
        "owner_response_date": "",
    }


def _tripadvisor_sample(query=TRIPADVISOR_URL):
    return [[_real_tripadvisor_review("r931211604", "Had two fabulous hair cuts here.", 5, query=query)]]


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
        assert row["review_id"] == "abc123"
        assert row["author_title"] == "Susan M."
        assert row["review_timestamp"] == 1399830275

    def test_the_real_multi_review_response_shape_produces_one_row_each(self):
        # Exactly the nesting Outscraper actually returned: one outer list
        # (one per submitted query), one inner list of review dicts - no
        # business wrapper anywhere.
        data = [
            [
                _real_yelp_review("abc123", "Lovely place, great coffee.", timestamp=1399830275),
                _real_yelp_review("def456", "Great haircut, will return.", timestamp=1337687363),
                _real_yelp_review("ghi789", "Excellent hairdresser.", timestamp=1345685299),
            ]
        ]

        frame = flatten_yelp_reviews_response(data, url_to_place_id={YELP_URL: PLACE_ID})

        assert len(frame) == 3
        assert set(frame["review_id"]) == {"abc123", "def456", "ghi789"}
        assert (frame["place_id"] == PLACE_ID).all()

    def test_owner_reply_field_is_mapped_from_owner_reply_not_owner_answer(self):
        review = _real_yelp_review("abc123", "Text")
        review["owner_reply"] = "Thanks for visiting!"
        review["owner_reply_timestamp"] = 1400000000

        frame = flatten_yelp_reviews_response(
            [[review]], url_to_place_id={YELP_URL: PLACE_ID}
        )

        assert frame.iloc[0]["owner_answer"] == "Thanks for visiting!"
        assert frame.iloc[0]["owner_answer_timestamp"] == 1400000000

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
    def test_a_matched_business_uses_review_rating_not_the_business_level_rating(self):
        # The real payload has both `rating` (business overall, 4 here) and
        # `review_rating` (this specific review, 5) - must not conflate them.
        frame = flatten_tripadvisor_reviews_response(
            _tripadvisor_sample(),
            url_to_place_id={TRIPADVISOR_URL: PLACE_ID},
            place_id_to_name={PLACE_ID: "Ciscos Karma"},
        )

        assert len(frame) == 1
        row = frame.iloc[0]
        assert row["place_id"] == PLACE_ID
        assert row["review_rating"] == 5
        assert row["author_title"] == "Sarah B"
        assert row["review_link"].startswith("https://www.tripadvisor.co.uk/ShowUserReviews-")

    def test_without_place_id_to_name_every_row_is_invalid_not_silently_empty(self):
        # The real response has no business_name field anywhere - without
        # the fallback, every row would be dropped by normalise_review_frame
        # (reproducing the original "0 imported" bug for a different
        # reason), which is worth a named test rather than just relying on
        # place_id_to_name always being passed.
        frame = flatten_tripadvisor_reviews_response(
            _tripadvisor_sample(), url_to_place_id={TRIPADVISOR_URL: PLACE_ID}
        )

        assert frame.iloc[0]["name"] is None
        valid, invalid = normalise_review_frame(frame)
        assert valid.empty
        assert len(invalid) == 1

    def test_the_real_multi_review_response_shape_produces_one_row_each(self):
        data = [
            [
                _real_tripadvisor_review("r931211604", "Had two fabulous hair cuts here.", 5),
                _real_tripadvisor_review("r249426877", "The manicure was not so good.", 2),
                _real_tripadvisor_review("r190397214", "One of the best massages I've ever had!", 5),
            ]
        ]

        frame = flatten_tripadvisor_reviews_response(
            data,
            url_to_place_id={TRIPADVISOR_URL: PLACE_ID},
            place_id_to_name={PLACE_ID: "Ciscos Karma"},
        )

        assert len(frame) == 3
        assert list(frame["review_rating"]) == [5, 2, 5]
        assert (frame["name"] == "Ciscos Karma").all()
        valid, invalid = normalise_review_frame(frame)
        assert len(valid) == 3
        assert invalid.empty

    def test_owner_response_field_is_mapped_not_owner_reply(self):
        review = _real_tripadvisor_review("r1", "Text", 5)
        review["owner_response"] = "Thanks for visiting!"

        frame = flatten_tripadvisor_reviews_response(
            [[review]],
            url_to_place_id={TRIPADVISOR_URL: PLACE_ID},
            place_id_to_name={PLACE_ID: "Ciscos Karma"},
        )

        assert frame.iloc[0]["owner_answer"] == "Thanks for visiting!"

    def test_an_unrecognised_url_is_dropped(self):
        frame = flatten_tripadvisor_reviews_response(
            _tripadvisor_sample(query="https://www.tripadvisor.co.uk/Attraction_Review-other.html"),
            url_to_place_id={TRIPADVISOR_URL: PLACE_ID},
            place_id_to_name={PLACE_ID: "Ciscos Karma"},
        )

        assert frame.empty

    def test_a_sub_ratings_field_when_present_survives_as_a_jsonb_ready_string(self):
        # No sub_ratings field was present in the real sample, but keep the
        # fallback covered in case a future response does include one.
        review = _real_tripadvisor_review("r1", "Text", 5)
        review["sub_ratings"] = {"food": 5, "service": 4, "value": 4}

        frame = flatten_tripadvisor_reviews_response(
            [[review]],
            url_to_place_id={TRIPADVISOR_URL: PLACE_ID},
            place_id_to_name={PLACE_ID: "Ciscos Karma"},
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
