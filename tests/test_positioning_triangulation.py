"""Do not turn unknown provenance, repeated excerpts or run context into positioning facts."""
from copy import deepcopy

import pytest

from src.positioning_triangulation import triangulate, TriangulationRules
from src.proposition_catalog import starter_catalogue
from src.public_evidence_archive import build_capture, validate_decision
from src.report_priorities import NOT_LINKED


def inputs():
    catalogue, aliases = starter_catalogue()
    business = {"google_place_id": "place", "business_name": "Synthetic salon"}
    bundle = {"business": business, "listing": None, "audit": None, "pages": [], "platform_links": [], "checks": {},
              "reviews": [{"id": f"row-{i}", "google_place_id": "place", "source": "outscraper_google_reviews",
                           "review_id": str(i), "review_text": "I love my balayage. My balayage looks lovely."} for i in range(2)]}
    cap = {"id": "00000000-0000-0000-0000-000000000001", **build_capture(bundle, catalogue, aliases)}
    brief = {"id": "owner-1", "target_google_place_id": "place", "known_for": "Unknown free text",
             "owner_context": {"priority_services": ["Balayage"]}}
    run = {"id": "run-1", "target_google_place_id": "place", "target_propositions": ["Balayage"]}
    questions = [{"base_prompt_order": 1, "prompt_text": "Where can I get balayage?"}]
    return cap, brief, run, questions


def reviews(cap, choice="EXPLICIT_SUPPORT", origin="customer_report"):
    return [{"id": f"decision-{i}", "capture_id": cap["id"], "revision": 1,
             **validate_decision(cap, evidence_id=o["evidence_id"], decision=choice, origin=origin,
                                 reviewer="Synthetic operator", note="Read exact source context", identity_confirmed=True)}
            for i, o in enumerate(cap["payload"]["matrix"]["observations"]) if o["kind"] == "proposition_candidate"]


def row(view):
    return next(r for r in view["rows"] if r["proposition_key"] == "balayage")


def test_unknown_reviews_and_context_do_not_make_zero_or_tested_intent():
    cap, brief, run, questions = inputs()
    view = triangulate(cap, [], owner_brief=brief, run=run, questions=questions)
    r = row(view)
    assert r["owner_intended"] is True and r["tested"] is None
    assert r["customer_support_records"] is None and r["suggestion"] == "NEEDS_REVIEW"
    assert view["tested_intent"]["run_context"][0]["proposition_key"] == "balayage"


def test_strategic_core_counts_records_not_repeated_sentences_or_repeats():
    cap, brief, run, questions = inputs()
    view = triangulate(cap, reviews(cap), owner_brief=brief, run=run, questions=questions * 3,
                       confirmed_question_map={"1": "Balayage"})
    r = row(view)
    assert r["customer_support_records"] == 2 and r["customer_source_classes"] == 1
    assert r["question_orders"] == ["1"] and r["suggestion"] == "STRATEGIC_CORE"
    assert len(r["decision_ids"]) == 4


def test_unmapped_questions_block_a_negative_tested_claim():
    cap, brief, run, questions = inputs()
    view = triangulate(cap, reviews(cap), owner_brief=brief, run=run, questions=questions,
                       confirmed_question_map={"1": "Unrecognised priority"})
    assert row(view)["tested"] is None and not view["question_mapping_complete"]
    view = triangulate(cap, reviews(cap), owner_brief=brief, run=run, questions=questions,
                       confirmed_question_map={"1": NOT_LINKED})
    assert row(view)["tested"] is False and row(view)["suggestion"] == "HIDDEN_STRENGTH"


def test_missing_owner_brief_and_unresolved_owner_label_remain_unknown():
    cap, brief, run, questions = inputs()
    view = triangulate(cap, reviews(cap))
    assert row(view)["owner_intended"] is None and row(view)["suggestion"] == "CUSTOMER_STRENGTH"
    brief["owner_context"]["priority_services"] = ["Balayag"]
    view = triangulate(cap, reviews(cap), owner_brief=brief)
    assert row(view)["owner_intended"] is None and view["owner_priorities"][0]["resolution"] == "unresolved"


@pytest.mark.parametrize("origin", ["owner_claim", "syndicated_claim", "independent_third_party"])
def test_noncustomer_origins_never_become_customer_strength(origin):
    cap, _, _, _ = inputs()
    r = row(triangulate(cap, reviews(cap, origin=origin)))
    assert r["suggestion"] == "NEEDS_REVIEW" and r["customer_support_records"] is None


def test_unconfirmed_no_support_cannot_become_unproven_ambition():
    cap, brief, _, _ = inputs()
    decisions = reviews(cap, choice="NO_SUPPORT", origin="unknown")
    for d in decisions: d["identity_confirmed"] = False
    r = row(triangulate(cap, decisions, owner_brief=brief))
    assert r["customer_support_records"] is None and r["suggestion"] == "NEEDS_REVIEW"


def test_reviewed_customer_origin_is_distinct_from_the_hosting_source_class():
    cap, _, _, _ = inputs()
    bundle = deepcopy(cap['payload']['source_bundle'])
    bundle['reviews'] = []
    bundle['audit'] = {'id':'audit', 'google_place_id':'place', 'audit_status':'completed'}
    bundle['pages'] = [{'id':f'page-{i}', 'audit_run_id':'audit', 'http_status':200,
                        'text_excerpt':'I love my balayage.'} for i in range(2)]
    catalogue, aliases = starter_catalogue()
    cap = {'id':cap['id'], **build_capture(bundle, catalogue, aliases)}
    # A human must establish testimonial origin from context; hosting on a website alone is insufficient.
    r = row(triangulate(cap, reviews(cap, origin='customer_report')))
    assert r['customer_support_records'] == 2 and r['suggestion'] == 'CUSTOMER_STRENGTH'
    assert row(triangulate(cap, reviews(cap, origin='owner_claim')))['customer_support_records'] is None


def test_thresholds_and_withdrawal_change_suggestions_without_changing_sources():
    cap, brief, run, questions = inputs()
    before = deepcopy(cap)
    decisions = reviews(cap)
    view = triangulate(cap, decisions, rules=TriangulationRules(min_customer_records=3))
    assert row(view)["suggestion"] == "NEEDS_REVIEW"
    withdrawn = [{**d, "revision": 2, "decision": "UNCERTAIN"} for d in decisions]
    assert row(triangulate(cap, [*decisions, *withdrawn]))["customer_support_records"] is None
    assert cap == before


def test_contradiction_overrides_strength_and_absence_requires_reviewed_excerpts():
    cap, brief, _, _ = inputs()
    decisions = reviews(cap)
    decisions[0]["decision"] = "CONTRADICTS"
    assert row(triangulate(cap, decisions, owner_brief=brief))["suggestion"] == "CONFLICTED_EVIDENCE"
    assert row(triangulate(cap, reviews(cap, choice="NO_SUPPORT"), owner_brief=brief))["suggestion"] == "UNPROVEN_AMBITION"
    assert row(triangulate(cap, [], owner_brief=brief))["suggestion"] == "NEEDS_REVIEW"


@pytest.mark.parametrize("kind", ["owner", "run", "decision"])
def test_cross_business_and_cross_capture_inputs_are_rejected(kind):
    cap, brief, run, questions = inputs()
    decisions = reviews(cap)
    if kind == "owner": brief["target_google_place_id"] = "other"
    elif kind == "run": run["target_google_place_id"] = "other"
    else: decisions[0]["capture_id"] = "other"
    with pytest.raises(ValueError):
        triangulate(cap, decisions, owner_brief=brief, run=run, questions=questions)


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_invalid_thresholds_cannot_weaken_support_rules(value):
    with pytest.raises(ValueError): TriangulationRules(min_customer_records=value)
