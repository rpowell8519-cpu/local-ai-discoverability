"""target_mention_summary: the target's own mention rate vs. recommendation rate.

Deliberately target-only (see the docstring on the function itself) - mentioned_known_businesses
is only reliable for whichever competitor cohort was already selected at scan time, so a
per-competitor mention table is a separate, not-yet-built piece of work, not something this
pretends to cover.

Operates on frozen responses (poc_audit_payload.freeze_ai_response's shape), reading the
parser_reconciliation block that already exists there for the RP's own consistency checks -
not a second, parallel calculation of mentioned/recommended/validity that could drift from it.
"""
from __future__ import annotations

from src.ai_recommendation_intelligence import target_mention_summary
from src.ai_visibility_analysis import analyse_visibility_response
from src.poc_audit_payload import freeze_ai_response


def _response(*, order, mentioned, recommended, excluded=False, prompt="Q text"):
    return {
        "base_prompt_order": order,
        "prompt_text": prompt,
        "parser_reconciliation": {
            "persisted_target_mentioned": mentioned,
            "persisted_target_recommended": recommended,
            "excluded_from_metrics": excluded,
        },
    }


def test_empty_responses_returns_zeroed_summary():
    summary = target_mention_summary([])
    assert summary == {"complete": 0, "mentioned": 0, "recommended": 0, "questions": []}


def test_mentioned_and_recommended_are_counted_separately():
    responses = [
        _response(order=1, mentioned=True, recommended=True),   # recommended (implies mentioned)
        _response(order=1, mentioned=True, recommended=False),  # mentioned only
        _response(order=1, mentioned=False, recommended=False), # neither
    ]
    summary = target_mention_summary(responses)
    assert summary["complete"] == 3
    assert summary["mentioned"] == 2
    assert summary["recommended"] == 1


def test_excluded_responses_are_skipped_using_the_same_flag_the_rp_already_relies_on():
    responses = [
        _response(order=1, mentioned=True, recommended=True),
        _response(order=1, mentioned=True, recommended=True, excluded=True),
    ]
    summary = target_mention_summary(responses)
    assert summary["complete"] == 1
    assert summary["mentioned"] == 1


def test_missing_parser_reconciliation_defaults_to_false_not_an_error():
    summary = target_mention_summary([{"base_prompt_order": 1, "prompt_text": "Q"}])
    assert summary == {
        "complete": 1, "mentioned": 0, "recommended": 0,
        "questions": [{"order": 1, "prompt": "Q", "complete": 1, "mentioned": 0, "recommended": 0}],
    }


def test_per_question_breakdown_is_ordered_and_independent():
    responses = [
        _response(order=2, mentioned=True, recommended=True, prompt="Second question"),
        _response(order=1, mentioned=True, recommended=False, prompt="First question"),
        _response(order=1, mentioned=False, recommended=False, prompt="First question"),
    ]
    summary = target_mention_summary(responses)
    assert [q["order"] for q in summary["questions"]] == [1, 2]
    first, second = summary["questions"]
    assert first == {"order": 1, "prompt": "First question", "complete": 2, "mentioned": 1, "recommended": 0}
    assert second == {"order": 2, "prompt": "Second question", "complete": 1, "mentioned": 1, "recommended": 1}


def test_agrees_with_the_real_freeze_and_analysis_functions_not_a_reimplementation():
    # Ground the fixture in the actual scan-time analyser and the actual freezing function,
    # rather than hand-picked reconciliation dicts, so this also catches a future change to
    # either of those shapes.
    numbered_list_hit = analyse_visibility_response(
        response_text="1. Ciscos Karma - great local salon\n2. Other Place - also good",
        target_google_place_id="place-ciscos", target_business_name="Ciscos Karma",
        known_businesses=[{"google_place_id": "place-ciscos", "business_name": "Ciscos Karma"}],
    )
    prose_only = analyse_visibility_response(
        response_text="For hair in Brighton, Ciscos Karma is worth a look alongside a few others.",
        target_google_place_id="place-ciscos", target_business_name="Ciscos Karma",
        known_businesses=[{"google_place_id": "place-ciscos", "business_name": "Ciscos Karma"}],
    )
    assert prose_only["target_mentioned"] and not prose_only["target_recommended"]

    def frozen(analysis, order):
        source = {
            "id": "r1", "query_id": "q1", "provider": "openai", "model": "m",
            "base_prompt_order": order, "prompt_category": "cat", "prompt_text": "Q",
            "repeat_index": 1, "raw_response": "text", "status": "completed",
            "response_complete": True,
        }
        return freeze_ai_response(
            source,
            parser_reconciliation={
                "persisted_target_mentioned": analysis["target_mentioned"],
                "persisted_target_recommended": analysis["target_recommended"],
                "excluded_from_metrics": False,
            },
        )

    summary = target_mention_summary([frozen(numbered_list_hit, 1), frozen(prose_only, 1)])
    assert summary["complete"] == 2
    assert summary["recommended"] == 1  # only the numbered-list answer
    assert summary["mentioned"] == 2  # both count - this is the exact gap the LS surfaces
