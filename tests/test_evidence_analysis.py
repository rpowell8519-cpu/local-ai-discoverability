"""Recommendations from the client's touchpoints against the businesses doing well."""
import pandas as pd
import pytest

from src.evidence_analysis import analyse_evidence, select_leaders
from tests import evidence_fixture as F


def run(group="coworking", **over):
    args = dict(target_id=F.T, target_name=F.NAMES[F.T], primary_group=group, leaders=select_leaders(F.leaders(), F.T),
                audits=F.audits(), pages_by_run=F.pages_by_run(), propositions=F.PROPOSITIONS, reviews=F.reviews())
    args.update(over)
    return analyse_evidence(**args)


def by_id(result):
    return {c["id"]: c for c in result["candidates"]}


def test_only_businesses_the_ai_recommended_are_leaders_most_visible_first():
    pool = [*F.leaders(), {"google_place_id": "never", "business_name": "Never Recommended", "recommendations": 0},
            {"google_place_id": F.T, "business_name": F.NAMES[F.T], "recommendations": 40}]
    leaders = select_leaders(pool, F.T)
    assert [l["google_place_id"] for l in leaders] == ["l3", "l1", "l2"]            # by visibility; no client, no zero-visibility business
    assert len(select_leaders([{"google_place_id": f"x{i}", "business_name": str(i), "recommendations": i + 1} for i in range(9)], F.T)) == 5


def test_the_gaps_that_matter_are_found_from_the_real_engines():
    result = run()
    assert {"website:pricing", "website:booking", "website:faq", "propositions:team away days"} <= set(by_id(result))
    assert [k for k, v in result["layers"].items() if v["status"] == "used"] == ["website", "propositions", "reviews"]


def test_each_recommendation_states_the_numbers_and_names_the_businesses_behind_it():
    pricing = by_id(run())["website:pricing"]
    assert pricing["prevalence"] == "3 of 3"
    assert "not detected on WRAP Coworking's saved website pages" in pricing["observation"]
    for name in ("Plus X Innovation Brighton", "Runway East Brighton", "PLATF9RM Brighton"):
        assert name in pricing["observation"]
    away = by_id(run())["propositions:team away days"]
    assert away["prevalence"] == "2 of 3" and "PLATF9RM" not in away["observation"]    # only the leaders that actually cover it are named


def test_evidence_carries_the_business_the_date_read_and_the_page():
    evidence = by_id(run())["website:booking"]["evidence"]
    client, leaders = evidence[0], evidence[1:]
    assert client["business"] == "WRAP Coworking" and "not detected" in client["note"] and client["read_on"] == "2026-09-10"
    assert {e["business"] for e in leaders} == {"Plus X Innovation Brighton", "Runway East Brighton", "PLATF9RM Brighton"}
    assert all(e["read_on"] and e["url"].startswith("https://") for e in evidence)


def test_a_gap_the_leaders_do_not_show_is_not_recommended():
    ids = set(by_id(run()))
    assert "propositions:sustainable working space" not in ids   # 0 of 3 leaders cover it, so nothing to learn from them
    assert "propositions:flexible membership" not in ids
    assert "propositions:event spaces" not in ids                # only 1 of 3


def test_wording_matches_the_kind_of_business():
    workspace = by_id(run("coworking"))["website:booking"]
    pub = by_id(run("pubs"))["website:booking"]
    assert "book a tour, a desk or a meeting room" in workspace["title"]
    assert "book a table, a group or an event" in pub["title"] and workspace["title"] != pub["title"]
    assert "membership, desk and room prices" in by_id(run("coworking"))["website:pricing"]["title"]
    assert "menus and prices" in by_id(run("pubs"))["website:pricing"]["title"]


def test_structured_data_is_housekeeping_ranked_last_and_says_it_has_no_known_effect():
    result = run()
    actions = [c for c in result["candidates"] if c["kind"] == "action"]
    schema = by_id(result)["website:relevant_schema"]
    assert actions[-1]["id"] == "website:relevant_schema" and schema["hygiene"] is True and schema["confidence"] == "Low"
    assert "no evidence that it changes AI answers" in schema["action"]


def test_review_findings_are_prompts_to_look_with_the_sample_size_never_a_cause():
    findings = [c for c in run()["candidates"] if c["kind"] == "finding"]
    assert findings and all(f["action"] == "" and f["confidence"] == "Low" for f in findings)
    text = findings[0]["observation"]
    assert "sampled reviews" in text and "not as a finding about cause" in text and "Target" not in text
    assert "3 " in text and "9 reviews" in text


def test_nothing_claims_a_cause_or_promises_a_result():
    for candidate in run()["candidates"]:
        text = " ".join(str(candidate[k]) for k in ("title", "observation", "why", "action", "done_when")).casefold()
        assert not any(word in text for word in ("because", "caused", "will increase", "guarantee", "ranks higher", "boost your"))


def test_actions_come_before_findings_and_are_ordered_by_score():
    result = run()
    kinds = [c["kind"] for c in result["candidates"]]
    assert kinds == sorted(kinds, key=lambda k: k != "action")
    scores = [c["score"] for c in result["candidates"] if c["kind"] == "action"]
    assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------- when evidence is missing
def test_with_no_leaders_every_layer_says_why_it_is_unavailable():
    result = run(leaders=[])
    assert result["candidates"] == [] and {v["status"] for v in result["layers"].values()} == {"unavailable"}
    assert "no leaders to compare with" in result["layers"]["website"]["note"]


def test_a_client_with_no_website_audit_still_gets_the_review_layer():
    audits = F.audits()
    audits = audits[audits["google_place_id"] != F.T]
    result = run(audits=audits)
    assert result["layers"]["website"]["status"] == "unavailable" and "client's website has no usable saved audit" in result["layers"]["website"]["note"]
    assert result["layers"]["reviews"]["status"] == "used"


def test_leaders_without_a_saved_audit_are_left_out_and_the_report_says_how_many_were_used():
    audits = F.audits()
    audits = audits[audits["google_place_id"] != "l2"]
    result = run(audits=audits)
    assert result["layers"]["website"]["note"] == "2 of 3 leaders had a saved website audit."
    assert "Runway East Brighton" not in by_id(result)["website:pricing"]["observation"]


def test_no_review_text_makes_only_the_review_layer_unavailable():
    result = run(reviews=F.reviews(target=False))
    assert result["layers"]["reviews"]["status"] == "unavailable" and "saved: 0 for the client, 9 for the leaders" in result["layers"]["reviews"]["note"]
    assert result["layers"]["website"]["status"] == "used" and any(c["layer"] == "website" for c in result["candidates"])


def test_a_failing_engine_disables_its_layer_and_never_stops_the_rest(monkeypatch):
    import src.evidence_analysis as module

    def boom(**kwargs):
        raise RuntimeError("engine failed")
    monkeypatch.setattr(module, "build_review_benchmark", boom)
    result = run()
    assert result["layers"]["reviews"]["status"] == "unavailable" and "could not be completed (RuntimeError)" in result["layers"]["reviews"]["note"]
    assert result["layers"]["website"]["status"] == "used" and result["candidates"]


def test_no_owner_priorities_means_no_proposition_recommendations():
    result = run(propositions=[])
    assert result["layers"]["propositions"]["status"] == "unavailable"
    assert not any(c["layer"] == "propositions" for c in result["candidates"])


def test_leaders_are_reported_with_when_their_site_was_read_and_how_many_reviews_exist():
    leaders = {l["google_place_id"]: l for l in run()["leaders"]}
    assert leaders["l1"]["website_read"] == "2026-09-08" and leaders["l1"]["reviews"] == 3 and leaders["l1"]["recommendations"] == 30
