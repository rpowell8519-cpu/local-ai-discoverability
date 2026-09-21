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


# ---------------------------------------------------------------- contact details
from src.site_checks import (  # noqa: E402
    SAVED_TEXT_CAP, check_contact_details, contact_finding, extract_contact_details,
    normalise_postcode, normalise_uk_phone,
)


@pytest.mark.parametrize("written", [
    "01273 123456", "+44 (0)1273 123456", "+44 1273 123456", "0044 1273 123456", "(01273) 123-456", "01273123456",
])
def test_every_way_of_writing_a_uk_number_gives_the_same_number(written):
    assert normalise_uk_phone(written) == "01273123456"


@pytest.mark.parametrize("not_a_phone", ["2026-09-21", "12345", "0123456789012345", "", None, "ABC"])
def test_dates_reference_numbers_and_junk_are_not_phone_numbers(not_a_phone):
    assert normalise_uk_phone(not_a_phone) is None


def test_postcodes_are_found_and_normalised():
    assert normalise_postcode("Unit 4, Brighton bn1 4ea") == "BN14EA"
    assert normalise_postcode("No code here") is None
    phones, postcodes = extract_contact_details("Hove BN3 2FL. Tel 01273 123456. Ref 0123456789012345")
    assert phones == {"01273123456"} and postcodes == {"BN32FL"}


def page(text, url="https://x.example/contact"):
    return {"url": url, "text_excerpt": text}


def contact(pages, phone="01273 123456", postcode="BN1 4EA"):
    return check_contact_details(listing_phone=phone, listing_postcode=postcode, pages=pages, checked_on=TODAY)


def test_matching_details_are_reported_as_an_observation_not_a_gap():
    finding = contact_finding(contact([page("Call 01273 123456. 4 Church Rd, Brighton BN1 4EA")]))
    assert finding["gap"] is False
    assert finding["observation"] == "The website shows the same phone number and postcode as the Google listing."


def test_a_different_number_on_complete_pages_is_a_specific_discrepancy():
    finding = contact_finding(contact([page("Call us on 01273 654321. BN1 4EA")]))
    assert finding["gap"] is True and finding["fields"] == ["phone number"]
    assert "01273 123456" in finding["observation"] and "01273 654321" in finding["observation"]
    assert "https://x.example/contact" in finding["source"] and "21 September 2026" in finding["source"]


def test_the_listing_number_appearing_on_any_page_means_no_discrepancy():
    pages = [page("Call 01273 654321"), page("Also on 01273 123456", "https://x.example/about")]
    assert contact_finding(contact(pages, postcode=None))["gap"] is False


def test_a_truncated_page_can_never_support_a_discrepancy():
    long_text = "Call 01273 654321. " + "x" * SAVED_TEXT_CAP
    assert contact([page(long_text)], postcode=None) is None


def test_no_number_on_the_site_is_not_reported_because_it_may_be_an_image():
    assert contact([page("Welcome to our salon. Book online.")], postcode=None) is None


def test_missing_listing_data_or_pages_means_no_finding():
    assert contact([page("Call 01273 654321")], phone=None, postcode=None) is None
    assert contact([], phone="01273 123456") is None
    assert contact_finding(None) is None


def test_two_differences_are_both_named_and_still_fit_the_contract():
    finding = contact_finding(contact([page("Call 07700 900123 or 01273 654321, Hove BN3 2FL")]))
    assert finding["fields"] == ["phone number", "postcode"]
    assert len(finding["observation"]) <= 220 and len(finding["source"]) <= 200
    assert finding["observation"].endswith(".")


def test_a_number_followed_by_a_sentence_is_not_swallowed_with_the_next_digits():
    # Regression: "Tel 01273 123456. 4 Church Road" once ran the number into the house number.
    phones, _ = extract_contact_details("Tel 01273 123456. 4 Church Road, Brighton. Or 07700 900123, 12 High St.")
    assert phones == {"01273123456", "07700900123"}
