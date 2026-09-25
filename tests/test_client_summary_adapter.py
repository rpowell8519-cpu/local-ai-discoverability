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


def test_renders_summary_and_three_review_pages_with_the_measured_result(payload):
    reader = PdfReader(BytesIO(render_client_summary_pdf(summary(payload))))
    assert len(reader.pages) == 11
    assert "12 of 24" in "\n".join(page.extract_text() for page in reader.pages)


def test_question_labels_use_the_owner_priority_they_test(payload):
    labels = [q["label"] for q in summary(payload)["questions"]]
    # Q1 and Q2 both test "Colour / balayage": each is shown by its own wording so neither is hidden.
    assert labels[2:] == ["Curly cuts", "Bridal hair"]
    assert all("Colour / balayage" not in label for label in labels[:2]) and len(set(labels)) == 4


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
    assert "robots.txt" in text and len(PdfReader(BytesIO(render_client_summary_pdf(data))).pages) == 11


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
        PdfReader(BytesIO(render_client_summary_pdf(data))).pages[6].extract_text().split()
    )
    assert "Why: robots.txt asks these AI search crawlers not to visit the site" in page_five
    assert "Why: The website and the Google listing disagree" in page_five
    # the topic count is still the reason for the suggested check
    assert "Why: you appeared in" in page_five


def test_the_adapter_produces_drafts_unless_told_not_to(payload):
    assert summary(payload)["draft"] is True
    assert summary(payload, draft=False)["draft"] is False


from src.client_summary.adapter import _topic_wording  # noqa: E402


@pytest.mark.parametrize("prompt,expected", [
    ("Recommend places in Brighton for coworking.", "coworking."),
    ("Recommend places for co working near Brighton station", "co working near Brighton station"),
    ("Best co working hub in Brighton", "co working hub in Brighton"),
    ("Where can i arrange a team away day in Brighton?", "team away day in Brighton?"),
    # unchanged: no boilerplate opener, or nothing would be left
    ("Sustainable working offices in Brighton", "Sustainable working offices in Brighton"),
    ("Which salons offer hair colouring in Exampletown?", "Which salons offer hair colouring in Exampletown?"),
    ("Recommend places", "Recommend places"),
])
def test_only_boilerplate_openers_are_removed_from_question_labels(prompt, expected):
    assert _topic_wording(prompt) == expected


def test_a_label_reads_as_a_topic_and_the_exact_question_is_kept_in_full(payload):
    data = summary(payload)
    assert data["questions"][0]["text"] == build_owner_report(payload)["questions"][0]["prompt"]  # never altered
    assert all(q["label"][0].isupper() for q in data["questions"])


# ---------------------------------------------------------------- two pages on competitors
def with_owner_competitors(payload, *entries):
    payload["report"]["owner_competitors"] = [dict(e) for e in entries]
    return payload


MATCHED = {"owner_name": "Colour Studio", "google_place_id": "synthetic-other", "business_name": "Example Colour Studio",
           "match_status": "matched", "recommendations": 24}
UNLISTED = {"owner_name": "Unlisted Rival", "google_place_id": None, "business_name": "Unlisted Rival",
            "match_status": "not_in_system", "recommendations": 0}


def test_the_summary_lists_the_competitors_the_owner_named_as_the_reviewer_matched_them(payload):
    data = summary(with_owner_competitors(payload, MATCHED, UNLISTED))
    assert data["named_ids"] == ["synthetic-other", "unresolved:unlisted rival"]
    assert data["unverified_ids"] == ["unresolved:unlisted rival"]
    names = {b["id"]: b["name"] for b in data["businesses"]}
    assert names["synthetic-other"] == "Example Colour Studio" and names["unresolved:unlisted rival"] == "Unlisted Rival"


def test_the_summary_lists_the_businesses_the_ai_recommended_most_whether_or_not_they_were_named(payload):
    data = summary(with_owner_competitors(payload, UNLISTED))
    assert data["visible_ids"] == ["synthetic-other"]      # verified, not the client, most recommended first
    assert "synthetic-other" not in data["named_ids"] and len(data["businesses"]) == 3   # client, the named one, the AI's pick


def test_a_business_that_is_both_named_and_highly_visible_appears_once_in_the_data_and_on_both_pages(payload):
    data = summary(with_owner_competitors(payload, MATCHED))
    assert [b["id"] for b in data["businesses"]].count("synthetic-other") == 1
    assert data["named_ids"] == data["visible_ids"] == ["synthetic-other"]
    pages = [" ".join(p.extract_text().split()) for p in PdfReader(BytesIO(render_client_summary_pdf(data))).pages]
    assert "Example Colour Studio" in pages[3] and "Example Colour Studio" in pages[4]
    assert "This business was also on your list." in pages[4]


def test_page_four_tells_the_owner_how_they_compared_with_the_competitors_they_named(payload):
    pages = [" ".join(p.extract_text().split()) for p in PdfReader(BytesIO(render_client_summary_pdf(summary(with_owner_competitors(payload, MATCHED, UNLISTED))))).pages]
    assert "Who you told us you compete with" in pages[3]
    assert "Of the 2 businesses you named, 1 appeared more often than Example Salon and 1 less often." in pages[3]
    assert "Unlisted Rival is not in our business database, so the count shown includes only AI answer names a reviewer matched to it." in pages[3]


def test_page_four_says_so_when_no_competitors_were_named(payload):
    text = " ".join(PdfReader(BytesIO(render_client_summary_pdf(summary(payload)))).pages[3].extract_text().split())
    assert "No competitors were named for this audit" in text


def test_page_five_is_the_ai_view_and_page_six_holds_providers_and_what_was_checked(payload):
    pages = [" ".join(p.extract_text().split()) for p in PdfReader(BytesIO(render_client_summary_pdf(summary(payload, site_findings=[CRAWLER_GAP], website_checked=True)))).pages]
    assert "Who AI treats as your competitors" in pages[4] and "MOST OFTEN RECOMMENDED" in pages[4]
    assert "Your results differed by provider" in pages[5] and "What we checked" in pages[5] and "We looked at their" not in pages[5]
    assert "observations on page 6" in pages[6]        # the action plan points at the page that holds the evidence


def test_the_contract_refuses_named_lists_that_point_at_the_client_or_nothing(payload):
    from src.client_summary import ReportValidationError, validate_report
    data = summary(with_owner_competitors(payload, MATCHED))
    for field, bad in (("named_ids", [data["target_id"]]), ("visible_ids", ["nobody"]), ("unverified_ids", ["synthetic-other", "x"])):
        broken = {**data, field: bad}
        with pytest.raises(ReportValidationError):
            validate_report(broken)
    with pytest.raises(ReportValidationError, match="subset"):
        validate_report({**data, "named_ids": [], "unverified_ids": ["synthetic-other"]})


def test_the_summary_says_what_the_actions_were_drawn_from_only_when_they_were():
    from tests.test_evidence_recommendations_in_reports import payload_with, summary_for
    used = summary_for(payload_with())                       # approved recommendations, websites and reviews both used
    assert used["evidence_layers"] == ["websites", "customer reviews"]
    text = " ".join(" ".join(p.extract_text().split()) for p in PdfReader(BytesIO(render_client_summary_pdf(used))).pages)
    assert "We looked at their websites and customer reviews, alongside yours, to shape the actions" in text
    none = summary_for(payload_with(()))
    assert none["evidence_layers"] == []
    text = " ".join(" ".join(p.extract_text().split()) for p in PdfReader(BytesIO(render_client_summary_pdf(none))).pages)
    assert "We looked at their" not in text
