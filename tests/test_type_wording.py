"""AI-drafted wording for a kind of business with none of its own: checked, reviewed, and never paid for in tests."""
import json

import pytest

from src.client_summary.actions import build_actions, has_builtin_profile, profile_for
from src.evidence_analysis import analyse_evidence, select_leaders
from src.type_wording import (
    InvalidWordingError, build_prompt, draft_type_wording, parse_draft, themes_from_text, themes_to_text, to_profile, validate_wording,
)
from tests import evidence_fixture as F

SAUNA = {
    "label": "sauna", "booking": "book a session, a private hire or a gift voucher", "pricing": "session, group and membership prices",
    "questions": "what to bring, how hot it is, age limits and private hire", "details": "opening times, session types, capacity and how to book",
    "review_themes": [
        {"label": "Heat and steam", "category": "Experience", "terms": ["too hot", "lovely heat", "steam", "wood fired"]},
        {"label": "Cold plunge", "category": "Experience", "terms": ["cold plunge", "ice bath", "sea dip"]},
        {"label": "Booking hassle", "category": "Problems", "terms": ["could not book", "hard to book", "booking system"]},
    ],
}


def reply(**changes):
    return "Here you go:\n" + json.dumps({**SAUNA, **changes})


def test_a_good_draft_is_accepted_and_shaped_for_use():
    wording = parse_draft(reply())
    assert wording["booking"].startswith("book a session") and [t["key"] for t in wording["review_themes"]] == ["type_heat_and_steam", "type_cold_plunge", "type_booking_hassle"]


def test_the_prompt_gives_the_ai_only_the_briefing_and_forbids_inventing_facts():
    prompt = build_prompt(business_type="Sauna", known_for="wood-fired seafront sauna", priorities=["Private hire"], questions=["best sauna in Hove"])
    assert "wood-fired seafront sauna" in prompt and "Private hire" in prompt and "best sauna in Hove" in prompt
    assert "Make it obvious how to" in prompt


@pytest.mark.parametrize("field, value", [
    ("booking", "book online for £15 a session"),
    ("pricing", ""),
    ("questions", "x" * 120),
    ("details", "see https://example.com"),
    ("booking", "book the best in Brighton"),
])
def test_a_draft_that_invents_prices_links_or_claims_or_is_the_wrong_size_is_refused(field, value):
    with pytest.raises(InvalidWordingError):
        parse_draft(reply(**{field: value}))


def test_a_reply_with_no_usable_wording_or_thin_themes_is_refused():
    with pytest.raises(InvalidWordingError):
        parse_draft("Sorry, I can't help with that.")
    with pytest.raises(InvalidWordingError, match="at least 3"):
        parse_draft(reply(review_themes=[{"label": "Heat", "category": "Experience", "terms": ["hot"]}]))
    with pytest.raises(InvalidWordingError, match="category"):
        parse_draft(reply(review_themes=[{"label": "Heat", "category": "Vibes", "terms": ["hot", "steam", "warm"]}]))


def test_drafting_uses_only_the_function_it_is_given_so_tests_pay_nothing():
    seen = []
    wording = draft_type_wording(lambda system, prompt: seen.append((system, prompt)) or reply(), business_type="sauna")
    assert len(seen) == 1 and "Do not praise" in seen[0][0] and wording["label"] == "sauna"


def test_the_theme_editor_round_trips_and_explains_a_malformed_line():
    themes = validate_wording(SAUNA)["review_themes"]
    assert themes_from_text(themes_to_text(themes))[0]["label"] == "Heat and steam"
    with pytest.raises(InvalidWordingError, match="should look like"):
        themes_from_text("Heat only")


def test_an_unknown_type_uses_the_approved_wording_and_a_known_type_keeps_its_own():
    assert not has_builtin_profile("wellness") and has_builtin_profile("coworking")
    assert profile_for("wellness").booking == "enquire or book"
    assert to_profile(validate_wording(SAUNA), "wellness").booking.startswith("book a session")
    assert to_profile(None, "coworking").booking == "book a tour, a desk or a meeting room"


QUESTIONS = [{"id": "q1", "label": "Sauna in Hove", "appearances": 0, "answers": 9}, {"id": "q2", "label": "Private hire", "appearances": 5, "answers": 9}]


def test_actions_use_the_approved_wording_only_when_given_it():
    generic = build_actions(QUESTIONS, business_group="wellness")
    tailored = build_actions(QUESTIONS, business_group="wellness", profile=to_profile(validate_wording(SAUNA), "wellness"))
    assert "session types, capacity" not in " ".join(a["task"] for a in generic)
    assert "opening times, session types, capacity and how to book" in " ".join(a["task"] for a in tailored)


def test_candidate_recommendations_follow_the_approved_wording():
    def candidates(wording):
        r = analyse_evidence(target_id=F.T, target_name=F.NAMES[F.T], primary_group="wellness", leaders=select_leaders(F.leaders(), F.T),
                             audits=F.audits(), pages_by_run=F.pages_by_run(), propositions=F.PROPOSITIONS, reviews=F.reviews(), type_wording=wording)
        return {c["id"]: c for c in r["candidates"]}
    plain, tailored = candidates(None), candidates(validate_wording(SAUNA))
    assert "website:booking" in plain and "book a session" not in plain["website:booking"]["action"]
    assert "book a session, a private hire or a gift voucher" in tailored["website:booking"]["action"]
