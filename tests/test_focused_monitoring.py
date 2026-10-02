"""Synthetic fixed panels: denominator, identity, temporal and cohort safeguards."""
import copy

import pytest

from src.focused_monitoring import focused_panel, summarise_wave, compare_waves

DIRECTORY = [{"google_place_id": pid, "business_name": name, "primary_group": "hair_services"}
             for pid,name in (("target", "Synthetic Salon"), ("one", "First Salon"),
                              ("two", "Second Salon"), ("three", "Third Salon"), ("zero", "Zero Salon"))]


def fixture(after=False):
    prompts = [{"prompt": "Which salons offer balayage?", "family": "balayage", "source": "operator_focused", "category": "balayage"}]
    panel = focused_panel(prompts=prompts, providers=["OpenAI"], models={"OpenAI": "requested"},
        location_context="Brighton", primary_group="hair_services", repeat_count=2,
        comparator_ids=["one", "two", "three", "zero"], cohort_basis="Independent local service eligibility", configured_by="Operator")
    wave = {**panel, "series_id": "same-series"}
    run = {"id": "after" if after else "before", "target_google_place_id": "target", "primary_group": "hair_services",
           "providers": ["OpenAI"], "started_at": "2026-10-02T15:00:00+00:00" if after else "2026-09-01T15:00:00+00:00"}
    queries = [{"id": f"q{i}", "base_prompt_order": 1, "repeat_index": i, "prompt_text": prompts[0]["prompt"]} for i in (1,2)]
    results = [{"query_id": q["id"], "provider": "OpenAI", "model": "requested", "status": "completed",
        "response_complete": True, "raw_response": "1. Synthetic Salon\n2. First Salon\n3. Second Salon\n4. Third Salon" if after else "1. First Salon\n2. Second Salon",
        "report_metadata": {"reported_model": "model-2026-09-20", "citation_status": "measured", "citations": [], "search_use_status": "observed", "search_calls": [{"type": "web_search_call"}]}}
        for q in queries]
    return dict(run=run, wave=wave, queries=queries, results=results, businesses=DIRECTORY)


def summary(after=False, **change):
    args = fixture(after)
    args.update(change)
    return summarise_wave(**args)


def test_fixed_cohort_includes_zero_and_context_is_target_minus_median():
    before, after = summary(), summary(True)
    result = compare_waves(before, after)
    assert result["compatible"]
    row = result["rows"][0]
    assert row["before_completed"] == row["after_completed"] == 2
    assert row["target_delta_pp"] == 100 and row["eligible_comparators"] == 4
    assert row["median_comparator_delta_pp"] == 0 and row["contextual_delta_pp"] == 100
    assert next(r for r in before["rows"] if r["google_place_id"]=="zero")["appearance_rate"] == 0
    assert "not a causal effect" in result["interpretation"]


@pytest.mark.parametrize("change", ["absent", "failed", "truncated", "blank", "error"])
def test_missing_failed_and_invalid_answers_block_comparison(change):
    args = fixture(True)
    if change == "absent": args["results"].pop()
    elif change == "failed": args["results"][1]["status"] = "failed"
    elif change == "truncated": args["results"][1]["response_complete"] = False
    elif change == "blank": args["results"][1]["raw_response"] = " "
    else: args["results"][1]["error_message"] = "bad"
    after = summarise_wave(**args)
    assert after["rows"][0]["expected_answers"] == 2 and after["rows"][0]["completed_answers"] == 1
    result = compare_waves(summary(), after)
    assert not result["compatible"] and result["rows"][0]["target_delta_pp"] is None
    assert any("Incomplete waves" in r for r in result["reasons"])


def test_missing_query_still_has_the_frozen_expected_denominator():
    args = fixture(True)
    args["queries"].pop()
    args["results"].pop()
    after = summarise_wave(**args)
    assert all(r["expected_answers"]==2 and r["completed_answers"]==1 for r in after["rows"])
    assert not compare_waves(summary(),after)["compatible"]


@pytest.mark.parametrize("model", [None, "requested-alias", "different-2026-09-21"])
def test_unknown_alias_and_changed_served_models_block_comparison(model):
    args = fixture(True)
    for r in args["results"]: r["report_metadata"]["reported_model"] = model
    result = compare_waves(summary(), summarise_wave(**args))
    assert not result["compatible"] and result["rows"][0]["contextual_delta_pp"] is None


def test_mixed_served_versions_duplicate_results_and_edited_query_cannot_compare():
    for change in ("version", "duplicate", "query"):
        args = fixture(True)
        if change == "version": args["results"][0]["report_metadata"]["reported_model"] = "other-2026-09-22"
        elif change == "duplicate": args["results"].append(copy.deepcopy(args["results"][0]))
        else: args["queries"][0]["prompt_text"] = "Changed prompt"
        assert not compare_waves(summary(), summarise_wave(**args))["compatible"]


def test_changed_configuration_series_core_and_missing_metadata_block_comparison():
    for change in ("configuration", "series", "core", "missing"):
        args = fixture(True)
        if change == "configuration": args["wave"]["configuration_sha256"] = "different"
        elif change == "series": args["wave"]["series_id"] = "different"
        elif change == "core": args["wave"]["panel_kind"] = "core"
        else: args["wave"] = None
        assert not compare_waves(summary(), summarise_wave(**args))["compatible"]


def test_mentions_and_repeated_slots_do_not_inflate_recommendations():
    args = fixture(True)
    for r in args["results"]:
        r["raw_response"] = "Synthetic Salon mentioned in prose.\n1. First Salon\n2. First Salon"
        r["target_recommended"] = True
    rows = summarise_wave(**args)["rows"]
    assert next(r for r in rows if r["google_place_id"]=="target")["appearances"] == 0
    assert next(r for r in rows if r["google_place_id"]=="one")["appearances"] == 2


def test_fuzzy_possible_target_is_unknown_and_not_promoted():
    args = fixture(True)
    for r in args["results"]: r["raw_response"] = "1. Synthetic Salon Brighton"
    view = summarise_wave(**args)
    assert view["unapproved_recommendations"]
    row = next(r for r in view["rows"] if r["google_place_id"]=="target")
    assert row["appearance_rate"] is None and row["identity_status"] == "needs_review"
    result = compare_waves(summary(), view)
    assert result["rows"][0]["target_delta_pp"] is None


def test_insufficient_comparators_keep_raw_delta_but_hide_context():
    result = compare_waves(summary(), summary(True), minimum_comparators=5)
    assert result["rows"][0]["target_delta_pp"] == 100
    assert result["rows"][0]["contextual_delta_pp"] is None
    assert any("Insufficient" in w for w in result["warnings"])


def test_action_bundles_overlaps_unknown_dates_and_evidence_timing_visible():
    actions = [{"action_id": "one", "google_place_id": "target", "implemented_date": "2026-09-15", "bundle_id": "bundle"},
               {"action_id": "two", "google_place_id": "target", "implemented_date": "2026-09-15"},
               {"action_id": "unknown", "google_place_id": "target", "implemented_date": None},
               {"action_id": "irrelevant", "google_place_id": "one", "implemented_date": "2026-09-15"}]
    evidence = [{"captured_at": "2026-09-10T00:00:00+00:00", "source_record_id": "later"}, {"captured_at": None}]
    result = compare_waves(summary(), summary(True), interventions=actions, evidence=evidence)
    assert len(result["interval_actions"]) == 2
    assert any("Overlapping" in w for w in result["warnings"])
    assert any("bundle" in w for w in result["warnings"])
    assert any("unknown for action" in w for w in result["warnings"])
    assert result["evidence_freshness"][0]["baseline_timing"] == "captured_after_baseline"
    assert result["evidence_freshness"][1]["baseline_timing"] == "unknown"


def test_order_business_and_coverage_must_match():
    for change in ("same", "reverse", "business", "coverage"):
        after = summary(True)
        if change == "same": after["run_id"] = "before"
        elif change == "reverse": after["started_at"] = "2020-01-01T00:00:00+00:00"
        elif change == "business": after["target_google_place_id"] = "one"
        else: after["rows"].pop()
        assert not compare_waves(summary(), after)["compatible"]


@pytest.mark.parametrize("field,value", [("models", {"OpenAI":"edited"}), ("benchmark_mode", "model_memory"),
    ("location_context", "Elsewhere"), ("repeat_count", 5), ("status", "running")])
def test_mutated_run_settings_and_unfinished_runs_block_comparison(field,value):
    args=fixture(True)
    args["run"][field]=value
    assert not compare_waves(summary(),summarise_wave(**args))["compatible"]


def test_family_mapping_and_cohort_change_panel_identity():
    base = fixture()["wave"]
    config = base["configuration"]
    for change in ("family", "cohort"):
        kwargs = dict(prompts=[{"prompt": config["prompts"][0]["text"], "family": "balayage", "source": "operator_focused", "category": "balayage"}],
            providers=config["providers"], models=config["requested_models"], location_context=config["location_context"],
            primary_group=config["primary_group"], repeat_count=2, comparator_ids=["one", "two", "three", "zero"],
            cohort_basis="Independent local service eligibility", configured_by="Operator")
        if change == "family": kwargs["prompts"][0]["family"] = "wedding hair"
        else: kwargs["comparator_ids"].pop()
        assert focused_panel(**kwargs)["panel_id"] != base["panel_id"]


def test_verified_dateless_claude_snapshots_are_provider_scoped():
    from src.focused_monitoring import _versioned_identifier
    assert _versioned_identifier('claude-sonnet-5-5', 'Claude')
    assert _versioned_identifier('claude-sonnet-5', 'Claude')
    assert not _versioned_identifier('claude-sonnet-5-5', 'OpenAI')
    assert not _versioned_identifier('claude-sonnet-4-5', 'Claude')
    assert not _versioned_identifier('claude-sonnet-latest', 'Claude')
    assert not _versioned_identifier('claude-sonnet-99', 'Claude')
    assert not _versioned_identifier('gemini-3.6-flash', 'Gemini')
