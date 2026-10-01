"""Deterministic tests for provenance, ambiguous labels and compatible benchmark panels."""
import copy
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import patch

import pandas as pd
import pytest

from src.ai_discovery_repository import create_discovery_run
from src.ai_visibility_repository import create_visibility_run
from src.evidence_foundations_repository import record_measurement_wave
from src.measurement_panels import build_panel, comparison_compatibility
from src.proposition_catalog import starter_catalogue, resolve_labels, build_tested_intent_links
from src.review_profile_metrics import google_profile_observation, review_sample_metrics
from src.review_ingestion import SOURCE, SOURCE_YELP

CATALOGUE, ALIASES = starter_catalogue()


def panel(**overrides):
    params = dict(prompts=[{"prompt": "Best salon in Brighton for balayage", "source": "owner_brief"}],
                  providers=["OpenAI"], models={"OpenAI": "requested-model"}, location_context="Brighton",
                  benchmark_mode="search_grounded", repeat_count=3, primary_group="hair_services")
    params.update(overrides)
    return build_panel(**params)


def test_known_alias_resolves_without_rewriting_the_original_label():
    result = resolve_labels(["Wedding hair", "Upholstry Cleaning"], CATALOGUE, ALIASES)
    assert result[0]["proposition_key"] == "bridal_hair" and result[0]["raw_label"] == "Wedding hair"
    assert result[1]["resolution"] == "unresolved" and result[1]["proposition_key"] is None


def test_conflicting_aliases_are_ambiguous_not_first_match():
    aliases = [*ALIASES, {"alias_text": "Wedding hair", "proposition_key": "curly_hair"}]
    assert resolve_labels(["Wedding hair"], CATALOGUE, aliases)[0]["resolution"] == "ambiguous"


@pytest.mark.parametrize("context", [None, []])
def test_unknown_historical_context_is_not_inferred_from_prompt_words(context):
    result = build_tested_intent_links({"id": "run", "target_propositions": context},
                                [{"base_prompt_order": 1, "prompt_text": "Best balayage salon?"}], {}, CATALOGUE, ALIASES)
    assert result["context_status"] == "unknown"
    assert result["tested_questions"][0]["resolution"] == "not_mapped"


def test_context_is_not_proof_of_tested_intent_and_repeats_are_one_question():
    questions = [{"base_prompt_order": 1, "prompt_text": "Where should I go for wedding hair?"}] * 3
    result = build_tested_intent_links({"id": "run", "target_propositions": ["Balayage", "Wedding hair"]},
                                questions, {"1": "Wedding hair"}, CATALOGUE, ALIASES)
    assert len(result["run_context"]) == 2 and len(result["tested_questions"]) == 1
    assert result["tested_questions"][0]["proposition_key"] == "bridal_hair"
    assert result["tested_questions"][0]["mapping_basis"] == "reviewer_confirmed"


@pytest.mark.parametrize("labels,keys", [(["Hair extensions", "Children's haircuts"], ["hair_extensions", "childrens_haircuts"]),
                                        (["private dining", "a great wine list"], ["private_dining", "wine_selection"])])
def test_cisco_and_wild_flor_existing_run_contexts_resolve(labels, keys):
    assert [r["proposition_key"] for r in resolve_labels(labels, CATALOGUE, ALIASES)] == keys


def raw_listing(**raw):
    return {"id": "source-uuid", "google_place_id": "place", "created_at": datetime(2025, 8, 5, tzinfo=timezone.utc),
            "raw_data": raw}


def test_published_count_is_from_profile_not_from_text_sample():
    observation = google_profile_observation(raw_listing(rating="4.7", reviews=214))
    reviews = pd.DataFrame([{"google_place_id": "place", "source": SOURCE, "review_id": str(i),
                             "review_text": "Helpful", "review_datetime_utc": "2025-08-01"} for i in range(63)])
    sample = review_sample_metrics(reviews)[0]
    assert observation["published_review_count"] == 214 and observation["rating"] == 4.7
    assert sample["sampled_review_count"] == 63
    assert observation["latest_published_review_at"] is None and observation["recent_review_velocity"] is None
    assert observation["observed_at"].startswith("2025-08-05")


@pytest.mark.parametrize("count", [None, "unknown", -1, 3.5, True, float("nan")])
def test_invalid_or_missing_profile_total_stays_unknown(count):
    assert google_profile_observation(raw_listing(reviews=count))["published_review_count"] is None


def test_actual_zero_is_distinct_from_unknown():
    assert google_profile_observation(raw_listing(reviews=0))["published_review_count"] == 0


def test_profile_capture_requires_identity_and_real_timestamp():
    raw = raw_listing(reviews=10)
    raw["created_at"] = None
    with pytest.raises(ValueError, match="timezone"):
        google_profile_observation(raw)
    raw["created_at"] = datetime(2099, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="future"):
        google_profile_observation(raw)


def test_samples_deduplicate_by_source_and_exclude_blank_text_and_unknown_dates():
    frame = pd.DataFrame([
        {"google_place_id": "place", "source": SOURCE, "review_id": "one", "review_text": "Helpful", "review_datetime_utc": "bad date"},
        {"google_place_id": "place", "source": SOURCE, "review_id": "one", "review_text": "Helpful", "review_datetime_utc": "bad date"},
        {"google_place_id": "place", "source": SOURCE_YELP, "review_id": "one", "review_text": "Helpful", "review_datetime_utc": None},
        {"google_place_id": "place", "source": SOURCE, "review_id": "empty", "review_text": " ", "review_datetime_utc": None},
    ])
    rows = review_sample_metrics(frame)
    assert len(rows) == 2 and all(r["sampled_review_count"] == 1 and r["latest_known_in_sample"] is None for r in rows)


def test_panel_hash_is_reproducible_and_provider_order_is_irrelevant():
    params = dict(providers=["OpenAI", "Gemini"], models={"OpenAI": "o", "Gemini": "g"})
    assert panel(**params) == panel(**{**params, "providers": ["Gemini", "OpenAI"]})


@pytest.mark.parametrize("change", [
    {"panel_kind": "focused"}, {"benchmark_mode": "model_memory"}, {"repeat_count": 1},
    {"location_context": "Hove"}, {"models": {"OpenAI": "new-model"}},
    {"prompts": [{"prompt": "Another natural variant"}]}, {"settings": {"new_setting": True}},
])
def test_material_config_changes_have_a_new_panel_identity(change):
    assert panel()["panel_id"] != panel(**change)["panel_id"]


def test_unknown_metadata_or_served_model_version_blocks_comparison():
    assert not comparison_compatibility(None, panel())["compatible"]
    before = {**panel(), "series_id": "series"}
    assert not comparison_compatibility(before, copy.deepcopy(before))["compatible"]
    versions = {"OpenAI": "verified-snapshot"}
    assert comparison_compatibility(before, before, before_model_versions=versions, after_model_versions=versions)["compatible"]
    after = {**panel(panel_kind="focused"), "series_id": "series"}
    assert not comparison_compatibility(before, after, before_model_versions=versions, after_model_versions=versions)["compatible"]


class Result:
    def __init__(self, scalar):
        self.value = scalar
    def scalar_one(self):
        return self.value
    def scalar_one_or_none(self):
        return self.value


class Connection:
    def __init__(self, ready=False, series=None):
        self.ready, self.series, self.calls = ready, series, []
    def execute(self, statement, params=None):
        sql = str(statement)
        self.calls.append((sql, params))
        if "to_regclass" in sql:
            return Result(self.ready)
        if "select w.series_id" in sql:
            return Result(self.series)
        return Result(None)


class Engine:
    def __init__(self, connection):
        self.connection = connection
    @contextmanager
    def begin(self):
        yield self.connection


def test_unapplied_migration_does_not_create_or_guess_wave_history():
    connection = Connection()
    assert not record_measurement_wave(connection, run_id="run", target_id="place", panel=panel())
    assert len(connection.calls) == 1


def test_matching_configuration_reuses_series_and_writes_a_distinct_wave():
    connection = Connection(ready=True, series="existing-series")
    assert record_measurement_wave(connection, run_id="new-wave", target_id="place", panel=panel())
    assert "pg_advisory_xact_lock" in connection.calls[1][0]
    parameters = connection.calls[-1][1]
    assert parameters["series_id"] == "existing-series" and parameters["run_id"] == "new-wave"


def test_visibility_creation_populates_existing_propositions_and_records_panel_atomically():
    connection = Connection(ready=True)
    with patch("src.ai_visibility_repository.get_engine", return_value=Engine(connection)):
        run = create_visibility_run(target_google_place_id="place", target_business_name="Example", primary_group="hair_services",
                                    location_context="Brighton", providers=["OpenAI"], models={"OpenAI": "model"}, prompt_count=1,
                                    target_propositions=["Wedding hair"], prompts=[{"prompt": "Wedding hair in Brighton?"}])
    sql, parameters = connection.calls[0]
    assert "target_propositions" in sql and json.loads(parameters["target_propositions"]) == ["Wedding hair"]
    assert connection.calls[-1][1]["run_id"] == run


def test_discovery_creation_preserves_original_context_and_unresolved_target_identity():
    connection = Connection(ready=True)
    with patch("src.ai_discovery_repository.get_engine", return_value=Engine(connection)):
        created = create_discovery_run(target_business_name="Unknown", target_google_place_id=None,
                                       target_resolution_status="unresolved", target_dataset_match_name=None,
                                       primary_group="hair_services", category_label="Salon", location_context="Brighton",
                                       website="", description="", propositions=["Unrecognised proposition"],
                                       providers=["OpenAI"], models={"OpenAI": "model"}, prompt_count=1, repeat_count=1,
                                       prompts=[{"prompt": "A salon in Brighton?"}])
    sql, parameters = connection.calls[0]
    assert "if panel" not in sql
    assert json.loads(parameters["target_propositions"]) == ["Unrecognised proposition"]
    assert created["target_google_place_id"].startswith("discovery:")
    assert connection.calls[-1][1]["run_id"] == created["run_id"]
