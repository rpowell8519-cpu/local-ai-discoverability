"""The full report (RP) built from findings: every claim cited, no invented estimates."""
from copy import deepcopy
from io import BytesIO

import pytest
from pypdf import PdfReader

from src.owner_report_findings import collect_findings
from src.owner_services_report import build_owner_report, evidence_index_html
from src.owner_services_synthetic import synthetic_owner_services_payload
from src.poc_audit_pdf import render_poc_audit_pdf

CRAWLER_GAP = {
    "id": "E1", "kind": "crawler_access", "gap": True, "blocked_labels": ["ChatGPT search", "Perplexity"],
    "observation": "robots.txt asks these AI search crawlers not to visit the site: OAI-SearchBot (ChatGPT search), PerplexityBot (Perplexity).",
    "source": "https://example.co.uk/robots.txt, read on 21 September 2026",
    "url": "https://example.co.uk/robots.txt", "checked_on": "2026-09-21",
}
CRAWLER_OK = {**CRAWLER_GAP, "gap": False, "blocked_labels": [],
              "observation": "robots.txt does not block the main AI search crawlers (ChatGPT search, Claude search, Perplexity, Google Search, Bing and Copilot)."}
ACTION_FIELDS = ("title", "need", "observation", "deliverable", "supplier", "implementer", "effort", "dependencies", "check", "refs")


def generated(*, site_findings=(), contact_phone=None, listing_phone="01273 123456", strip=True, cohort=None):
    """A synthetic payload whose report config asks for findings, as a generated report does."""
    payload = synthetic_owner_services_payload()
    config = payload["report"]["owner_report"]
    if strip:  # a generated report has no hand-written content
        for key in ("strengths", "gaps", "actions", "comparisons"):
            config[key] = []
    config.update(auto_findings=True, site_findings=[deepcopy(f) for f in site_findings],
                  listing_contact={"phone": listing_phone, "postal_code": None, "address": None})
    if contact_phone:
        audit = payload["website_evidence"]["audits"][0]
        audit["completed_at"] = "2026-09-20T10:00:00"
        audit["pages"][0]["text_excerpt"] += f" Call us on {contact_phone}."
    if cohort is not None:
        payload["diagnostic"]["cohort"] = cohort
    return payload


def build(**kwargs):
    return build_owner_report(generated(**kwargs))["config"]


def test_a_generated_report_with_no_findings_gets_strengths_and_one_honest_investigation_action():
    config = build()
    assert [a["title"] for a in config["actions"]] == ["1. Investigate the topics where the business appeared least"]
    action = config["actions"][0]
    assert "TEST" in action["refs"] and any(ref.startswith("Q") for ref in action["refs"])
    assert "do not show that a page or profile is missing information" in action["observation"]
    assert config["strengths"] and config["strengths"][0]["title"].startswith("Visible in the AI answers for")
    # No site or contact finding, so the only gap is the honest research one about comparison evidence.
    assert [g["title"] for g in config["gaps"]] == ["Comparison businesses have no saved website evidence"]


def test_every_generated_action_is_complete_cited_and_never_invents_an_estimate():
    for findings in ([], [CRAWLER_GAP], [CRAWLER_OK]):
        for action in build(site_findings=findings, contact_phone="01273 654321")["actions"]:
            assert all(action[field] for field in ACTION_FIELDS)
            assert action["effort"].startswith("Not yet estimated")
            text = " ".join(str(v) for v in action.values()).casefold()
            assert not any(word in text for word in ("guarantee", "will increase", "hours", "£"))


def test_a_blocked_crawler_is_a_cited_gap_and_the_first_action():
    payload = generated(site_findings=[CRAWLER_GAP])
    report = build_owner_report(payload)
    config = report["config"]
    assert config["actions"][0]["title"] == "1. Let AI search tools visit the website"
    assert config["actions"][1]["title"].startswith("2. Investigate")
    assert "robots.txt blocks AI search crawlers" in [g["title"] for g in config["gaps"]]
    source = report["sources"]["S1"]
    assert source["kind"] == "site_check" and source["url"] == "https://example.co.uk/robots.txt"
    assert source["date"] == "2026-09-21" and "OAI-SearchBot" in source["text"]
    crawler_gap = next(g for g in config["gaps"] if g["title"].startswith("robots.txt"))
    assert config["actions"][0]["refs"] == ["S1"] and crawler_gap["refs"] == ["S1"]
    assert "firewall or hosting rules are not visible" in config["actions"][0]["observation"]


def test_an_all_clear_crawler_check_is_a_strength_not_an_action():
    config = build(site_findings=[CRAWLER_OK])
    assert "AI search crawlers are not blocked by robots.txt" in [s["title"] for s in config["strengths"]]
    assert not any("robots" in a["title"] for a in config["actions"])


def test_a_contact_difference_cites_the_listing_and_quotes_the_saved_page_exactly():
    payload = generated(contact_phone="01273 654321")
    report = build_owner_report(payload)  # would raise if the quoted excerpt were not in the saved page
    action = next(a for a in report["config"]["actions"] if "contact details" in a["title"])
    assert any(ref.startswith("L") for ref in action["refs"]) and any(ref.startswith("W") for ref in action["refs"])
    listing = next(s for s in report["sources"].values() if s["kind"] == "listing")
    assert "01273 123456" in listing["text"]
    page_source = next(s for r, s in report["sources"].items() if r in action["refs"] and s["kind"] == "website")
    assert page_source["excerpt"] == "01273 654321" and page_source["url"]


def test_matching_contact_details_are_a_strength():
    titles = [s["title"] for s in build(contact_phone="01273 123456")["strengths"]]
    assert "The website and Google listing agree on contact details" in titles


def test_derived_references_never_reuse_ones_the_report_already_has():
    payload = generated(site_findings=[CRAWLER_GAP], contact_phone="01273 654321", strip=False)
    refs = [s["ref"] for s in payload["report"]["owner_report"]["sources"]]
    report = build_owner_report(payload)
    assert len(set(report["sources"])) == len(report["sources"]) >= len(refs) + 3


def test_comparison_businesses_without_saved_websites_are_a_research_gap_not_a_finding():
    cohort = [{"google_place_id": "someone-else", "business_name": "Other Salon"}]
    gap = next(g for g in build(cohort=cohort)["gaps"] if g["title"].startswith("Comparison businesses"))
    assert gap["refs"] == ["INVENTORY"] and "not a finding about those businesses" in gap["body"]


def test_reports_that_do_not_ask_for_findings_are_left_exactly_as_written():
    payload = synthetic_owner_services_payload()
    before = deepcopy(payload["report"]["owner_report"])
    build_owner_report(payload)
    assert payload["report"]["owner_report"] == before
    assert "auto_findings" not in payload["report"]["owner_report"]


def test_the_summary_and_the_full_report_are_built_from_the_same_findings():
    from src.client_summary.adapter import build_client_summary_report

    payload = generated(site_findings=[CRAWLER_GAP], contact_phone="01273 654321")
    summary = build_client_summary_report(payload, business_group="hair_beauty", location="X")
    report = build_owner_report(payload)
    assert [e["observation"] for e in summary["evidence"]] == [
        s["text"] for s in report["sources"].values() if s["kind"] == "site_check"
    ] + [g["body"].split(" Only the saved pages")[0] for g in report["config"]["gaps"] if "contact" in g["title"]]
    assert summary["actions"][0]["status"] == "verified_gap" and report["config"]["actions"][0]["title"].endswith("visit the website")


def test_the_rendered_report_shows_the_actions_the_sources_and_the_evidence_index():
    payload = generated(site_findings=[CRAWLER_GAP], contact_phone="01273 654321")
    reader = PdfReader(BytesIO(render_poc_audit_pdf(payload)))
    text = " ".join(" ".join(page.extract_text().split()) for page in reader.pages)
    assert "Let AI search tools visit the website" in text and "Make the contact details match everywhere" in text
    assert "S1 · robots.txt read for the AI crawler check" in text and "L1 · Google listing (saved business record)" in text
    index = evidence_index_html(payload)
    assert "Checks made by this audit" in index and "https://example.co.uk/robots.txt" in index


def test_collect_findings_orders_gaps_first_and_keeps_one_per_kind():
    payload = generated(site_findings=[CRAWLER_OK], contact_phone="01273 654321")
    found = collect_findings(payload, payload["report"]["owner_report"], "synthetic-target", extra=[CRAWLER_GAP])
    assert [f["kind"] for f in found] == ["contact_details", "crawler_access"]
    assert found[1]["gap"] is False  # the finding already in the report wins over a duplicate kind
