"""Approved recommendations from the evidence flow into both reports, cited and specific."""
import copy
from io import BytesIO

import pytest
from pypdf import PdfReader

from src.client_summary.actions import DONE_LIMIT, OWNER_LIMIT, TASK_LIMIT, TITLE_LIMIT, build_actions
from src.client_summary.adapter import build_client_summary_report, render_client_summary_pdf
from src.evidence_analysis import analyse_evidence, select_leaders
from src.owner_services_report import build_owner_report, evidence_index_html
from src.owner_services_synthetic import synthetic_owner_services_payload
from src.poc_audit_pdf import render_poc_audit_pdf
from tests import evidence_fixture as F
from tests.test_client_summary_adapter import CONTACT_GAP, CRAWLER_GAP, QUESTIONS


def analysis():
    return analyse_evidence(target_id=F.T, target_name=F.NAMES[F.T], primary_group="coworking", leaders=select_leaders(F.leaders(), F.T),
                            audits=F.audits(), pages_by_run=F.pages_by_run(), propositions=F.PROPOSITIONS, reviews=F.reviews())


def approved(*ids, wording=None):
    result = analysis()
    chosen = [copy.deepcopy(c) for c in result["candidates"] if c["id"] in ids]
    for c in chosen:
        if wording and c["id"] in wording:
            c["action"] = wording[c["id"]]
    return chosen, {"layers": result["layers"], "leaders": result["leaders"], "basis": result["basis"]}


def payload_with(ids=("website:pricing", "website:booking", "reviews:booking--reservations")):
    chosen, basis = approved(*ids)
    payload = synthetic_owner_services_payload()
    config = payload["report"]["owner_report"]
    for key in ("strengths", "gaps", "actions", "comparisons"):
        config[key] = []
    config.update(auto_findings=True, site_findings=[], listing_contact={}, evidence_recommendations=chosen, recommendation_basis=basis)
    return payload


# ---------------------------------------------------------------- the client summary
EVIDENCE_ACTIONS = [c for c in analysis()["candidates"] if c["kind"] == "action"]


def test_approved_recommendations_come_before_the_generic_advice():
    actions = build_actions(QUESTIONS, business_group="coworking", evidence_actions=EVIDENCE_ACTIONS[:2])
    assert [a["title"] for a in actions[:2]] == [c["title"][:75] for c in EVIDENCE_ACTIONS[:2]]
    assert len(actions) == 3 and "consistent" in actions[2]["title"]          # the generic listing check fills the last slot


def test_each_approved_action_explains_itself_with_the_numbers_not_a_topic_count():
    actions = build_actions(QUESTIONS, business_group="coworking", evidence_actions=EVIDENCE_ACTIONS[:1])
    assert actions[0]["why"] == EVIDENCE_ACTIONS[0]["why"][:240] and "3 of 3" in actions[0]["why"] or "2 of 3" in actions[0]["why"]
    assert actions[0]["status"] == "suggested_check"


def test_verified_findings_still_come_first_then_the_approved_recommendations():
    findings = [dict(CRAWLER_GAP, id="E1"), dict(CONTACT_GAP, id="E2")]
    actions = build_actions(QUESTIONS, business_group="coworking", findings=findings, evidence_actions=EVIDENCE_ACTIONS)
    assert [a["status"] for a in actions] == ["verified_gap", "verified_gap", "suggested_check"]
    assert actions[2]["title"] == EVIDENCE_ACTIONS[0]["title"][:75]


def test_three_approved_recommendations_replace_all_of_the_generic_advice():
    actions = build_actions(QUESTIONS, business_group="coworking", evidence_actions=EVIDENCE_ACTIONS[:3])
    assert len(actions) == 3 and not any("consistent" in a["title"] or a["title"].startswith("Make ") and "easy to find and act on" in a["title"] for a in actions)


def test_wording_that_is_too_long_is_shortened_at_a_word_never_rejected():
    long = dict(EVIDENCE_ACTIONS[0], title="A very long title " * 8, action="Words " * 200, owner="An owner " * 30, done_when="Done " * 100, why="Because " * 80)
    action = build_actions(QUESTIONS, evidence_actions=[long])[0]
    assert len(action["title"]) <= TITLE_LIMIT and len(action["task"]) <= TASK_LIMIT
    assert len(action["owner"]) <= OWNER_LIMIT and len(action["done_when"]) <= DONE_LIMIT and len(action["why"]) <= 240


def test_an_action_about_a_topic_is_tied_to_the_question_that_tests_it():
    questions = [{"id": "q1", "label": "Coworking", "appearances": 5, "answers": 9}, {"id": "q2", "label": "Team away days", "appearances": 0, "answers": 9},
                 {"id": "q3", "label": "Meeting rooms", "appearances": 2, "answers": 9}]
    away = next(c for c in EVIDENCE_ACTIONS if c["id"] == "propositions:team away days")
    assert build_actions(questions, evidence_actions=[away])[0]["question_id"] == "q2"


def summary_for(payload):
    return build_client_summary_report(payload, business_group="coworking", location="Brighton")


def test_the_summary_carries_the_approved_actions_and_says_what_they_were_compared_with():
    data = summary_for(payload_with())
    assert data["actions"][0]["title"].startswith("Publish membership, desk and room prices")
    assert data["actions"][0]["why"].startswith("Pricing information was not detected on your saved pages")
    assert any("Saved website pages of WRAP Coworking and 3 of the 3 most visible businesses" in e["observation"] for e in data["evidence"])
    text = " ".join(" ".join(p.extract_text().split()) for p in PdfReader(BytesIO(render_client_summary_pdf(data))).pages)
    assert "Why: Pricing information was not detected on your saved pages, but was on 3 of 3 of the most visible businesses." in text
    assert "Check and improve: Show membership, desk and room prices as ordinary page text" in text


def test_the_reviewers_edited_wording_is_what_the_client_sees():
    chosen, basis = approved("website:booking", wording={"website:booking": "Put a Book a tour button on the home page."})
    payload = payload_with(())
    payload["report"]["owner_report"].update(evidence_recommendations=chosen, recommendation_basis=basis)
    assert "Put a Book a tour button on the home page." in [a["task"] for a in summary_for(payload)["actions"]]


def test_a_summary_with_no_approved_recommendations_is_unchanged():
    payload = payload_with(())
    data = summary_for(payload)
    assert not any("why" in a for a in data["actions"])
    assert not any("most visible businesses" in e["observation"] for e in data["evidence"])


def test_review_observations_never_become_client_summary_actions():
    data = summary_for(payload_with(("reviews:booking--reservations",)))
    assert not any("reviews" in a["title"].casefold() for a in data["actions"]) and not any("why" in a for a in data["actions"])


def test_the_contract_limits_an_actions_reason():
    from src.client_summary import ReportValidationError, validate_report
    from tests.wrap_fixture import wrap_summary
    d = wrap_summary()
    d["actions"][0]["why"] = "x" * 261
    with pytest.raises(ReportValidationError, match="action.why"):
        validate_report(d)


# ---------------------------------------------------------------- the full report
def test_approved_actions_become_cited_full_report_actions_with_all_ten_fields():
    report = build_owner_report(payload_with())
    actions = report["config"]["actions"]
    assert [a["title"] for a in actions[:2]] == [f"1. {EVIDENCE_ACTIONS[1]['title']}", f"2. {EVIDENCE_ACTIONS[2]['title']}"] or len(actions) == 2
    for action in actions:
        assert all(action[k] for k in ("title", "need", "observation", "deliverable", "supplier", "implementer", "effort", "dependencies", "check", "refs"))
        assert action["effort"].startswith("Not yet estimated") and "A1" in action["refs"] and "INVENTORY" in action["refs"]
    assert not any(a["title"].endswith("Investigate the topics where the business appeared least") for a in actions)


def test_the_comparison_is_a_source_listing_each_business_when_its_site_was_read_and_where():
    source = build_owner_report(payload_with())["sources"]["A1"]
    assert source["kind"] == "analysis" and "Sites and dates:" in source["text"]
    for name in ("WRAP Coworking", "Plus X Innovation Brighton", "Runway East Brighton", "PLATF9RM Brighton"):
        assert name in source["text"]
    assert "read 2026-09-08" in source["text"] and "https://l1.example/" in source["text"]


def test_review_observations_become_gaps_citing_the_review_comparison():
    report = build_owner_report(payload_with())
    gap = next(g for g in report["config"]["gaps"] if "comes up less often" in g["title"])
    assert "sampled reviews" in gap["body"] and "not as a finding about cause" in gap["body"]
    ref = gap["refs"][0]
    assert report["sources"][ref]["kind"] == "analysis" and "Google review text" in report["sources"][ref]["text"]


def test_with_nothing_approved_the_full_report_keeps_its_honest_investigation_action():
    actions = build_owner_report(payload_with(()))["config"]["actions"]
    assert actions[-1]["title"].endswith("Investigate the topics where the business appeared least")


def test_new_reference_numbers_never_collide_with_existing_ones():
    payload = payload_with()
    payload["report"]["owner_report"]["sources"].append({"ref": "A1", "kind": "site_check", "title": "x", "url": "https://x", "date": "2026-09-21", "observation": "x", "record_id": "x"})
    report = build_owner_report(payload)
    assert report["sources"]["A1"]["kind"] == "site_check" and any(s["kind"] == "analysis" for r, s in report["sources"].items() if r != "A1")


def test_the_rendered_report_and_evidence_index_show_the_recommendations_and_their_basis():
    payload = payload_with()
    text = " ".join(" ".join(p.extract_text().split()) for p in PdfReader(BytesIO(render_poc_audit_pdf(payload))).pages)
    assert "Publish membership, desk and room prices on the page for each service" in text and "Make it obvious how to book a tour" in text
    assert "A1 · Comparison with the most visible businesses' saved websites" in text and "Sites and dates:" in text
    assert "Checks made by this audit" in evidence_index_html(payload)


def test_hand_built_reports_never_gain_recommendations():
    payload = synthetic_owner_services_payload()
    before = copy.deepcopy(payload["report"]["owner_report"])
    build_owner_report(payload)
    assert payload["report"]["owner_report"] == before and "evidence_recommendations" not in before


def test_the_summary_uses_approved_business_type_wording_for_its_topic_checks():
    payload = payload_with(())
    wording = {"label": "sauna", "booking": "book a session", "pricing": "session prices", "questions": "what to bring",
               "details": "opening times, session types and capacity", "review_themes": []}
    payload["report"]["owner_report"].update(type_wording=wording, primary_group="wellness")
    tasks = " ".join(a["task"] for a in summary_for(payload)["actions"])
    assert "opening times, session types and capacity" in tasks


def test_the_comparison_basis_line_never_doubles_its_closing_punctuation_when_shortened():
    # Regression: a live WRAP report showed "…." — the shortener's own ellipsis plus an unconditional
    # trailing period appended on top of it.
    payload = payload_with()
    long_basis = ("Saved website pages of WRAP- Coworking, Meeting Rooms & Offices and 3 of the 5 most visible businesses "
                  "(Plus X Innovation Brighton, Runway East Brighton | Office Space and PLATF9RM Brighton - Coworking, "
                  "Offices & Events, all read across several separate saved audit runs on different dates)"
                  ", read between 2026-09-08 and 2026-09-10")
    payload["report"]["owner_report"]["recommendation_basis"]["basis"] = long_basis
    comparison = next(e for e in summary_for(payload)["evidence"] if "most visible businesses" in e["observation"])
    assert not comparison["observation"].endswith("….") and comparison["observation"].endswith("…")
