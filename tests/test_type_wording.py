"""AI-drafted wording for a kind of business with none of its own: checked, reviewed, and never paid for in tests."""
import json

import pytest

from src.client_summary.actions import build_actions, has_builtin_profile, profile_for
from src.evidence_analysis import analyse_evidence, select_leaders
from src.type_wording import (
    DETAILS_LIMIT, InvalidWordingError, build_prompt, draft_type_wording, parse_draft, themes_from_text, themes_to_text, to_profile,
    validate_wording,
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
    "site_checks": [
        {"label": "Gift vouchers", "page_terms": ["gift voucher", "gift card"], "url_terms": ["gift"]},
        {"label": "Private hire", "page_terms": ["private hire", "group hire"], "url_terms": ["private-hire"]},
        {"label": "Memberships", "page_terms": ["membership", "10-session pass"], "url_terms": []},
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
    ("details", "see https://example.com"),
    ("booking", "book the best in Brighton"),
])
def test_a_draft_that_invents_prices_links_or_claims_is_refused(field, value):
    with pytest.raises(InvalidWordingError):
        parse_draft(reply(**{field: value}))


def test_a_draft_that_is_merely_too_long_is_shortened_not_rejected():
    # Regression: the model drafted "details" at 176 characters against a 170 limit, and the whole
    # draft was thrown away instead of trimmed, the one field a reviewer could easily have shortened.
    wording = parse_draft(reply(details=("opening times, session types, capacity and how to book, plus gift vouchers " * 3)[:176]))
    assert len(wording["details"]) <= DETAILS_LIMIT and wording["details"].endswith("…")
    long_questions = parse_draft(reply(questions="x" * 120))["questions"]
    assert len(long_questions) == 90 and long_questions.endswith("…")


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


# ---- website checks for the type, run over pages that are already saved
import pandas as pd
from src.type_wording import site_checks_from_text, site_checks_to_text, to_audit_checks
from src.vertical_audit_profiles import get_audit_profile


def sauna_evidence():
    names = {"target": "Driftwood Sauna", "l1": "Sauna A", "l2": "Sauna B", "l3": "Sauna C"}
    F.NAMES.clear(); F.NAMES.update(names)
    audits = pd.DataFrame([F._audit(p, has_pricing_page=True, has_booking_link=True) for p in names])
    text = {"target": "Wood-fired sauna. Book a session. Prices per session.",
            "l1": "Book a session. Gift vouchers available. Private hire. Memberships.",
            "l2": "Book a session. Gift card. Group hire. 10-session pass.",
            "l3": "Book a session. Buy a gift voucher. Private hire. Membership."}
    pages = {f"run-{p}": pd.DataFrame([F._page(f"https://{p}.example/", names[p], text[p])]) for p in names}
    leaders = [{"google_place_id": p, "business_name": names[p], "recommendations": n} for p, n in (("l1", 30), ("l2", 23), ("l3", 33))]
    return audits, pages, leaders


def sauna_candidates(wording, propositions=("Sauna sessions",)):
    audits, pages, leaders = sauna_evidence()
    result = analyse_evidence(target_id="target", target_name="Driftwood Sauna", primary_group="wellness", leaders=select_leaders(leaders, "target"),
                              audits=audits, pages_by_run=pages, propositions=list(propositions), reviews=pd.DataFrame(), type_wording=wording)
    return {c["id"]: c for c in result["candidates"]}


def test_without_approved_wording_the_generic_checks_miss_what_a_sauna_customer_looks_for():
    assert not [c for c in sauna_candidates(None) if "type_check" in c]


def test_approved_topics_are_checked_on_the_saved_pages_of_the_client_and_its_leaders():
    found = sauna_candidates(validate_wording(SAUNA))
    gift, membership = found["website:type_check_gift_vouchers"], found["website:type_check_memberships"]
    assert gift["prevalence"] == "3 of 3" and membership["prevalence"] == "3 of 3"   # "gift card" and "10-session pass" count too
    assert "not detected on Driftwood Sauna's saved website pages" in gift["observation"]
    assert gift["title"] == "Cover “Gift vouchers” on the website" and gift["action"] and gift["done_when"]
    assert {e["business"] for e in gift["evidence"]} == {"Driftwood Sauna", "Sauna A", "Sauna B", "Sauna C"}


def test_a_topic_the_owner_already_listed_as_a_priority_is_not_recommended_twice():
    found = sauna_candidates(validate_wording(SAUNA), propositions=("Private hire",))
    assert "website:type_check_private_hire" not in found and "propositions:private hire" in found


def test_a_topic_the_client_already_covers_is_not_recommended():
    audits, pages, leaders = sauna_evidence()
    pages["run-target"] = pd.DataFrame([F._page("https://t.example/", "Driftwood", "Book a session. Gift vouchers. Memberships.")])
    result = analyse_evidence(target_id="target", target_name="Driftwood Sauna", primary_group="wellness", leaders=select_leaders(leaders, "target"),
                              audits=audits, pages_by_run=pages, propositions=[], reviews=pd.DataFrame(), type_wording=validate_wording(SAUNA))
    assert not any("gift_vouchers" in c["id"] or "memberships" in c["id"] for c in result["candidates"])


def test_the_checks_join_the_audit_profile_without_touching_the_built_in_ones():
    checks = to_audit_checks(validate_wording(SAUNA))
    assert [c["key"] for c in checks] == ["type_check_gift_vouchers", "type_check_private_hire", "type_check_memberships"]
    plain, tailored = get_audit_profile("wellness"), get_audit_profile("wellness", extra_checks=checks)
    assert len(tailored["checks"]) == len(plain["checks"]) + 3 and tailored["checks"][: len(plain["checks"])] == plain["checks"]


@pytest.mark.parametrize("checks", [
    [{"label": "Gift vouchers", "page_terms": ["gift voucher"], "url_terms": []}],                      # too few phrases
    [{"label": "Gift vouchers", "page_terms": ["gift voucher", "see www.x.com"], "url_terms": []}],     # a link
    [{"label": "Gift vouchers", "page_terms": ["gift voucher", "gift card"], "url_terms": []}] * 2,     # duplicate topic
])
def test_website_topics_that_break_the_rules_are_refused(checks):
    with pytest.raises(InvalidWordingError):
        validate_wording({**SAUNA, "site_checks": checks})


def test_the_topic_editor_round_trips_and_explains_a_malformed_line():
    checks = validate_wording(SAUNA)["site_checks"]
    assert [c["label"] for c in site_checks_from_text(site_checks_to_text(checks))] == ["Gift vouchers", "Private hire", "Memberships"]
    with pytest.raises(InvalidWordingError, match="should look like"):
        site_checks_from_text("Gift vouchers")
