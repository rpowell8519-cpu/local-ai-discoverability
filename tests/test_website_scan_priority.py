"""The website scan reaches the pages that describe the business before form confirmation pages."""
from src.website_audit import url_priority


def test_thank_you_pages_are_visited_after_real_content():
    score = lambda path: url_priority(f"https://example.org/{path}", business_group="generic", source="sitemap")
    assert score("contactus-coworking-thankyou") < score("cowork")
    assert score("contactus-events-thankyou") < score("events-2026")
    assert score("contact-form") > score("contactus-thankyou"), "the contact page itself still ranks well"


def test_reports_read_far_more_than_a_twenty_page_sample():
    from pathlib import Path
    page = (Path(__file__).resolve().parents[1] / "app/pages/10_AI_Report_Generator.py").read_text()
    assert "REPORT_WEBSITE_PAGE_LIMIT = 200" in page and "max_pages=20," not in page
    assert page.count("max_pages=REPORT_WEBSITE_PAGE_LIMIT") == 2
