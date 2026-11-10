"""Chains: one business with several Google listings, counted once per answer (src/chains.py)."""
from __future__ import annotations

import pandas as pd
import pytest

from src.chains import ChainError, apply_chains, chain_names, clean_chains
from src.owner_services_report import place_words

PLACES = place_words("Brighton, Hove, Newhaven, East Sussex, South East")
TOPPS = {"name": "Topps Tiles", "place_ids": ["sup", "kemp", "new"], "evidence_place_id": "sup"}
MASTER = {"name": "Mastertiles", "place_ids": ["holl"]}


def row(query, provider, position, raw, place=None, name=None):
    return {"query_id": query, "provider": provider, "position": position, "raw_business_name": raw,
            "google_place_id": place, "business_name": name or raw,
            "resolution_status": "exact" if place else "unresolved",
            "classification": "AI-discovered" if place else "Unresolved"}


def test_clean_chains_validates_and_defaults_the_evidence_listing():
    chains = clean_chains([MASTER, {**TOPPS, "aliases": ["  Topps  Tile  Store "]}], target_id="client")
    assert chains[0]["evidence_place_id"] == "holl"
    assert chains[1]["aliases"] == ["Topps Tile Store"]
    assert chain_names(chains) == {"holl": "Mastertiles", "sup": "Topps Tiles"}
    assert clean_chains(None) == []


@pytest.mark.parametrize("bad, message", [
    ({"name": "", "place_ids": ["a"]}, "needs a name"),
    ({"name": "X", "place_ids": []}, "needs a name"),
    ({"name": "X", "place_ids": ["client"]}, "client cannot"),
    ({"name": "X", "place_ids": ["a"], "evidence_place_id": "b"}, "must be one of its listings"),
])
def test_clean_chains_refuses_unsafe_definitions(bad, message):
    with pytest.raises(ChainError, match=message):
        clean_chains([bad], target_id="client")


def test_a_listing_cannot_be_in_two_chains():
    with pytest.raises(ChainError, match="two chains"):
        clean_chains([TOPPS, {"name": "Other", "place_ids": ["kemp"]}])


def test_branches_and_bare_brand_names_count_once_per_answer_for_the_chain():
    records = pd.DataFrame([
        row("q1", "OpenAI", 1, "Topps Tiles Newhaven", "new", "Topps Tiles Newhaven"),
        row("q1", "OpenAI", 3, "Topps Tiles (Kemp Town)"),            # second Topps mention in the same answer
        row("q2", "Gemini", 2, "Topps Tiles – Brighton & Hove"),       # brand only, place words stripped
        row("q2", "Gemini", 4, "Master Tiles (Brighton)"),             # spacing differs from the chain name
        row("q3", "Claude", 1, "House of Tiles, Newhaven"),            # not a chain: untouched
        row("q3", "Claude", 2, "Topps", "hotel", "Topps"),             # a listing outside every chain: untouched
    ])
    out = apply_chains(records, clean_chains([TOPPS, MASTER]), PLACES)

    topps = out[out["google_place_id"] == "sup"]
    assert sorted(topps["query_id"]) == ["q1", "q2"]                 # once per answer, not three times
    assert set(topps["business_name"]) == {"Topps Tiles"}
    assert topps.loc[topps["query_id"] == "q1", "chain_branch_place_id"].tolist() == ["new"]  # best-placed branch kept
    assert topps.loc[topps["query_id"] == "q2", "resolution_status"].tolist() == ["chain_name"]

    master = out[out["google_place_id"] == "holl"]
    assert master["business_name"].tolist() == ["Mastertiles"]

    untouched = out[out["query_id"] == "q3"].set_index("raw_business_name")
    assert pd.isna(untouched.loc["House of Tiles, Newhaven", "google_place_id"])
    assert untouched.loc["Topps", "google_place_id"] == "hotel"


def test_no_chains_leaves_records_unchanged():
    records = pd.DataFrame([row("q1", "OpenAI", 1, "Topps Tiles")])
    assert apply_chains(records, [], PLACES) is records


def test_the_same_written_name_cannot_belong_to_two_chains():
    with pytest.raises(ChainError, match="name of two chains"):
        apply_chains(pd.DataFrame([row("q1", "OpenAI", 1, "Topps")]),
                     clean_chains([{**TOPPS, "aliases": ["Tile Co"]}, {"name": "Tile Co", "place_ids": ["x"]}]), PLACES)
