"""Exercise the read-only operator view without a database or provider calls."""
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

from src.measurement_panels import build_panel
from src.proposition_catalog import starter_catalogue

PAGE = str(Path(__file__).resolve().parents[1] / "app/pages/11_Evidence_Foundations.py")
RUN = {"id": "run-1", "target_google_place_id": "place-cisco", "target_propositions": ["Wedding hair", "Upholstry Cleaning"],
       "benchmark_mode": "search_grounded", "started_at": datetime(2025, 8, 5, tzinfo=timezone.utc)}
PROFILE = {"profile_observations": [{"published_review_count": 214, "rating": 4.8, "observed_at": "2025-08-05"}],
           "stored_profile_history": [], "samples": [{"sampled_review_count": 63, "platform": "google"}],
           "unusable_observations": []}


def run_page(*, stored=False, context=None, no_runs=False, matrix=None):
    import streamlit as st
    st.cache_data.clear()
    catalogue, aliases = starter_catalogue()
    wave = None
    if stored:
        wave = {**build_panel(prompts=[{"prompt": "Best wedding hair in Brighton?"}], providers=["OpenAI"],
                            models={"OpenAI": "model"}, location_context="Brighton", benchmark_mode="search_grounded",
                            repeat_count=3, primary_group="hair_services"), "run_id": RUN["id"], "series_id": "series-1"}
    stack = ExitStack()
    patches = [
        patch("src.evidence_foundations_repository.foundation_status", return_value={name: stored for name in
              ["proposition_catalog", "proposition_aliases", "review_profile_metrics", "ai_measurement_waves"]}),
        patch("src.evidence_foundations_repository.list_foundation_businesses", return_value=[
            {"google_place_id": "place-cisco", "business_name": "Cisco's Karma", "primary_group": "hair_services"}]),
        patch("src.evidence_foundations_repository.load_catalogue", return_value=(catalogue, aliases, "test catalogue")),
        patch("src.evidence_foundations_repository.list_business_runs", return_value=[] if no_runs else [
            {**RUN, "target_propositions": context if context is not None else RUN["target_propositions"]}]),
        patch("src.evidence_foundations_repository.load_profile_evidence", return_value=PROFILE),
        patch("src.evidence_foundations_repository.load_measurement_wave", return_value=wave),
        patch("src.evidence_foundations_repository.load_confirmed_question_map", return_value={"1": "Wedding hair"}),
        patch("src.public_evidence_repository.load_public_evidence_matrix", return_value=matrix or {
            "collection": [], "facts": [], "propositions": [], "observations": [], "limitations": []}),
        patch("src.ai_visibility_repository.get_run_queries", return_value=pd.DataFrame([
            {"base_prompt_order": 1, "prompt_text": "Best wedding hair in Brighton?"},
            {"base_prompt_order": 1, "prompt_text": "Best wedding hair in Brighton?"}]))
    ]
    for item in patches:
        stack.enter_context(item)
    at = AppTest.from_file(PAGE).run()
    return at, stack


def test_pending_migration_keeps_existing_evidence_visible_and_totals_separate():
    at, stack = run_page()
    with stack:
        assert not at.exception, [e.value for e in at.exception]
        assert any("migration has not been applied" in info.value for info in at.info)
        published = next(d.value for d in at.dataframe if "published_review_count" in d.value.columns)
        sample = next(d.value for d in at.dataframe if "sampled_review_count" in d.value.columns)
        assert published.iloc[0]["published_review_count"] == 214 and sample.iloc[0]["sampled_review_count"] == 63
        assert not at.button  # this view cannot start a provider call or a production write


def test_context_and_confirmed_question_mappings_are_separate_and_unresolved_is_visible():
    at, stack = run_page(stored=True)
    with stack:
        assert not at.exception, [e.value for e in at.exception]
        context = next(d.value for d in at.dataframe if "raw_label" in d.value.columns and "question_order" not in d.value.columns)
        questions = next(d.value for d in at.dataframe if "question_order" in d.value.columns)
        assert "unresolved" in set(context["resolution"]) and len(questions) == 1
        assert questions.iloc[0]["mapping_basis"] == "reviewer_confirmed"
        assert any("not demand or search volume" in c.value for c in at.caption)
        assert any("Unknown model versions" in info.value for info in at.info)


def test_legacy_context_and_no_benchmark_have_explicit_unknown_states():
    at, stack = run_page(context=[])
    with stack:
        assert not at.exception
        assert any("Historical proposition context is unknown" in info.value for info in at.info)
        assert any("no frozen panel metadata" in info.value for info in at.info)
    at, stack = run_page(no_runs=True)
    with stack:
        assert not at.exception
        assert any("No saved benchmark" in info.value for info in at.info)


def test_matrix_displays_collection_facts_and_unapproved_candidates_separately():
    from src.public_evidence_matrix import build_evidence_matrix
    catalogue, aliases = starter_catalogue()
    matrix = build_evidence_matrix(business={"google_place_id": "place-cisco", "business_name": "Cisco's Karma"},
        listing={"id": "capture-1", "created_at": datetime(2025, 8, 5, tzinfo=timezone.utc),
                 "raw_data": {"phone": "01273 123456"}}, audit=None,
        pages=[{"id": "page-1", "http_status": 200, "text_excerpt": "We offer wedding hair. Call 01273 123456.",
                "url": "https://salon.example/services", "crawled_at": datetime(2025, 8, 5, tzinfo=timezone.utc)}],
        reviews=pd.DataFrame(), platform_links=pd.DataFrame(), checks={}, catalogue=catalogue, aliases=aliases)
    at, stack = run_page(matrix=matrix)
    with stack:
        assert not at.exception and not at.error
        collection = next(d.value for d in at.dataframe if "collection_status" in d.value.columns)
        facts = next(d.value for d in at.dataframe if "comparison_scope" in d.value.columns)
        propositions = next(d.value for d in at.dataframe if "substantive_evidence_breadth" in d.value.columns)
        observations = next(d.value for d in at.dataframe if "evidence_sha256" in d.value.columns)
        assert "NOT_CHECKED" in set(collection["collection_status"])
        assert facts.iloc[0]["state"] == "MATCH"
        assert propositions.iloc[0]["website"].startswith("REVIEW_REQUIRED")
        assert propositions["substantive_evidence_breadth"].isna().all()
        assert observations["source_record_id"].notna().all()
        assert not at.button
