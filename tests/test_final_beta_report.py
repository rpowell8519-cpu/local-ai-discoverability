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
