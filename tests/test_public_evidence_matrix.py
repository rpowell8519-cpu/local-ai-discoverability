"""Prevent observed phrases, missing samples and ambiguous facts becoming claims."""
from datetime import datetime, timezone
import re
from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.fact_consistency import compare_fact, normalize_fact
from src.proposition_catalog import starter_catalogue
from src.public_evidence_matrix import build_evidence_matrix, observation, proposition_mentions
from src.public_evidence_repository import load_public_evidence_matrix
from src.review_ingestion import SOURCE, SOURCE_YELP


def comparison(field, left, right, **options):
    return compare_fact(field, left, right, collection_status=options.pop("collection_status", "COLLECTED"),
                        complete=options.pop("complete", True), **options)["state"]


@pytest.mark.parametrize("left,right,state", [
    (["01273 123456"], ["01273 123456"], "MATCH"),
    (["01273 123456"], ["+44 1273 123456"], "SEMANTIC_MATCH"),
    (["01273 123456"], ["01273 987654"], "CONFLICT"),
    (["01273 123456"], [], "MISSING"),
    ([], ["01273 123456"], "UNKNOWN"),
    (["bad phone"], ["bad phone"], "UNKNOWN"),
    (["01273 123456"], ["01273 123456", "01273 987654"], "UNKNOWN"),
    (["01273 123456"], ["01273 123456", "+44 1273 123456"], "SEMANTIC_MATCH"),
])
def test_contact_fact_states(left, right, state):
    assert comparison("phone", left, right) == state


@pytest.mark.parametrize("status", ["NOT_CHECKED", "FAILED", "UNAVAILABLE"])
def test_uncollected_or_failed_sources_are_unknown_even_with_stale_values(status):
    assert comparison("phone", ["01273 123456"], ["01273 987654"], collection_status=status) == "UNKNOWN"


def test_partial_capture_cannot_establish_conflict_or_missing():
    assert comparison("phone", ["01273 123456"], [], complete=False) == "UNKNOWN"
    assert comparison("phone", ["01273 123456"], ["01273 987654"], complete=False) == "UNKNOWN"
    assert comparison("phone", ["01273 123456"], ["01273 123456"], complete=False) == "MATCH"
    assert comparison("phone", [], [], applicable=False) == "NOT_APPLICABLE"


def test_semantic_service_match_requires_reviewed_alias_not_fuzzy_guess():
    aliases = {"ladies cut and finish": "cut & finish"}
    assert comparison("service_name", ["Cut & Finish"], ["Ladies Cut and Finish"], aliases=aliases) == "SEMANTIC_MATCH"
    assert comparison("service_name", ["Cut & Finish"], ["Colour correction"], aliases=aliases) == "CONFLICT"


def test_price_context_and_from_qualifier_preserved():
    fixed = {"service": "Balayage", "amount": "£70"}
    assert comparison("price", [fixed], [{**fixed, "amount": "£70.00"}]) == "SEMANTIC_MATCH"
    assert comparison("price", [fixed], [{**fixed, "amount": "from £70"}]) == "UNKNOWN"
    assert comparison("price", [fixed], [{**fixed, "amount": "£80"}]) == "CONFLICT"
    assert comparison("price", [fixed], [{**fixed, "service": "Cut"}]) == "UNKNOWN"
    assert comparison("price", [fixed], [{**fixed, "amount": "$70"}]) == "UNKNOWN"
    assert normalize_fact("price", "£70") is None


def test_hours_normalization_requires_day_timezone_and_exception_context():
    hours = {"day": "Monday", "timezone": "Europe/London", "opens": "9am", "closes": "6pm"}
    assert comparison("hours", [hours], [{**hours, "opens": "09:00", "closes": "18:00"}]) == "SEMANTIC_MATCH"
    assert comparison("hours", [hours], [{**hours, "closes": "17:00"}]) == "CONFLICT"
    for change in [{"day": "Tuesday"}, {"timezone": "America/New_York"}, {"exception_date": "2026-12-25"}]:
        assert comparison("hours", [hours], [{**hours, **change}]) == "UNKNOWN"
    assert normalize_fact("hours", {**hours, "opens": "9pm", "closes": "2am"}) is None


def mentions(text):
    catalogue, aliases = starter_catalogue()
    return proposition_mentions(text, catalogue, aliases)


def test_negation_and_sentence_context_never_become_approved_support():
    found = mentions("The haircut was great. My balayage was awful. I would not recommend their bridal hair.")
    assert {m["proposition_key"] for m in found} == {"balayage", "bridal_hair"}
    assert next(m for m in found if m["proposition_key"] == "balayage")["polarity_hint"] == "negative"
    assert all(m["evidence_state"] == "REVIEW_REQUIRED" for m in found)
    assert mentions("Not only was my balayage great, the staff were lovely.")[0]["polarity_hint"] == "mixed_or_negated"
    assert mentions("The balayage was awful but my curly hair looks great.")[0]["polarity_hint"] == "negative"
    assert mentions("The balayage was awful but my curly hair looks great.")[1]["polarity_hint"] == "positive"


def test_alias_matching_does_not_use_substrings_or_fuzzy_spelling():
    assert mentions("We offer wedding hair.")[0]["proposition_key"] == "bridal_hair"
    assert mentions("Upholstry cleaning and balayageish offers") == []


def matrix(*, pages=None, reviews=None, listing=None, audit=None, checks=None, links=None):
    catalogue, aliases = starter_catalogue()
    return build_evidence_matrix(business={"google_place_id": "place-cisco", "business_name": "Cisco's Karma"},
        listing=listing, audit=audit, pages=pages or [], reviews=pd.DataFrame(reviews or []),
        platform_links=pd.DataFrame(links or []), checks=checks or {}, catalogue=catalogue, aliases=aliases)


PAGE = {"id": "page-1", "http_status": 200, "url": "https://salon.example/services",
        "crawled_at": datetime(2025, 8, 5, tzinfo=timezone.utc),
        "text_excerpt": "We offer balayage. Call 01273 123456 in BN1 1AA."}
REVIEW = {"id": "saved-review-1", "google_place_id": "place-cisco", "review_id": "review-1", "source": SOURCE,
          "review_text": "My balayage was awful. The haircut was excellent.", "review_rating": 5,
          "imported_at": datetime(2025, 8, 7, tzinfo=timezone.utc), "review_datetime_utc": datetime(2025, 8, 1, tzinfo=timezone.utc)}
LISTING = {"id": "listing-1", "created_at": datetime(2025, 8, 3, tzinfo=timezone.utc),
           "raw_data": {"phone": "+44 1273 123456", "postal_code": "BN1 1AA", "location_link": "https://maps.example/salon"}}


def test_website_only_support_is_a_traceable_candidate_not_customer_corroboration():
    result = matrix(pages=[PAGE], listing=LISTING)
    prop = result["propositions"][0]
    assert prop["website"].startswith("REVIEW_REQUIRED")
    assert prop["google_reviews"].startswith("UNKNOWN")
    assert prop["substantive_evidence_breadth"] is None
    assert result["facts"][0]["state"] == "SEMANTIC_MATCH"
    assert all(o["source_record_id"] and o["evidence_sha256"] and o["captured_at"] for o in result["observations"])


def test_review_only_and_cross_source_candidates_do_not_inflate_breadth():
    review_only = matrix(reviews=[REVIEW])
    assert review_only["propositions"][0]["candidate_source_classes"] == 1
    result = matrix(pages=[PAGE, PAGE], reviews=[REVIEW, REVIEW, {**REVIEW, "source": SOURCE_YELP}])
    assert result["propositions"][0]["candidate_source_classes"] == 3
    assert result["propositions"][0]["substantive_evidence_breadth"] is None
    assert len(result["propositions"][0]["evidence_ids"]) == 3
    negative = next(o for o in result["observations"] if o["source_class"] == "google_reviews")
    assert negative["polarity_hint"] == "negative"  # five stars are deliberately ignored
    assert negative["source_published_at"] != negative["captured_at"]


def test_checked_empty_is_separate_from_not_checked_and_from_fact_missing():
    from src.review_coverage import empty_text_check
    url = "https://yelp.example/salon"
    check = empty_text_check(source_url=url, checked_at="2025-08-01", note="Checked the linked profile; no usable text collected")
    result = matrix(checks={"place-cisco": {SOURCE_YELP: check}},
                    links=[{"google_place_id": "place-cisco", "platform": "yelp", "external_url": url}])
    collection = {c["source_class"]: c for c in result["collection"]}
    assert collection["yelp_reviews"]["collection_status"] == "CHECKED_EMPTY"
    assert collection["yelp_reviews"]["sample_size"] == 0
    assert collection["google_reviews"]["collection_status"] == "NOT_CHECKED"
    assert collection["google_reviews"]["sample_size"] is None
    assert all(f["state"] == "UNKNOWN" for f in result["facts"])


def test_latest_failed_website_and_capped_text_cannot_prove_absence():
    result = matrix(audit={"audit_status": "failed"}, listing=LISTING)
    assert result["collection"][1]["collection_status"] == "FAILED"
    result = matrix(pages=[{**PAGE, "text_excerpt": "x" * 8000}], listing=LISTING)
    assert all(f["state"] == "UNKNOWN" for f in result["facts"])


def test_restaurant_propositions_use_same_model_without_salon_assumptions():
    result = matrix(pages=[{**PAGE, "text_excerpt": "Private dining with an extensive wine list."}],
                    reviews=[{**REVIEW, "review_text": "The wine list was excellent, but private dining was disappointing."}])
    assert {p["proposition_key"] for p in result["propositions"]} == {"wine_selection", "private_dining"}
    assert all(p["candidate_source_classes"] == 2 for p in result["propositions"])
    assert all(p["substantive_evidence_breadth"] is None for p in result["propositions"])


def test_saved_review_hash_changes_with_content_and_is_platform_specific():
    kwargs = dict(place_id="place-1", source_class="google_reviews", source_record_id="review-1",
                  source_url=None, captured_at=None, kind="proposition_candidate", field="balayage")
    a = observation(**kwargs, raw_value="Lovely balayage")
    assert a == observation(**kwargs, raw_value="Lovely balayage")
    assert a["evidence_id"] != observation(**kwargs, raw_value="Awful balayage")["evidence_id"]
    assert a["evidence_id"] != observation(**{**kwargs, "source_class": "yelp_reviews"}, raw_value="Lovely balayage")["evidence_id"]
    assert a["captured_at"] is None and a["freshness"] == "capture_date_unknown"
    with pytest.raises(ValueError):
        observation(**{**kwargs, "place_id": ""}, raw_value="Lovely balayage")


def test_review_original_profile_url_survives_replaced_link_and_fallback_is_labelled():
    review = {**REVIEW, "source": SOURCE_YELP, "location_link": "https://yelp.example/original-salon"}
    links = [{"google_place_id": "place-cisco", "platform": "yelp", "external_url": "https://yelp.example/replacement-profile"}]
    result = matrix(reviews=[review], links=links)
    evidence = result['observations'][0]
    assert evidence['source_url'] == review['location_link']
    assert evidence['source_url_basis'] == 'collected_profile_url'
    result = matrix(reviews=[{**review, "location_link": None}], links=links)
    assert result['observations'][0]['source_url_basis'] == 'linked_profile_reference'
    assert evidence['adapter_version'] == 'saved-evidence-matrix-v2'


def test_repository_uses_read_only_transaction_and_latest_capture_ordering():
    engine, connection = MagicMock(), MagicMock()
    engine.connect.return_value.__enter__.return_value = connection
    connection.execute.return_value.mappings.return_value.first.return_value = None
    connection.execute.return_value.mappings.return_value.all.return_value = []
    catalogue, aliases = starter_catalogue()
    result = load_public_evidence_matrix({"google_place_id": "place-cisco", "business_name": "Cisco"}, catalogue, aliases, engine=engine)
    queries = [str(call.args[0]).lower() for call in connection.execute.call_args_list]
    assert "read only" in queries[0] and "repeatable read" in queries[0]
    assert "created_at desc, id desc" in queries[1]
    assert "started_at desc, id desc" in queries[2]
    assert not any(re.search(r"\b(?:insert|update|delete)\b", q) for q in queries)
    assert result["propositions"] == []
