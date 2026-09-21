from io import BytesIO

import pytest
from pypdf import PdfReader

from src.client_summary import metrics
from src.client_summary.actions import (
    DONE_LIMIT, OWNER_LIMIT, TASK_LIMIT, TITLE_LIMIT, build_actions, profile_for,
)
from src.client_summary.adapter import (
    ClientSummaryError, build_client_summary_report, render_client_summary_pdf,
)
from src.owner_services_report import build_owner_report
from src.owner_services_synthetic import synthetic_owner_services_payload


@pytest.fixture
def payload():
    return synthetic_owner_services_payload()


def summary(payload, **kwargs):
    return build_client_summary_report(payload, business_group="hair_beauty", location="Exampletown", **kwargs)


def test_summary_and_full_report_agree_on_every_count(payload):
    report, data = build_owner_report(payload), summary(payload)
    result = metrics(data)
    assert (result["appearances"], result["complete"]) == (report["appearances"], report["answers"]) == (12, 24)
    assert [(q["appearances"], q["complete"]) for q in data["questions"]] == [
        (q["appearances"], q["answers"]) for q in report["questions"]
    ]
    by_provider = {p["name"]: (p["appearances"], p["complete"]) for p in data["providers"]}
    assert by_provider == {p["name"]: (p["appearances"], p["answers"]) for p in report["provider_counts"]}


def test_renders_six_pages_with_the_measured_result(payload):
    reader = PdfReader(BytesIO(render_client_summary_pdf(summary(payload))))
    assert len(reader.pages) == 6
    assert "12 of 24" in "\n".join(page.extract_text() for page in reader.pages)


def test_question_labels_use_the_owner_priority_they_test(payload):
    labels = [q["label"] for q in summary(payload)["questions"]]
    assert labels == ["Colour / balayage (Q1)", "Colour / balayage (Q2)", "Curly cuts", "Bridal hair"]


def test_unlinked_questions_fall_back_to_their_own_wording(payload):
    payload["report"]["owner_report"]["services"][0]["questions"] = None
    payload["report"]["owner_report"]["services"][1]["questions"] = None
    labels = [q["label"] for q in summary(payload)["questions"]]
    assert all(len(label) <= 65 for label in labels)
    assert not any("mapping not confirmed" in label for label in labels)


def test_incomplete_answers_stop_the_summary_with_a_clear_reason(payload):
    record = payload["baseline_validation"]["responses"][0]
    record.update(response_complete=False, status="failed", raw_response="")
    with pytest.raises(ClientSummaryError, match="incomplete or failed"):
        summary(payload)


def test_reviewer_titles_replace_action_titles_and_are_length_checked(payload):
    data = summary(payload, reviewer_action_titles=["Fix the booking page"])
    assert data["actions"][0]["title"] == "Fix the booking page"
    assert data["actions"][1]["title"].startswith("Make ")


def test_confirmed_target_names_are_disclosed(payload):
    slot = next(s for s in payload["recommendation_market"]["slot_evidence"] if s["google_place_id"] == "synthetic-target")
    slot.update(resolution_method="reviewer_confirmed_target_name", source_raw_business_name="Example")
    assert any("“Example”" in item for item in summary(payload)["limitations"])


def test_owner_review_is_only_claimed_when_questions_are_the_owners(payload):
    assert summary(payload)["owner_reviewed_questions"] is False
    owner = [q["prompt"] for q in build_owner_report(payload)["questions"]]
    assert summary(payload, owner_questions=owner)["owner_reviewed_questions"] is True
    assert summary(payload, owner_questions=owner[:-1])["owner_reviewed_questions"] is False


def test_summary_is_read_only(payload):
    import copy
    before = copy.deepcopy(payload)
    summary(payload)
    assert payload == before


QUESTIONS = [
    {"id": "q1", "label": "L" * 65, "appearances": 0, "answers": 9},
    {"id": "q2", "label": "Group bookings", "appearances": 3, "answers": 9},
    {"id": "q3", "label": "Garden seating", "appearances": 8, "answers": 9},
]


@pytest.mark.parametrize("group", ["pub", "salon", "cleaning_services", "coworking", "something_new", None])
def test_actions_fit_the_contract_for_every_business_type(group):
    actions = build_actions(QUESTIONS, business_group=group)
    assert len(actions) == 3 and {a["status"] for a in actions} == {"suggested_check"}
    for action in actions:
        assert len(action["title"]) <= TITLE_LIMIT and len(action["task"]) <= TASK_LIMIT
        assert len(action["owner"]) <= OWNER_LIMIT and len(action["done_when"]) <= DONE_LIMIT
        assert action["evidence_ids"] == []


def test_weakest_topics_get_checks_and_the_strongest_gets_the_consistency_action():
    actions = build_actions(QUESTIONS, business_group="pub")
    assert [a["question_id"] for a in actions] == ["q1", "q2", "q3"]
    assert "consistent" in actions[2]["title"]
    assert actions[0]["title"] == "Make this topic easy to find and act on"  # label too long for a title


def test_business_type_changes_wording_not_structure():
    assert "TripAdvisor" in profile_for("pubs").platforms
    assert "Checkatrade" in profile_for("cleaning_services").platforms
    assert profile_for("unknown thing") == profile_for(None)


def test_summary_needs_two_questions_to_choose_actions():
    with pytest.raises(ValueError, match="at least two"):
        build_actions(QUESTIONS[:1])


def test_actions_make_no_uplift_promise():
    text = " ".join(a["task"] + a["done_when"] for a in build_actions(QUESTIONS)).casefold()
    assert not any(word in text for word in ("guarantee", "rank higher", "more customers", "increase your"))


CRAWLER_GAP = {
    "id": "E1", "kind": "crawler_access", "gap": True, "blocked_labels": ["ChatGPT search", "Perplexity"],
    "observation": "robots.txt asks these AI search crawlers not to visit the site: OAI-SearchBot (ChatGPT search), PerplexityBot (Perplexity).",
    "source": "https://example.co.uk/robots.txt, read on 21 September 2026",
}
CRAWLER_OK = {
    "id": "E1", "kind": "crawler_access", "gap": False, "blocked_labels": [],
    "observation": "robots.txt does not block the main AI search crawlers (ChatGPT search, Claude search, Perplexity, Google Search, Bing and Copilot).",
    "source": "https://example.co.uk/robots.txt, read on 21 September 2026",
}


def test_a_blocked_crawler_becomes_the_first_action_and_a_verified_gap():
    actions = build_actions(QUESTIONS, business_group="pub", findings=[CRAWLER_GAP])
    assert len(actions) == 3
    first = actions[0]
    assert first["status"] == "verified_gap" and first["evidence_ids"] == ["E1"]
    assert "ChatGPT search, Perplexity" in first["task"]
    assert [a["status"] for a in actions[1:]] == ["suggested_check", "suggested_check"]
    assert [a["id"] for a in actions] == ["action-1", "action-2", "action-3"]
    assert "robots.txt" not in actions[2]["task"] and "crawlers" not in actions[2]["task"]


def test_an_all_clear_check_removes_the_generic_crawler_request_but_is_not_an_action():
    actions = build_actions(QUESTIONS, business_group="pub", findings=[CRAWLER_OK])
    assert {a["status"] for a in actions} == {"suggested_check"}
    assert "crawlers" not in actions[2]["task"] and "crawlers" not in actions[2]["done_when"]


def test_without_a_check_the_consistency_action_still_asks_the_provider_to_confirm():
    actions = build_actions(QUESTIONS, business_group="pub")
    assert "crawlers are not blocked" in actions[2]["task"]


def test_verified_actions_fit_the_contract():
    for action in build_actions(QUESTIONS, findings=[CRAWLER_GAP]):
        assert len(action["title"]) <= TITLE_LIMIT and len(action["task"]) <= TASK_LIMIT
        assert len(action["owner"]) <= OWNER_LIMIT and len(action["done_when"]) <= DONE_LIMIT


def test_the_summary_shows_the_observation_its_source_and_a_verified_action(payload):
    data = summary(payload, site_findings=[CRAWLER_GAP], website_checked=True)
    assert [e["id"] for e in data["evidence"]] == ["E1"]
    assert data["actions"][0]["status"] == "verified_gap"
    text = " ".join(
        page.extract_text() for page in PdfReader(BytesIO(render_client_summary_pdf(data))).pages
    )
    text = " ".join(text.split())
    assert "OAI-SearchBot (ChatGPT search)" in text
    assert "https://example.co.uk/robots.txt, read on 21 September 2026" in text
    assert "Action for a documented gap" in text and "LET AI SEARCH TOOLS VISIT YOUR WEBSITE" in text
    assert "robots.txt" in text and len(PdfReader(BytesIO(render_client_summary_pdf(data))).pages) == 6


def test_an_all_clear_observation_is_shown_but_no_gap_is_claimed(payload):
    data = summary(payload, site_findings=[CRAWLER_OK], website_checked=True)
    assert data["evidence"][0]["id"] == "E1"
    assert all(a["status"] == "suggested_check" for a in data["actions"])
    assert not any("could not be read" in item for item in data["limitations"])


def test_an_unreadable_robots_file_is_a_limitation_never_a_gap(payload):
    data = summary(payload, site_findings=[], website_checked=True)
    assert data["evidence"] == [] and all(a["status"] == "suggested_check" for a in data["actions"])
    assert any("could not be read" in item for item in data["limitations"])


def test_no_website_means_no_limitation_about_crawlers(payload):
    data = summary(payload, site_findings=[], website_checked=False)
    assert not any("robots.txt" in item for item in data["limitations"])


CONTACT_GAP = {
    "id": "E2", "kind": "contact_details", "gap": True, "fields": ["phone number"],
    "observation": "The website and the Google listing disagree: the Google listing gives 01273 123456; the pages read show 01273 654321 but not that number.",
    "source": "https://example.co.uk/contact, saved 21 September 2026",
}
CONTACT_OK = {
    "id": "E2", "kind": "contact_details", "gap": False, "fields": [], "matches": ["phone number", "postcode"],
    "observation": "The website shows the same phone number and postcode as the Google listing.",
    "source": "https://example.co.uk/contact, saved 21 September 2026",
}


def test_a_contact_discrepancy_is_a_second_verified_gap_and_replaces_the_generic_consistency_action():
    actions = build_actions(QUESTIONS, business_group="pub", findings=[CRAWLER_GAP, CONTACT_GAP])
    assert [a["status"] for a in actions] == ["verified_gap", "verified_gap", "suggested_check"]
    assert actions[1]["title"] == "Make your contact details match everywhere"
    assert actions[1]["evidence_ids"] == ["E2"] and "phone number" in actions[1]["task"]
    assert not any("consistent" in a["title"] for a in actions)
    assert [a["id"] for a in actions] == ["action-1", "action-2", "action-3"]


def test_a_contact_gap_alone_keeps_two_topic_checks():
    actions = build_actions(QUESTIONS, business_group="pub", findings=[CONTACT_GAP])
    assert [a["status"] for a in actions] == ["verified_gap", "suggested_check", "suggested_check"]


def test_matching_contact_details_are_acknowledged_in_the_consistency_action():
    actions = build_actions(QUESTIONS, business_group="pub", findings=[CONTACT_OK])
    assert {a["status"] for a in actions} == {"suggested_check"}
    assert "agree on the phone number and postcode" in actions[2]["task"]
    assert len(actions[2]["task"]) <= TASK_LIMIT


def test_every_finding_combination_fits_the_contract():
    for findings in ([], [CRAWLER_GAP], [CONTACT_GAP], [CRAWLER_GAP, CONTACT_GAP], [CRAWLER_OK, CONTACT_OK]):
        for group in ("pub", "salon", "cleaning_services", "coworking", None):
            for action in build_actions(QUESTIONS, business_group=group, findings=findings):
                assert len(action["title"]) <= TITLE_LIMIT and len(action["task"]) <= TASK_LIMIT
                assert len(action["owner"]) <= OWNER_LIMIT and len(action["done_when"]) <= DONE_LIMIT


def _with_website(payload, phone_on_site):
    """Add a phone number to a page the synthetic audit already saved for the target."""
    payload["report"]["owner_report"]["listing_contact"] = {"phone": "01273 123456", "postal_code": None, "address": None}
    audit = payload["website_evidence"]["audits"][0]
    audit["completed_at"] = "2026-09-20T10:00:00"
    audit["pages"][0]["text_excerpt"] += f" Call us on {phone_on_site}."
    return payload


def test_the_summary_runs_the_contact_check_from_the_saved_pages_and_shows_its_source(payload):
    data = summary(_with_website(payload, "01273 654321"), site_findings=[], website_checked=False)
    assert [e["id"] for e in data["evidence"]] == ["E1"]
    assert data["actions"][0]["status"] == "verified_gap" and data["actions"][0]["evidence_ids"] == ["E1"]
    page_url = payload["website_evidence"]["audits"][0]["pages"][0]["url"]
    assert data["evidence"][0]["source"] == f"{page_url}, saved 20 September 2026"
    text = " ".join(" ".join(p.extract_text().split()) for p in PdfReader(BytesIO(render_client_summary_pdf(data))).pages)
    assert "01273 654321" in text and "MAKE YOUR CONTACT DETAILS MATCH EVERYWHERE" in text


def test_findings_are_numbered_in_order_with_gaps_first(payload):
    data = summary(_with_website(payload, "01273 654321"), site_findings=[CRAWLER_OK], website_checked=True)
    assert [(e["id"], "robots" in e["observation"]) for e in data["evidence"]] == [("E1", False), ("E2", True)]
    both = summary(_with_website(synthetic_owner_services_payload(), "01273 654321"), site_findings=[CRAWLER_GAP], website_checked=True)
    assert [a["status"] for a in both["actions"]][:2] == ["verified_gap", "verified_gap"]
    assert [e["id"] for e in both["evidence"]] == ["E1", "E2"]
    assert both["actions"][0]["evidence_ids"] == ["E1"] and both["actions"][1]["evidence_ids"] == ["E2"]


def test_no_listing_data_means_the_contact_check_is_skipped(payload):
    data = summary(payload)
    assert data["evidence"] == []


def test_a_verified_action_is_justified_by_its_observation_not_by_a_topic_count(payload):
    data = summary(_with_website(payload, "01273 654321"), site_findings=[CRAWLER_GAP], website_checked=True)
    page_five = " ".join(
        PdfReader(BytesIO(render_client_summary_pdf(data))).pages[4].extract_text().split()
    )
    assert "Why: robots.txt asks these AI search crawlers not to visit the site" in page_five
    assert "Why: The website and the Google listing disagree" in page_five
    # the topic count is still the reason for the suggested check
    assert "Why: you appeared in" in page_five
