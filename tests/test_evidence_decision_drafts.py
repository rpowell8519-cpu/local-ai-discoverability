"""AI drafts for excerpt decisions: the reply is checked strictly and the source fixes the origin."""
import json

import pytest

from src.evidence_decision_drafts import (BATCH, InvalidDraftError, build_prompt, draft_decisions, origin_for,
                                          parse_drafts)

EXCERPTS = [
    {"evidence_id": "e1", "topic": "Wine selection", "source_class": "google_reviews", "raw_value": "The wine list is superb."},
    {"evidence_id": "e2", "topic": "Private dining", "source_class": "website", "raw_value": "Menu  Wine  Private Dining  About Us"},
    {"evidence_id": "e3", "topic": "Wine selection", "source_class": "press", "raw_value": "A fine cellar."},
]


def reply(*decisions):
    return json.dumps([{"n": n, "decision": d, "reason": f"Reason {n}."} for n, d in enumerate(decisions, 1)])


def test_origin_comes_from_where_the_text_was_collected():
    assert (origin_for("website"), origin_for("google_reviews"), origin_for("yelp_reviews"), origin_for("press")) == \
        ("owner_claim", "customer_report", "customer_report", "unknown")


def test_prompt_numbers_each_excerpt_and_shortens_long_text():
    prompt = build_prompt([{**EXCERPTS[0], "raw_value": "wine " * 500}, EXCERPTS[1]])
    assert "1. topic: Wine selection | source: google_reviews | text: wine wine" in prompt
    assert "2. topic: Private dining | source: website | text: Menu Wine Private Dining About Us" in prompt
    assert len(prompt) < 2500


def test_valid_reply_becomes_one_draft_per_excerpt_with_fixed_origins():
    drafts = parse_drafts("Here you go:\n" + reply("explicit_support", "NO_SUPPORT", "EXPLICIT_SUPPORT"), EXCERPTS)
    assert [(d["evidence_id"], d["decision"], d["origin"]) for d in drafts] == [
        ("e1", "EXPLICIT_SUPPORT", "customer_report"), ("e2", "NO_SUPPORT", "owner_claim"),
        ("e3", "UNCERTAIN", "unknown")], "support from an unknown speaker is left for a person"
    assert drafts[0]["reason"] == "Reason 1."


@pytest.mark.parametrize("text", [
    "no json here", "{\"n\": 1}", reply("EXPLICIT_SUPPORT", "NO_SUPPORT"),
    reply("EXPLICIT_SUPPORT", "NO_SUPPORT", "GREAT"),
    json.dumps([{"n": 1, "decision": "NO_SUPPORT", "reason": "a"}] * 3),
    json.dumps([{"n": n, "decision": "NO_SUPPORT", "reason": ""} for n in (1, 2, 3)]),
    json.dumps([{"decision": "NO_SUPPORT", "reason": "a"}] * 3),
])
def test_incomplete_or_unknown_replies_are_rejected_whole(text):
    with pytest.raises(InvalidDraftError):
        parse_drafts(text, EXCERPTS)


def test_drafting_works_in_batches_and_keeps_order():
    excerpts = [{**EXCERPTS[0], "evidence_id": f"e{n}"} for n in range(BATCH + 2)]
    prompts = []

    def call(system, prompt):
        prompts.append(prompt)
        return reply(*["IMPLICIT_SUPPORT"] * (BATCH if len(prompts) == 1 else 2))

    drafts = draft_decisions(call, excerpts)
    assert len(prompts) == 2 and [d["evidence_id"] for d in drafts] == [e["evidence_id"] for e in excerpts]
