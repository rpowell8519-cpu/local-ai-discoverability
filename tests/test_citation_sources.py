"""Cited sources: one count per website per answer, honest kinds of website, and Google redirects resolved."""
from datetime import datetime

import pytest

from src.citation_sources import (BUSINESS_SITE, by_business_type, CLIENT_SITE, PUBLIC_BODY, UNCLASSIFIED, area_of, build_records,
                                  cited_host, cited_page, classify, load_source_types, over_time, rank_websites,
                                  resolve_redirects, sample, type_mix)

REDIRECT = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/"
CATALOG = {"checkatrade.com": "Directory or comparison site", "reddit.com": "Social or forum"}


def cite(url, title=""):
    return {"url": url, "title": title}


def result(run, place, business, *citations, provider="OpenAI", day=1, question="Best cleaner in Brighton?",
           text="", measured=True, status="completed", kind="core", group="cleaning_services", own=()):
    result.count += 1
    return {"result_id": f"r{result.count}", "run_id": run, "answered_at": datetime(2026, 10, day), "provider": provider,
            "question": question, "status": status, "raw_response": text, "place_id": place, "business": business,
            "business_type": group, "location": "Brighton, Hove", "panel_kind": kind, "own_websites": list(own),
            "report_metadata": {"citation_status": "measured" if measured else "unavailable", "citations": list(citations)}}


result.count = 0


def test_google_redirects_use_the_resolved_page_else_the_title_and_unnamed_titles_name_nothing():
    assert cited_host(cite(REDIRECT + "a", "checkatrade.com")) == "checkatrade.com"
    assert cited_page(cite(REDIRECT + "a", "checkatrade.com")) == ""
    resolved = {**cite(REDIRECT + "b", "uk.com"), "resolved_url": "https://www.carpetbright.uk.com/brighton/"}
    assert cited_host(resolved) == "carpetbright.uk.com"
    assert cited_page(resolved) == "https://www.carpetbright.uk.com/brighton/"
    assert cited_host(cite(REDIRECT + "c", "uk.com")) is None
    assert cited_page(cite("https://www.x.co.uk/p?utm_source=openai")) == "https://www.x.co.uk/p"


def test_only_google_redirects_are_followed_and_a_bad_location_is_ignored():
    asked = []

    def fetch(url):
        asked.append(url)
        return {"a": "https://www.yell.com/biz/x", "b": REDIRECT + "loop", "c": "javascript:alert(1)"}.get(url[-1])

    cites = [cite(REDIRECT + "a"), cite(REDIRECT + "b"), cite(REDIRECT + "c"), cite("https://evil.example/a"),
             {**cite(REDIRECT + "d"), "resolved_url": "https://kept.example/"}]
    assert resolve_redirects(cites, fetch) == 1
    assert sorted(asked) == sorted([REDIRECT + "a", REDIRECT + "b", REDIRECT + "c"])
    assert cites[0]["resolved_url"] == "https://www.yell.com/biz/x"
    assert "resolved_url" not in cites[1] and "resolved_url" not in cites[2]
    assert cites[4]["resolved_url"] == "https://kept.example/"


def test_a_failing_lookup_leaves_the_citation_as_saved():
    def fetch(url):
        raise TimeoutError

    cites = [cite(REDIRECT + "a", "checkatrade.com")]
    assert resolve_redirects(cites, fetch) == 0 and "resolved_url" not in cites[0]


def test_kinds_come_from_own_site_then_the_list_then_businesses_and_never_default_to_business():
    kw = {"own_hosts": {"client.co.uk"}, "catalog": CATALOG, "business_domains": {"rival.co.uk": "Rival Ltd"},
          "recommended_names": ["Sparkle Cleaning Brighton"]}
    assert classify("client.co.uk", **kw) == (CLIENT_SITE, None)
    assert classify("brighton.checkatrade.com", **kw) == ("Directory or comparison site", None)
    assert classify("brighton-hove.gov.uk", **kw) == (PUBLIC_BODY, None)
    assert classify("rival.co.uk", **kw) == (BUSINESS_SITE, "Rival Ltd")
    assert classify("sparklecleaning.co.uk", **kw) == (BUSINESS_SITE, "Sparkle Cleaning Brighton")
    assert classify("someguide.co.uk", **kw) == (UNCLASSIFIED, None)


def test_the_checked_in_list_loads_and_uses_only_known_kinds(tmp_path):
    catalog = load_source_types()
    assert catalog["checkatrade.com"] == "Directory or comparison site" and catalog["reddit.com"] == "Social or forum"
    bad = tmp_path / "types.csv"
    bad.write_text("domain,source_type\nexample.com,Great site\n")
    with pytest.raises(ValueError):
        load_source_types(bad)


def test_areas_written_differently_are_one_area():
    assert area_of("Brighton, Hove") == area_of("Brighton and Hove") == area_of("Hove") == "Brighton & Hove"
    assert area_of("Lewes") == "Lewes" and area_of(None) == "Area not recorded"


def test_a_website_counts_once_per_answer_and_each_business_can_weigh_the_same():
    rows = [
        # One business tested twice: three answers with citations, two citing Checkatrade (once with three links).
        result("run1", "p1", "UDR", cite("https://checkatrade.com/a"), cite("https://checkatrade.com/b"),
               cite(REDIRECT + "x", "checkatrade.com"), provider="Gemini"),
        result("run1", "p1", "UDR", cite("https://reddit.com/r/brighton")),
        result("run2", "p1", "UDR", cite("https://checkatrade.com/c"), day=8),
        result("run2", "p1", "UDR", day=8),  # measured, cited nothing
        result("run2", "p1", "UDR", cite("https://x.example/"), measured=False, day=8),  # not recorded: left out
        # A second business, one answer, citing Reddit only.
        result("run3", "p2", "Sparkle", cite("https://www.reddit.com/r/x"), group="cleaning_services"),
    ]
    answers, citations = build_records(rows, business_domains={}, catalog=CATALOG)
    assert len(answers) == 5 and answers["websites_cited"].tolist() == [1, 1, 1, 0, 1]
    ranked = rank_websites(answers, citations).set_index("website")
    assert ranked.loc["checkatrade.com", "answers"] == 2
    assert ranked.loc["checkatrade.com", "share_of_answers"] == pytest.approx(2 / 4)
    # UDR: 2 of its 3 cited answers; Sparkle: 0 of 1. Each business equal: (2/3 + 0) / 2.
    assert ranked.loc["checkatrade.com", "share_each_business_equal"] == pytest.approx(1 / 3)
    assert ranked.loc["reddit.com", "share_each_business_equal"] == pytest.approx((1 / 3 + 1) / 2)
    assert ranked.loc["reddit.com", "businesses"] == 2
    assert sample(answers)["businesses"] == 2 and sample(answers)["answers_with_citations"] == 4
    mix = type_mix(answers, citations).set_index("source_type")
    assert mix.loc["Directory or comparison site", "answers"] == 2 and mix.loc["Social or forum", "answers"] == 2
    trend = over_time(answers, citations, "checkatrade.com")
    udr = trend[trend["business"] == "UDR"]
    assert udr["answers_citing"].tolist() == [1, 1] and udr["answers_with_citations"].tolist() == [2, 1]


def test_a_rival_site_is_recognised_from_the_names_its_test_recommended():
    rows = [result("run1", "p1", "UDR", cite("https://www.sparklecleaning.co.uk/"),
                   text="1. **Sparkle Cleaning Brighton** - offices\n2. **Other Co** - homes"),
            result("run1", "p1", "UDR", cite("https://udrcleaning.co.uk/"), own=["https://udrcleaning.co.uk"])]
    _, citations = build_records(rows, business_domains={}, catalog=CATALOG)
    kinds = dict(zip(citations["website"], citations["source_type"]))
    assert kinds == {"sparklecleaning.co.uk": BUSINESS_SITE, "udrcleaning.co.uk": CLIENT_SITE}
    assert citations.set_index("website").loc["sparklecleaning.co.uk", "belongs_to"] == "Sparkle Cleaning Brighton"


def test_business_types_rank_their_own_websites_and_best_evidenced_types_come_first():
    rows = [result("a", "p1", "Clean A", cite("https://checkatrade.com/a")),
            result("b", "p2", "Clean B", cite("https://checkatrade.com/b"), cite("https://reddit.com/r")),
            result("c", "p3", "Cafe C", cite("https://reddit.com/x"), group="coffee_cafes")]
    answers, citations = build_records(rows, business_domains={}, catalog=CATALOG)
    segments = by_business_type(answers, citations)
    assert [seg["sample"]["businesses"] for seg in segments] == [2, 1]
    assert list(segments[0]["websites"]["website"]) == ["checkatrade.com", "reddit.com"]
    assert list(segments[1]["websites"]["website"]) == ["reddit.com"]
