"""Name matching fixes from the Authentic Stone report (10 November 2026), using the names that went wrong.

1. A listing's one-word stem claimed longer names: "The House Restaurant" took "House of Tiles", a hotel called
   "Topps" took "Topps Tiles".
2. A name rejected in step 5 was still credited by the automatic matcher.
3. A name confirmed for a business outside the comparison set was left unmatched in the report.
4. Highly recommended names with no matching listing were dropped from the report instead of shown as written.
"""
from io import BytesIO

import pandas as pd
import pytest
from pypdf import PdfReader

from src.ai_recommendation_intelligence import build_directory_index, resolve_business_name, without_rejected_links
from src.business_matching import Subject, rejected_links_from_decisions
from src.client_summary.adapter import build_client_summary_report, render_client_summary_pdf
from src.final_beta_report import build_competitors
from src.owner_services_report import build_owner_report, place_words, unmatched_display_name, unmatched_key
from src.owner_services_synthetic import synthetic_owner_services_payload
from src.poc_audit_generic import _all_confirmed_names

DIRECTORY = build_directory_index(pd.DataFrame([
    {"google_place_id": "house", "business_name": "The House Restaurant", "primary_group": "restaurants"},
    {"google_place_id": "topps-hotel", "business_name": "Topps", "primary_group": "hotels_accommodation"},
    {"google_place_id": "brighton-hotel", "business_name": "Brighton", "primary_group": "hotels_accommodation"},
    {"google_place_id": "pig", "business_name": "The Ginger Pig Restaurant and Rooms", "primary_group": "restaurants"},
]))


@pytest.mark.parametrize("name", [
    "House of Tiles", "House of Tiles, Newhaven", "House of Tiles (Newhaven)", "Topps Tiles",
    "Topps Tiles (Kemp Town, Brighton)", "Brighton Tiling & Mosaics", "Brighton & Hove Tiling", "The House Gallery",
])
def test_a_one_word_listing_name_does_not_claim_longer_names(name):
    assert resolve_business_name(name, directory_index=DIRECTORY)["google_place_id"] is None


def test_a_distinctive_short_name_still_matches_its_full_listing():
    assert resolve_business_name("The Ginger Pig", directory_index=DIRECTORY)["google_place_id"] == "pig"


def test_rejected_names_are_taken_off_the_business_they_were_rejected_for():
    decisions = {"rejected_target_names": ["Authentic Stone Gallery"],
                 "name_links": {"topps-hotel": {"rejected": ["Topps Tiles"], "confirmed": []},
                                "owner:somebody": {"rejected": ["Ignored"], "confirmed": []}}}
    links = rejected_links_from_decisions(decisions, "client")
    assert links == {"Authentic Stone Gallery": ["client"], "Topps Tiles": ["topps-hotel"]}
    records = pd.DataFrame([
        {"raw_business_name": "Topps Tiles", "google_place_id": "topps-hotel", "business_name": "Topps",
         "resolution_status": "fuzzy", "classification": "AI-discovered"},
        {"raw_business_name": "Topps Tiles", "google_place_id": "elsewhere", "business_name": "Other",
         "resolution_status": "fuzzy", "classification": "AI-discovered"},
    ])
    out = without_rejected_links(records, links)
    assert out["google_place_id"].tolist() == [None, "elsewhere"]
    assert out.loc[0, "business_name"] == "Topps Tiles" and out.loc[0, "classification"] == "Unresolved"
    assert records.loc[0, "google_place_id"] == "topps-hotel"  # the input is not changed


def test_a_name_confirmed_for_a_business_outside_the_comparison_set_is_credited():
    decisions = {"name_links": {"showroom": {"confirmed": ["Natural Angle"], "rejected": []}}}
    subjects = [Subject("target", "Authentic Stone", "client")]
    records = [{"google_place_id": "showroom", "business_name": "Natural Angle Showroom"}]
    found = _all_confirmed_names(subjects, decisions, "client", records)
    assert found["Natural Angle"]["google_place_id"] == "showroom"
    assert found["Natural Angle"]["business_name"] == "Natural Angle Showroom"


PLACES = place_words("Brighton, Hove, Newhaven, East Sussex, South East")


@pytest.mark.parametrize("variants,shown", [
    (["House of Tiles", "House of Tiles, Newhaven", "House of Tiles (Newhaven)"], "House of Tiles"),
    (["Mastertiles", "Mastertiles Brighton & Hove", "Mastertiles (Brighton)", "Mastertiles, Hove / Brighton"], "Mastertiles"),
    (["Topps Tiles – Brighton and Hove", "Topps Tiles Newhaven", "Topps Tiles (Old Shoreham Road, Brighton & Hove / Newhaven)"], "Topps Tiles"),
])
def test_ways_of_writing_one_unmatched_name_are_grouped(variants, shown):
    assert {unmatched_key(v, PLACES) for v in variants} == {unmatched_key(shown, PLACES)}
    assert {unmatched_display_name(v, PLACES) for v in variants} == {shown}


@pytest.mark.parametrize("name", ["Brighton & Hove Tiling", "Smith, Jones & Co", "Eurotiles & Bathrooms", "Brighton"])
def test_grouping_keeps_names_that_only_look_like_place_qualifiers(name):
    assert unmatched_display_name(name, PLACES) == name


def _with_unmatched_name(payload, written, times):
    """Adds an AI name no listing matches to `times` answers that do not already list it."""
    slots = payload["recommendation_market"]["slot_evidence"]
    answers = list(dict.fromkeys((s["query_id"], s["provider"]) for s in slots))[:times]
    template = next(s for s in slots if s["google_place_id"] != "synthetic-target")
    for (query_id, provider), raw in zip(answers, written * times):
        slots.append({**template, "query_id": query_id, "provider": provider, "google_place_id": None,
                      "business_name": raw, "raw_business_name": raw, "resolution_method": "unresolved",
                      "slot_disposition": "business"})
    return payload


def test_a_highly_recommended_unmatched_name_is_shown_as_written_and_counted_once_per_answer():
    payload = _with_unmatched_name(synthetic_owner_services_payload(),
                                   ["House of Tiles", "House of Tiles, Exampletown", "House of Tiles (Exampletown)"], 20)
    payload["report"]["client_context"] = {"location": "Exampletown"}
    market = build_owner_report(payload)["market"]
    rows = [row for row in market if row.get("unmatched")]
    assert [(row["name"], row["count"]) for row in rows] == [("House of Tiles", 20)]

    summary = build_client_summary_report(payload, business_group="hair_beauty", location="Exampletown")
    key = rows[0]["key"]
    assert key in summary["visible_ids"] and summary["unmatched_ids"] == [key]
    assert any("House of Tiles" in note for note in summary["limitations"])
    assert not any("are not shown" in note for note in summary["limitations"])
    ai = build_competitors(summary)["ai"]
    assert next(row for row in ai if row["name"] == "House of Tiles")["unmatched"] is True
    text = "".join(page.extract_text() for page in PdfReader(BytesIO(render_client_summary_pdf(summary))).pages)
    assert "could not match it to a single Google listing" in " ".join(text.split())


def test_the_final_beta_page_marks_an_unmatched_name_and_explains_it():
    from datetime import date

    from src.final_beta_pdf import render_final_beta_pdf
    from src.final_beta_report import build_final_beta_report

    payload = _with_unmatched_name(synthetic_owner_services_payload(), ["House of Tiles"], 20)
    summary = build_client_summary_report(payload)
    data = build_final_beta_report(summary, responses=list(payload["baseline_validation"]["responses"]), results=[],
                                   confirmed_names=[], today=date(2026, 11, 10))
    text = " ".join(" ".join((page.extract_text() or "").split())
                    for page in PdfReader(BytesIO(render_final_beta_pdf(data))).pages)
    assert "House of Tiles *" in text and "could not match it to a single Google listing" in text
    assert "for the businesses we verified" not in text
