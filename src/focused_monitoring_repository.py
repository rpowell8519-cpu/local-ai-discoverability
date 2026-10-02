"""Read saved focused waves; execute only on an explicit operator request."""
from __future__ import annotations

from src.ai_enrichment_repository import load_entity_aliases
from src.ai_visibility_repository import create_visibility_run, create_visibility_queries, get_run_queries, get_run_results
from src.ai_visibility_runner import execute_calls, finalise_run_from_results, build_retry_plan
from src.evidence_foundations_repository import load_measurement_wave
from src.focused_monitoring import focused_panel, summarise_wave, VERSION


def load_wave_summary(run, businesses):
    return summarise_wave(run=run, wave=load_measurement_wave(str(run["id"])),
        queries=get_run_queries(str(run["id"])).to_dict("records"),
        results=get_run_results(str(run["id"])).to_dict("records"),
        businesses=businesses, aliases=load_entity_aliases())


def execute_focused_wave(*, panel, business, businesses, api_keys, run_id=None,
                         progress_callback=None, status_callback=None):
    """Freeze a plan, then run or explicitly retry its missing/incomplete calls.

    Retrying requires the original saved run identity and exact original plan; no
    canonical report is attached, no evidence is archived and no approvals are written.
    """
    config = panel["configuration"]
    settings = config["settings"]
    if config.get("panel_kind") != "focused" or settings.get("monitoring_version") != VERSION:
        raise ValueError("A frozen focused monitoring plan is required")
    prompts = [{"prompt": p["text"], "source": p.get("source"), "category": p.get("category"),
                "weight": p.get("weight", 1), "family": settings["question_families"][str(i)]}
               for i, p in enumerate(config["prompts"], 1)]
    rebuilt = focused_panel(prompts=prompts, providers=config["providers"], models=config["requested_models"],
        location_context=config["location_context"], primary_group=config["primary_group"],
        benchmark_mode=config["benchmark_mode"], repeat_count=config["repeat_count"],
        comparator_ids=settings["comparator_ids"], cohort_basis=settings["cohort_basis"],
        configured_by=settings["configured_by"], action_ids=settings.get("action_ids", []))
    if rebuilt["configuration_sha256"] != panel["configuration_sha256"] or config != rebuilt["configuration"]:
        raise ValueError("Panel configuration or provider adapter changed; prepare a new panel")
    if str(business["google_place_id"]) in settings["comparator_ids"]:
        raise ValueError("The target cannot be a comparator")
    directory = {str(b["google_place_id"]): b for b in businesses}
    if config["primary_group"] != business.get("primary_group") or any(
            pid not in directory or directory[pid].get("primary_group") != config["primary_group"]
            for pid in settings["comparator_ids"]):
        raise ValueError("Verify comparator identities and business-group eligibility")
    if any(not str(api_keys.get(p) or "").strip() for p in config["providers"]):
        raise ValueError("Every selected provider requires a configured API key")
    if run_id:
        from src.ai_visibility_repository import get_visibility_run
        saved = get_visibility_run(run_id)
        wave = load_measurement_wave(run_id)
        if (not saved or str(saved["target_google_place_id"]) != str(business["google_place_id"])
                or not wave or wave["configuration_sha256"] != panel["configuration_sha256"]):
            raise ValueError("Retry must use this business's exact saved focused wave")
        queries = get_run_queries(run_id)
        expected_queries = len(prompts)*config["repeat_count"]
        if len(queries) != expected_queries:
            raise ValueError("Incomplete saved query plan; prepare a new wave")
        coordinates = set()
        for q in queries.to_dict("records"):
            order, repeat = int(q.get("base_prompt_order") or 0), int(q.get("repeat_index") or 1)
            if (not 1 <= order <= len(prompts) or not 1 <= repeat <= config["repeat_count"]
                    or (order, repeat) in coordinates or q.get("prompt_text") != prompts[order-1]["prompt"]):
                raise ValueError("Saved query plan differs from this panel; do not retry")
            coordinates.add((order, repeat))
        plan = build_retry_plan(queries=queries, results=get_run_results(run_id), providers=config["providers"])
    else:
        run_id = create_visibility_run(target_google_place_id=str(business["google_place_id"]),
            target_business_name=business["business_name"], primary_group=config["primary_group"],
            location_context=config["location_context"], benchmark_mode=config["benchmark_mode"],
            providers=config["providers"], models=config["requested_models"], prompt_count=len(prompts),
            repeat_count=config["repeat_count"], prompts=prompts, panel_kind="focused", panel_settings=settings)
        queries = create_visibility_queries(run_id=run_id, prompts=prompts, repetitions=config["repeat_count"])
        plan = [{**q, "provider": p} for q in queries for p in config["providers"]]
    execute_calls(run_id=run_id, call_plan=plan, models=config["requested_models"], api_keys=api_keys,
        target_google_place_id=str(business["google_place_id"]), target_business_name=business["business_name"],
        known_businesses=businesses, benchmark_mode=config["benchmark_mode"], location_context=config["location_context"],
        progress_callback=progress_callback, status_callback=status_callback)
    status = finalise_run_from_results(run_id=run_id,
        expected_call_count=len(prompts)*config["repeat_count"]*len(config["providers"]))
    return {"run_id": run_id, "status": status, "attempted_calls": len(plan)}
