import pytest

from src.business_lookup import looks_like_place_id, near_misses, search_businesses

RECORDS = [
    {"google_place_id": "ChIJwrap0000000000000000001", "business_name": "WRAP- Coworking, Meeting Rooms & Offices", "city": "Brighton", "address": "1 Test St, Brighton BN1 4EA"},
    {"google_place_id": "ChIJplusx000000000000000002", "business_name": "Plus X Innovation Brighton", "city": "Brighton", "address": "Ditchling Rd"},
    {"google_place_id": "ChIJskiff000000000000000003", "business_name": "The Skiff", "city": "Brighton", "address": "Cheapside"},
    {"google_place_id": "ChIJleeds000000000000000004", "business_name": "The Skiff Leeds", "city": "Leeds", "address": "Call Lane"},
    {"google_place_id": "ChIJkeys0000000000000000005", "business_name": "Captain Keys Cafe", "city": "Hove", "address": None},
]


def names(found):
    return [r["business_name"] for r in found]


def test_a_short_brand_name_finds_the_long_google_listing():
    assert names(search_businesses(RECORDS, "wrap")) == ["WRAP- Coworking, Meeting Rooms & Offices"]
    assert names(search_businesses(RECORDS, "WRAP Coworking")) == ["WRAP- Coworking, Meeting Rooms & Offices"]


def test_exact_and_prefix_matches_rank_above_looser_ones():
    assert names(search_businesses(RECORDS, "the skiff")) == ["The Skiff", "The Skiff Leeds"]


def test_a_town_narrows_the_search():
    assert names(search_businesses(RECORDS, "skiff leeds")) == ["The Skiff Leeds"]
    assert names(search_businesses(RECORDS, "skiff brighton")) == ["The Skiff"]


def test_a_partial_word_matches():
    assert names(search_businesses(RECORDS, "cowork")) == ["WRAP- Coworking, Meeting Rooms & Offices"]


def test_capitals_punctuation_and_spacing_do_not_matter():
    assert names(search_businesses(RECORDS, "  CAPTAIN   keys!  ")) == ["Captain Keys Cafe"]


def test_a_business_that_is_not_there_finds_nothing():
    assert search_businesses(RECORDS, "Definitely Not A Real Place") == []
    assert search_businesses(RECORDS, "") == [] and search_businesses(RECORDS, "   ") == []
    assert search_businesses(RECORDS, "!!!") == []


def test_a_pasted_place_id_matches_exactly_and_only_that_business():
    found = search_businesses(RECORDS, "ChIJplusx000000000000000002")
    assert names(found) == ["Plus X Innovation Brighton"]
    assert search_businesses(RECORDS, "ChIJnotinthedatabase00000000") == []


@pytest.mark.parametrize("value,expected", [
    ("ChIJplusx000000000000000002", True), ("ChIJ N2 spaces 0000000000000000", False), ("wrap", False), ("", False), (None, False),
])
def test_place_id_detection(value, expected):
    assert looks_like_place_id(value) is expected


def test_a_typo_gets_a_suggestion_but_is_not_treated_as_a_match():
    assert search_businesses(RECORDS, "Captain Kees Cafe") == []
    assert names(near_misses(RECORDS, "Captain Kees Cafe")) == ["Captain Keys Cafe"]


def test_a_brand_typo_reaches_the_long_listing_through_its_brand_name():
    assert names(near_misses(RECORDS, "wrapp")) == ["WRAP- Coworking, Meeting Rooms & Offices"]


def test_actual_matches_are_not_repeated_as_suggestions():
    assert near_misses(RECORDS, "wrap") == []


def test_unrelated_text_gets_no_suggestions():
    assert near_misses(RECORDS, "Zebra Quantum Laundromat") == []


def test_results_are_limited():
    many = [{"google_place_id": f"ChIJ{n:024d}", "business_name": f"Salon {n}", "city": "X", "address": None} for n in range(60)]
    assert len(search_businesses(many, "salon", limit=25)) == 25
