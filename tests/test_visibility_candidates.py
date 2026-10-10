"""Suggestions from cited sources, review volume and leaders' review themes state their evidence and never guess."""
from datetime import date

from src.visibility_candidates import (build_visibility_candidates, leader_theme_finding, listing_candidates, own_site_candidate,
                                       review_volume_candidate)

SOURCES = {"available": True, "answers": 63, "own_answers": 0,
           "business_sites": [("Float Spa", 22), ("Luna Hut", 14), ("Tiny Rival", 1)],
           "independent": [{"domain": "visitbrighton.com", "answers": 5, "urls": ["https://visitbrighton.com/saunas"], "status": "Not found", "businesses_listed": 4},
                           {"domain": "thesaunaguide.co.uk", "answers": 6, "urls": ["https://thesaunaguide.co.uk/b"], "status": "Yes"},
                           {"domain": "findmysauna.com", "answers": 4, "urls": [], "status": "To check"},
                           {"domain": "rare.example", "answers": 2, "urls": ["https://rare.example/x"], "status": "Not found", "businesses_listed": 5},
                           {"domain": "onerival.example", "answers": 9, "urls": ["https://onerival.example/"], "status": "Not found", "businesses_listed": 1}]}
REQUIRED = {"id", "kind", "layer", "signal", "title", "observation", "why", "action", "done_when", "owner", "confidence", "score",
            "prevalence", "evidence", "hygiene", "basis"}


def test_listing_suggestions_only_for_pages_read_and_cited_often_enough():
    out = listing_candidates(SOURCES, target_name="Sauna Yard", read_on=date(2026, 10, 10))
    assert [c["id"] for c in out] == ["sources:listing:visitbrighton.com"], "unreadable, present, rarely cited and single-business sources give nothing"
    item = out[0]
    assert REQUIRED <= set(item) and item["kind"] == "action" and item["layer"] == "sources"
    assert "5 of 63 answers" in item["why"] and "name 4 of the businesses" in item["why"] and "does not show why" in item["observation"]
    assert item["evidence"] == [{"business": "visitbrighton.com", "url": "https://visitbrighton.com/saunas", "read_on": "2026-10-10",
                                 "note": "Sauna Yard not found on this page"}]
    assert not item["id"].startswith("reviews:platform-"), "must not be mistaken for the retired presence action"
    assert listing_candidates({**SOURCES, "available": False}, target_name="Sauna Yard", read_on=date(2026, 10, 10)) == []


def test_own_site_suggestion_needs_zero_citations_and_other_business_sites_cited():
    item, = own_site_candidate(SOURCES, target_name="Sauna Yard")
    assert "0 of 63 answers" in item["why"] and "Float Spa (22), Luna Hut (14)" in item["why"] and "Tiny Rival" not in item["why"]
    assert "We have not established why" in item["observation"] and item["confidence"] == "Low"
    assert own_site_candidate({**SOURCES, "own_answers": 3}, target_name="Sauna Yard") == []
    assert own_site_candidate({**SOURCES, "business_sites": [("Tiny Rival", 1)]}, target_name="Sauna Yard") == []


def test_review_volume_uses_published_totals_and_needs_a_clear_gap():
    leaders = [{"business_name": n, "google_reviews": c} for n, c in (("A", "100.0"), ("B", "120"), ("C", 43), ("D", None))]
    item, = review_volume_candidate(target_name="Sauna Yard", target_reviews="12", leaders=leaders)
    assert "Google shows 12 reviews" in item["why"] and "median of 100" in item["why"] and "B 120, A 100, C 43" in item["why"]
    assert "have not been shown to cause" in item["observation"] and item["layer"] == "reviews" and item["kind"] == "action"
    assert review_volume_candidate(target_name="X", target_reviews="60", leaders=leaders) == [], "over half the median is not a clear gap"
    assert review_volume_candidate(target_name="X", target_reviews=None, leaders=leaders) == [], "an unknown total is not zero"
    assert review_volume_candidate(target_name="X", target_reviews="1", leaders=leaders[:2]) == [], "too few leaders to compare"


def test_leader_themes_are_shares_of_reviews_beside_the_clients_own():
    reviews = ([{"google_place_id": "L1", "review_text": "Such friendly staff"}] * 15 + [{"google_place_id": "L2", "review_text": "Lovely views and friendly team"}] * 10
               + [{"google_place_id": "other", "review_text": "friendly"}] * 50 + [{"google_place_id": "me", "review_text": "Great views"}] * 4
               + [{"google_place_id": "L1", "review_text": "  "}])
    themes = [("Friendly people", ["friendl"]), ("Views", ["views"]), ("Parking", ["parking"])]
    item, = leader_theme_finding(target_id="me", target_name="Sauna Yard", leader_ids=["L1", "L2"], reviews=reviews, themes=themes)
    assert item["kind"] == "finding" and item["id"] == "reviews:leader-themes"
    assert "Across 25 Google reviews of the 2 most visible businesses" in item["observation"]
    assert "friendly people (100%); views (40%)" in item["observation"] and "parking" not in item["observation"]
    assert "In Sauna Yard's 4 reviews: friendly people (0%); views (100%)" in item["observation"]
    assert leader_theme_finding(target_id="me", target_name="X", leader_ids=["L2"], reviews=reviews, themes=themes) == [], "too few leader reviews"


def test_all_suggestions_together_have_unique_ids_and_the_fields_step_five_needs():
    leaders = [{"google_place_id": f"L{n}", "business_name": f"Leader {n}", "google_reviews": 100} for n in range(3)]
    reviews = [{"google_place_id": "L0", "review_text": "friendly staff"}] * 30
    out = build_visibility_candidates(sources=SOURCES, target_id="me", target_name="Sauna Yard", target_reviews="12", leaders=leaders,
                                      reviews=reviews, themes=[("Friendly people", ["friendl"])], read_on=date(2026, 10, 10))
    assert [c["id"] for c in out] == ["sources:own-site", "sources:listing:visitbrighton.com", "reviews:volume", "reviews:leader-themes"]
    assert all(REQUIRED <= set(c) for c in out)
