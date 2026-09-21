from datetime import date

import pytest

from src.site_checks import (
    AI_SEARCH_CRAWLERS, check_ai_crawler_access, crawler_finding, evaluate_robots,
)

SITE = "https://www.example-salon.co.uk"
TODAY = "2026-09-21"


def access(text, status=200):
    return evaluate_robots(website_url=SITE, status=status, text=text, checked_on=TODAY)


def blocked_agents(result):
    return [agent for agent, _ in result.blocked]


def test_a_site_wide_block_for_everyone_blocks_every_search_crawler():
    result = access("User-agent: *\nDisallow: /\n")
    assert result.status == "blocked"
    assert blocked_agents(result) == [agent for agent, _ in AI_SEARCH_CRAWLERS]


def test_only_the_named_crawler_is_blocked_when_others_are_allowed():
    result = access("User-agent: OAI-SearchBot\nDisallow: /\n\nUser-agent: *\nAllow: /\n")
    assert result.status == "blocked" and blocked_agents(result) == ["OAI-SearchBot"]


def test_blocking_only_training_crawlers_is_not_flagged():
    result = access("User-agent: GPTBot\nDisallow: /\n\nUser-agent: ClaudeBot\nDisallow: /\n\nUser-agent: Google-Extended\nDisallow: /\n")
    assert result.status == "open" and result.blocked == ()


def test_blocking_a_private_folder_leaves_the_home_page_open():
    assert access("User-agent: *\nDisallow: /wp-admin/\n").status == "open"


def test_an_empty_or_permissive_file_is_open():
    assert access("").status == "open"
    assert access("User-agent: *\nAllow: /\n").status == "open"


@pytest.mark.parametrize("status", [404, 410])
def test_no_robots_file_means_nothing_blocks_crawlers(status):
    result = access(None, status)
    assert result.status == "open" and result.robots_found is False


@pytest.mark.parametrize("status", [None, 500, 503, 401, 403, 429, 302])
def test_an_unreadable_robots_file_is_unknown_never_a_gap(status):
    assert access(None, status).status == "unknown"
    assert crawler_finding(access(None, status)) is None


def test_blocked_finding_names_the_crawlers_and_its_source_and_date():
    finding = crawler_finding(access("User-agent: PerplexityBot\nDisallow: /\n"))
    assert finding["gap"] is True
    assert "PerplexityBot (Perplexity)" in finding["observation"]
    assert finding["source"] == "https://www.example-salon.co.uk/robots.txt, read on 21 September 2026"
    assert finding["blocked_labels"] == ["Perplexity"]


def test_open_finding_is_an_observation_not_a_gap():
    finding = crawler_finding(access("User-agent: *\nAllow: /\n"))
    assert finding["gap"] is False and "does not block" in finding["observation"]
    missing = crawler_finding(access(None, 404))
    assert missing["gap"] is False and "No robots.txt file was found" in missing["observation"]


def test_findings_fit_the_summary_contract_even_when_everything_is_blocked():
    finding = crawler_finding(access("User-agent: *\nDisallow: /\n"))
    assert len(finding["observation"]) <= 220 and len(finding["source"]) <= 200


def test_no_website_means_no_check():
    assert check_ai_crawler_access("") is None
    assert check_ai_crawler_access("   ") is None
    assert crawler_finding(None) is None


def test_check_uses_the_fetcher_and_the_supplied_date():
    result = check_ai_crawler_access(
        SITE, today=date(2026, 9, 21), fetcher=lambda url: (200, "User-agent: *\nDisallow: /\n")
    )
    assert result.status == "blocked" and result.checked_on == "2026-09-21"
