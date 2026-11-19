"""Scan-time name matching: which known businesses an answer names (WRAP's November test).

Plain text matching credited listings called "Brighton", "Village", "Here" and "The Space" with nearly every answer,
and "STRONG Brighton" with the phrase "a strong Brighton feel".
"""

from src.ai_visibility_analysis import analyse_visibility_response, name_aliases


def _named(text, businesses, *, target=("target-id", "Target Business Ltd"), location=None):
    known = [{"google_place_id": target[0], "business_name": target[1]}] + [
        {"google_place_id": f"id-{index}", "business_name": name} for index, name in enumerate(businesses)
    ]
    result = analyse_visibility_response(
        response_text=text,
        target_google_place_id=target[0],
        target_business_name=target[1],
        known_businesses=known,
        location_context=location,
    )
    return result, {item["business_name"] for item in result["mentioned_competitors"]}


def test_place_word_listing_is_not_named_by_the_place():
    _, named = _named(
        "Here are some options in Brighton:\n1. **Hotel Pelirocco** - a quirky choice.",
        ["Brighton", "Hotel Pelirocco"],
        location="Brighton and Hove",
    )
    assert named == {"Hotel Pelirocco"}


def test_place_word_listing_is_not_named_by_an_area_heading():
    _, named = _named("### Brighton\n- **Hove Village Day Nursery**: flexible hours.", ["Brighton"], location="Brighton, Hove")
    assert named == set()


def test_ordinary_words_do_not_name_one_word_listings():
    _, named = _named(
        "Here is a village feel in a creative space with a strong Brighton vibe and a pod for calls.",
        ["Here", "Village", "The Space", "POD", "STRONG Brighton", "The Point"],
    )
    assert named == set()


def test_one_word_name_inside_a_longer_name_does_not_count():
    _, named = _named("1. **Hove Village Day Nursery** - open 51 weeks.", ["Village", "Hove Village Day Nursery"])
    assert named == {"Hove Village Day Nursery"}


def test_one_word_name_counts_when_presented_as_a_name():
    _, listed = _named("1. **Funplex** - soft play for under-fives.", ["Funplex"])
    _, bold = _named("For parties, **Funplex** has party rooms.", ["Funplex"])
    _, bullet = _named("- Honeycroft: a creche for weddings", ["Honeycroft"])
    assert listed == {"Funplex"} and bold == {"Funplex"} and bullet == {"Honeycroft"}


def test_one_word_name_in_plain_prose_does_not_count_unless_spelt_distinctively():
    _, plain = _named("Many parents like Funplex for parties.", ["Funplex"])
    _, distinctive = _named("PLATF9RM and WRAP both offer desks.", ["PLATF9RM", "WRAP"])
    _, wrong_case = _named("Wrap up warm and bring a pod.", ["POD", "WRAP"])
    assert plain == set()
    assert distinctive == {"PLATF9RM", "WRAP"}
    assert wrong_case == set()


def test_multi_word_name_must_be_written_with_capitals():
    _, named = _named(
        "It has a strong brighton feel. STRONG Brighton is a gym. The Library Café is nearby.",
        ["STRONG Brighton", "The Library Cafe"],
    )
    assert named == {"STRONG Brighton", "The Library Cafe"}


def test_lower_case_multi_word_phrase_does_not_count():
    _, named = _named("a strong brighton feel and the library cafe vibe", ["STRONG Brighton", "The Library Cafe"])
    assert named == set()


def test_apostrophes_ampersands_and_accents_still_match():
    _, named = _named(
        "1. **Cisco's Karma** - salon\nTry Gin & Juice, or Café Rouge Brighton.",
        ["Ciscos Karma", "Gin and Juice", "Cafe Rouge Brighton"],
    )
    assert named == {"Ciscos Karma", "Gin and Juice", "Cafe Rouge Brighton"}


def test_the_prefix_alias_needs_two_words_left():
    assert "space" not in name_aliases("The Space")
    assert "ginger pig" in name_aliases("The Ginger Pig")


def test_target_keeps_plain_matching_for_its_one_word_name():
    result, _ = _named("Funplex is the best soft play in town.", [], target=("t", "Funplex"))
    assert result["target_mentioned"] and not result["target_recommended"]


def test_target_in_lower_case_prose_is_not_named():
    result, _ = _named("you could wrap presents there", [], target=("t", "Wrap"))
    assert not result["target_mentioned"]


def test_recommendation_position_still_found_for_a_listed_one_word_name():
    result, _ = _named("1. **Hotel Pelirocco** - quirky\n2. **Funplex** - soft play", ["Hotel Pelirocco", "Funplex"])
    positions = {item["business_name"]: item["recommendation_position"] for item in result["mentioned_competitors"]}
    assert positions == {"Hotel Pelirocco": 1, "Funplex": 2}


def test_presented_name_with_the_place_added_still_counts():
    _, named = _named("1. **Honeycroft Hove** - creche for events", ["Honeycroft"], location="Brighton and Hove")
    assert named == {"Honeycroft"}


def test_name_with_a_digit_matches_in_any_case():
    _, named = _named("Time2Shine Cleaning is well reviewed.", ["Time2shine"])
    assert named == {"Time2shine"}
