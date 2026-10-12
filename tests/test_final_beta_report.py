"""The Final Beta report restates reviewed results and adds mentions, an earlier test, sources and reviews."""
import io
from datetime import date

import pytest

from src.client_summary.adapter import build_client_summary_report
from src.final_beta_pdf import render_final_beta_pdf
from src.final_beta_report import (COMMON_THEMES, build_final_beta_report, check_coverage, count_by_question, domain_of,
                                   name_patterns, summarise_reviews, summarise_sources)
from src.owner_services_synthetic import synthetic_owner_services_payload


def answer(question, text, *, provider="OpenAI", citations=None, status="completed", measured=True):
    return {"prompt_text": question, "raw_response": text, "status": status, "response_complete": True, "provider": provider,
            "report_metadata": {"citations": citations or [], "citation_status": "measured" if measured else "unavailable"}}


def test_named_and_listed_are_counted_separately_and_a_short_name_is_case_sensitive():
    patterns = name_patterns(["Wrap.space"], "WRAP")
    rows = [answer("Q", "1. **WRAP Brighton** - coworking\n2. **Other Place** - desks"),
            answer("Q", "1. **Other Place** - desks\n\nYou could also look at WRAP, though it is further out."),
            answer("Q", "1. **Other Place** - desks\n\nTo wrap up, book a tour."),
            answer("Q", "1. **wrap.space** - listed by its website name"),
            answer("Q", "1. **WRAP** - not counted, the call failed", status="failed")]
    assert count_by_question(rows, patterns) == {"Q": {"complete": 4, "named": 3, "listed": 2}}


def test_sources_count_each_website_once_per_answer_and_split_own_business_and_independent():
    cite = lambda url, title="": {"url": url, "title": title}
    rows = [
        answer("Q", "", citations=[cite("https://www.client.example/a?utm_source=openai"), cite("https://client.example/b"),
                                   cite("https://guide.example/best"), cite("https://rival.example/")]),
        answer("Q", "", provider="Gemini", citations=[cite("https://vertexaisearch.cloud.google.com/redirect/x", "guide.example"),
                                                      cite("https://vertexaisearch.cloud.google.com/redirect/y", "uk.com")]),
        answer("Q", "", provider="Claude", citations=[cite("https://www.facebook.com/rival")]),
        answer("Q", "", provider="Claude"),
    ]
    out = summarise_sources(rows, own_domains=["https://www.client.example/"],
                            business_domains={"rival.example": "Rival Ltd", "facebook.com": "Someone"})
    assert (out["available"], out["answers"], out["answers_with_citations"], out["citations"]) == (True, 4, 3, 7)
    assert out["own_answers"] == 1 and out["own_by_provider"] == {"OpenAI": 1}
    assert out["business_sites"] == [("Rival Ltd", 1)]
    assert [(s["domain"], s["answers"]) for s in out["independent"]] == [("guide.example", 2), ("facebook.com", 1)]
    assert out["independent"][0]["urls"] == ["https://guide.example/best"], "Google's redirect links are not kept as pages"
    assert out["unnamed_citations"] == 1
    assert summarise_sources([answer("Q", "", measured=False)], own_domains=[], business_domains={})["available"] is False


def test_a_rivals_own_website_is_not_treated_as_an_independent_source():
    cite = lambda url: {"url": url, "title": ""}
    rows = [answer("Q", "", citations=[cite("https://lunahutsauna.co.uk/hire"), cite("https://www.thesaunaguide.co.uk/brighton"),
                                       cite("https://spa.example/")])]
    out = summarise_sources(rows, own_domains=[], business_domains={}, recommended_names=["Luna Hut Sauna (Sea Lanes)", "Spa"])
    assert out["business_sites"] == [("Luna Hut Sauna (Sea Lanes)", 1)]
    assert [s["domain"] for s in out["independent"]] == ["spa.example", "thesaunaguide.co.uk"], "a short or unmatched name proves nothing"


def test_coverage_is_yes_not_found_or_to_check_never_a_guess():
    patterns = name_patterns(["Client Studio"], "")
    pages = {"https://a.example/list": "<html><script>Client Studio</script>" + "filler " * 400 + "<p>Client Studio, Hove</p></html>",
             "https://b.example/list": "<html>" + "other businesses " * 200 + "</html>",
             "https://c.example/list": "<html>blocked</html>"}
    def fetch(url):
        if url.startswith("https://d."):
            raise TimeoutError
        return pages[url]
    sources = [{"domain": d + ".example", "answers": 3, "urls": [f"https://{d}.example/list"]} for d in "abcd"] + [{"domain": "e.example", "answers": 1, "urls": []}]
    assert [s["status"] for s in check_coverage(sources, patterns, fetch)] == ["Yes", "Not found", "To check", "To check", "To check"]
    assert {s["status"] for s in check_coverage(sources, patterns, None)} == {"To check"}
    listing = "<p>" + "Rival One and Rival Two (Hove) are here, with Other Place. " * 60 + "</p>"
    counted = check_coverage([{"domain": "guide.example", "answers": 4, "urls": ["https://guide.example/"]}], patterns, lambda url: listing,
                             ["Rival One", "Rival Two (Hove)", "Not There", "Spa"])
    assert (counted[0]["status"], counted[0]["businesses_listed"]) == ("Not found", 2)


def test_reviews_summary_counts_themes_ratings_recency_and_picks_a_quote():
    records = [
        {"review_id": "1", "review_text": "Such friendly staff and a lovely atmosphere. I would recommend it to anyone looking for a calm place to work.",
         "review_rating": 5, "review_datetime_utc": "2026-06-01 10:00:00"},
        {"review_id": "2", "review_text": "Helpful team, great location by the station.", "review_rating": 4, "review_datetime_utc": "2024-01-01"},
        {"review_id": "3", "review_text": "Too noisy.", "review_rating": 2, "review_datetime_utc": None},
        {"review_id": "4", "review_text": "   ", "review_rating": 5, "review_datetime_utc": "2026-07-01"},
    ]
    out = summarise_reviews(records, [(l, list(t)) for l, t in COMMON_THEMES], today=date(2026, 10, 9), google_total="158.0", google_rating="4.9")
    assert (out["read"], out["google_total"], out["five_star"], out["four_star"], out["three_or_below"]) == (3, 158, 1, 1, 1)
    assert out["recent"] == 1 and out["first"] == date(2024, 1, 1) and out["last"] == date(2026, 6, 1)
    assert out["themes"][0] == ("Friendly, helpful people", 2) and ("Location and getting there", 1) in out["themes"]
    assert out["quote"]["text"].startswith("Such friendly staff") and out["quote"]["date"] == date(2026, 6, 1)
    chosen = summarise_reviews(records, [], today=date(2026, 10, 9), quote_ids=["2"])
    assert chosen["quote"]["text"].startswith("Helpful team")
    assert summarise_reviews([], [], today=date(2026, 10, 9)) is None


def test_domain_of_handles_bare_and_prefixed_addresses():
    assert (domain_of("https://www.Example.co.uk/page"), domain_of("example.co.uk"), domain_of(None)) == ("example.co.uk", "example.co.uk", "")


@pytest.fixture(scope="module")
def synthetic():
    payload = synthetic_owner_services_payload()
    return payload, build_client_summary_report(payload)


def build(synthetic, **changes):
    payload, summary = synthetic
    values = dict(responses=list(payload["baseline_validation"]["responses"]), results=[], confirmed_names=[], today=date(2026, 10, 9))
    return build_final_beta_report(summary, **{**values, **changes})


def test_report_keeps_reviewed_counts_and_lists_untested_priorities(synthetic):
    _, summary = synthetic
    data = build(synthetic, owner_priorities=[summary["questions"][0]["label"], "Hair extensions"])
    asked = [q for q in data["questions"] if q["complete"]]
    assert data["recommended"] == sum(int(q["appearances"]) for q in summary["questions"])
    assert data["total"] == sum(int(q["complete"]) for q in summary["questions"])
    assert all(q["named"] >= q["recommended"] for q in asked), "a recommendation is also a mention"
    assert [q["label"] for q in data["questions"] if not q["complete"]] == ["Hair extensions"]
    assert data["sources"]["available"] is False and data["reviews"] is None and data["previous_date"] is None
    assert sum(p["recommended"] for p in data["providers"]) == data["recommended"]


def test_earlier_test_is_shown_only_for_questions_it_asked(synthetic):
    _, summary = synthetic
    first = summary["questions"][0]["text"]
    earlier = [answer(first, "1. **Example Salon** - colour"), answer(first, "1. **Another Salon**"), answer("A different question", "1. **Example Salon**")]
    data = build(synthetic, previous_rows=earlier, previous_date="2025-12-01")
    by_text = {q["text"]: q for q in data["questions"] if q["complete"]}
    assert by_text[first]["previous"] == {"recommended": 1, "complete": 2}
    assert all(q["previous"] is None for text, q in by_text.items() if text != first)


def test_pdf_renders_with_and_without_sources_reviews_and_actions(synthetic):
    from pypdf import PdfReader
    bare = render_final_beta_pdf(build(synthetic))
    text = " ".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(bare)).pages)
    assert "FINDINGS FOR DISCUSSION" in text and "NOT AVAILABLE FOR THIS TEST" in text and "No reviews have been read yet" in text
    assert "No actions are recommended yet" in text and "On your list" not in text and "INTERNAL" not in text
    payload, summary = synthetic
    cite = [{"url": "https://guide.example/best", "title": "Guide"}, {"url": "https://example-salon.example/", "title": "Salon"}]
    results = [{**r, "report_metadata": {"citations": cite, "citation_status": "measured"}} for r in payload["baseline_validation"]["responses"]]
    reviews = [{"review_id": str(n), "review_text": "Friendly staff and a lovely atmosphere, I would recommend this salon to everyone I know in town.",
                "review_rating": 5, "review_datetime_utc": "2026-05-01"} for n in range(12)]
    full = build(synthetic, results=results, own_domains=["example-salon.example"], review_records=reviews,
                 review_themes=[(l, list(t)) for l, t in COMMON_THEMES], fetch=lambda url: "<p>" + "Example Salon is listed here. " * 80 + "</p>",
                 approved_actions=[{"title": "Finish the bridal page", "why": "It says under construction.", "action": "Publish the service details.", "basis": "Saved page"}],
                 owner_priorities=[f"Priority {n}" for n in range(30)])
    assert full["sources"]["independent"][0]["status"] == "Yes" and full["sources"]["own_answers"] == full["total"]
    pdf = render_final_beta_pdf(full)
    reader = PdfReader(io.BytesIO(pdf))
    text = " ".join(page.extract_text() or "" for page in reader.pages)
    assert "Finish the bridal page" in text and "guide.example" in text and "12 reviews read" in text
    assert "(CONTINUED)" in text, "a long brief continues on a further page instead of overflowing"
    assert f"/ {len(reader.pages):02d}" in text


def test_actions_with_the_same_title_are_merged_and_listings_already_actioned_are_not_repeated(synthetic):
    from src.final_beta_report import things_to_investigate
    approved = [{"title": "Publish prices", "why": "Pricing was not detected.", "action": "Show prices as text.", "basis": "Saved pages.", "signal": "pricing"},
                {"title": "Publish  prices", "why": "Service coverage was not detected.", "action": "Other wording", "basis": "Saved pages", "signal": "services"},
                {"title": "Check whether you can be listed on guide.example", "why": "Cited in 6.", "action": "Look.", "basis": "Cited pages", "signal": "listing:guide.example"}]
    data = build(synthetic, approved_actions=approved)
    assert [a["title"] for a in data["actions"]] == ["Publish prices", "Check whether you can be listed on guide.example"]
    assert data["actions"][0]["why"] == "Pricing was not detected. Service coverage was not detected." and data["actions"][0]["basis"] == "Saved pages"
    sources = {"independent": [{"domain": "guide.example", "status": "Not found", "businesses_listed": 4},
                               {"domain": "other.example", "status": "Not found", "businesses_listed": 3},
                               {"domain": "onerival.example", "status": "Not found", "businesses_listed": 1}]}
    lines = things_to_investigate([], sources, actioned={"listing:guide.example"})
    assert lines == ["Cited by the AI tools, but you were not found on the pages cited: other.example."]


def test_a_report_with_no_recommendations_has_no_strongest_question_tile(synthetic):
    from pypdf import PdfReader
    payload, summary = synthetic
    zero = {**summary, "questions": [{**q, "appearances": 0, "provider_appearances": {k: 0 for k in q["provider_appearances"]}} for q in summary["questions"]],
            "providers": [{**p, "appearances": 0} for p in summary["providers"]]}
    data = build_final_beta_report(zero, responses=list(payload["baseline_validation"]["responses"]), results=[], confirmed_names=[], today=date(2026, 10, 10))
    text = " ".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(render_final_beta_pdf(data))).pages)
    assert "Your strongest question" not in text and "A STARTING POINT" in text and "Questions tested" in text


def test_the_report_opens_with_a_page_explaining_the_test_in_the_business_own_figures(synthetic):
    from pypdf import PdfReader
    data = build(synthetic, owner_priorities=["Colour", "Bridal hair"])
    pages = [" ".join((page.extract_text() or "").split()) for page in PdfReader(io.BytesIO(render_final_beta_pdf(data))).pages]
    assert "What AI visibility means" in pages[1] and "Colour, Bridal hair" in pages[1]
    assert f"{data['total']} answers overall" in pages[1] and data["questions"][0]["text"] in pages[1]
    assert "03 / WHERE YOU APPEAR" in pages[2] and "REFERENCE / 09" in pages[-1]


def test_reviews_are_set_beside_the_most_recommended_businesses_only_with_enough_text(synthetic):
    from pypdf import PdfReader
    from src.final_beta_report import compare_reviews
    themes = [("Friendly staff", ["friendly"]), ("Location", ["station"]), ("Never said", ["zzz"])]
    review = lambda n, text, place="x": {"review_id": f"{place}{n}", "review_text": text, "review_rating": 5, "review_datetime_utc": "2026-05-01"}
    mine = [review(n, "Friendly team, right by the station.") for n in range(10)]
    rival = [review(n, "Friendly welcome every time.", "a") for n in range(15)] + [review(n, "Close to the station.", "a") for n in range(15, 20)]
    out = compare_reviews(mine, [{"name": "Rival", "records": rival, "google_total": "41", "google_rating": "4.8"},
                                 {"name": "No Text Ltd", "records": [], "google_total": None}], themes, target_total=12)
    assert out["names"] == ["Rival"] and out["reviews"] == 20 and out["totals"] == [("Rival", 41, 4.8)]
    assert out["rows"] == [("Location", 100, 25), ("Friendly staff", 100, 75)], "widest gap first; a theme nobody mentions is left out"
    few = compare_reviews(mine, [{"name": "Rival", "records": rival[:5], "google_total": 41}], themes, target_total=12)
    assert few["rows"] == [] and few["totals"], "too little text to compare shares, but the published totals still stand"
    assert compare_reviews(mine, [{"name": "Rival", "records": rival[:5]}], themes, target_total=12) is None
    long = lambda rows: [{**r, "review_text": r["review_text"] + " I would recommend this salon to everyone I know in town, truly."} for r in rows]
    data = build(synthetic, review_records=long(mine), review_themes=themes, google_total=12, google_rating=5,
                 comparison_reviews=[{"name": "Rival", "records": rival, "google_total": 41, "google_rating": 4.8}])
    text = " ".join(" ".join((page.extract_text() or "").split()) for page in PdfReader(io.BytesIO(render_final_beta_pdf(data))).pages)
    assert "Compared with the businesses recommended most" in text and "Rival 41 (4.8)" in text
    assert "Compared with the businesses" not in " ".join(
        (p.extract_text() or "") for p in PdfReader(io.BytesIO(render_final_beta_pdf(build(synthetic, review_records=long(mine), review_themes=themes)))).pages)


def test_the_earlier_test_is_left_out_unless_asked_for(synthetic, monkeypatch):
    import pandas as pd
    from src import final_beta_repository as repo
    payload, summary = synthetic
    asked = []
    monkeypatch.setattr(repo, "get_run_results", lambda run_id: pd.DataFrame())
    monkeypatch.setattr(repo, "load_business_domains", lambda engine=None: {})
    monkeypatch.setattr(repo, "load_comparison_reviews", lambda summary, engine=None: [])
    monkeypatch.setattr(repo, "load_previous_run", lambda *a, **k: asked.append(1) or (
        [answer(summary["questions"][0]["text"], "1. **Example Salon**")] * 6, "2025-12-01"))
    revision = {"benchmark_run_id": "run", "target_google_place_id": summary["target_id"], "reviewer_decisions": {}, "owner_context": {}}
    plain = repo.assemble_final_beta(summary, payload, revision, {"primary_group": "generic"})
    assert not asked and plain["previous_date"] is None and all(q["previous"] is None for q in plain["questions"])
    compared = repo.assemble_final_beta(summary, payload, revision, {"primary_group": "generic"}, compare_with_earlier=True)
    assert asked and compared["previous_date"] is not None
