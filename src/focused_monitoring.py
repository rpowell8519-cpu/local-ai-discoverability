"""Deterministic focused measurement; no network, persistence or causal inference."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import hashlib
import json
import re
from statistics import median

import pandas as pd

from src.ai_recommendation_intelligence import build_recommendation_records
from src.measurement_panels import build_panel, comparison_compatibility
from src.report_identity import find_possible_target_names

VERSION = "focused-monitoring-v1"


def focused_panel(*, prompts, providers, models, location_context, primary_group,
                  repeat_count, comparator_ids, cohort_basis, configured_by,
                  action_ids=(), benchmark_mode="search_grounded"):
    """Explicit question families/cohort, fixed before observing recommendation outcomes."""
    if not str(cohort_basis).strip() or not str(configured_by).strip():
        raise ValueError("Record the cohort selection basis and configuring operator")
    if not prompts or any(not str(p.get("family") or "").strip() or not str(p.get("prompt") or "").strip() for p in prompts):
        raise ValueError("Each focused question needs exact text and an explicit family")
    ids = [str(x) for x in comparator_ids]
    if len(ids) != len(set(ids)) or any(not x.strip() for x in ids):
        raise ValueError("Comparator identities must be distinct and nonblank")
    families = {str(i): p["family"].strip() for i, p in enumerate(prompts, 1)}
    return build_panel(prompts=prompts, providers=providers, models=models,
        location_context=location_context, primary_group=primary_group,
        repeat_count=repeat_count, benchmark_mode=benchmark_mode, panel_kind="focused",
        settings={"monitoring_version": VERSION, "question_families": families,
                  "comparator_ids": sorted(ids), "cohort_basis": cohort_basis.strip(),
                  "configured_by": configured_by.strip(), "action_ids": sorted(set(map(str, action_ids)))})


def _date(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else None
    except (TypeError, ValueError):
        return None


def _versioned_identifier(value, provider=None):
    # Verified 2026-10-02: Claude's 4.6+ canonical IDs pin snapshots even without dates.
    # Explicitly reviewed IDs only; do not accept arbitrary future IDs or older aliases.
    # https://platform.claude.com/docs/en/about-claude/models/model-ids-and-versions
    if provider == "Claude" and value in {"claude-sonnet-5", "claude-sonnet-5-5"}:
        return True
    # Other undated identifiers remain unknown. This lexical check cannot verify weights.
    return bool(value and re.search(r"(?:20\d{2}-\d{2}-\d{2}|20\d{6}|-\d{3}$)", str(value)))


def summarise_wave(*, run, wave, queries, results, businesses, aliases=None):
    """One recommendation per linked business/valid answer; fuzzy names stay unapproved.

    Denominators use the saved expected query/provider grid, including missing answers.
    Every monitored business, including zero appearances, is defined by the fixed cohort.
    """
    config = (wave or {}).get("configuration") or {}
    settings = config.get("settings") or {}
    families = settings.get("question_families") or {}
    providers = config.get("providers") or run.get("providers") or []
    target = str(run["target_google_place_id"])
    ids = [target, *settings.get("comparator_ids", [])]
    directory = {str(b["google_place_id"]): b for b in businesses}
    issues = []
    if not wave:
        issues.append("Historical panel metadata is unavailable")
    elif wave.get("panel_kind") != "focused" or settings.get("monitoring_version") != VERSION:
        issues.append("No frozen focused question-family/cohort plan is available")
    if run.get("status") and run["status"] != "completed":
        issues.append("Run has not been marked completed")
    if wave:
        checksum = hashlib.sha256(json.dumps(config, sort_keys=True, ensure_ascii=False,
            separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        if checksum != wave.get("configuration_sha256") or wave.get("panel_id") != checksum:
            issues.append("Frozen panel fingerprint does not match its configuration")
        if wave.get("run_id") and str(wave["run_id"]) != str(run["id"]):
            issues.append("Panel metadata belongs to another run")
        if set(providers) != set(run.get("providers") or []) or config.get("primary_group") != run.get("primary_group"):
            issues.append("Saved run provider/business group differs from the frozen panel")
        for run_field, config_field in (("models", "requested_models"), ("benchmark_mode", "benchmark_mode"),
                ("location_context", "location_context"), ("repeat_count", "repeat_count")):
            if run_field in run and run[run_field] != config.get(config_field):
                issues.append(f"Saved run {run_field} differs from the frozen panel")
        if set(families) != {str(i) for i in range(1, len(config.get("prompts", []))+1)}:
            issues.append("Frozen question-family mapping is incomplete")
    if target in settings.get("comparator_ids", []):
        issues.append("The target cannot also be a comparator")
    if not settings.get("cohort_basis"):
        issues.append("Independent comparator selection basis is unavailable")
    for pid in ids:
        if pid not in directory:
            issues.append(f"Business identity is unavailable: {pid}")
        elif directory[pid].get("primary_group") != run.get("primary_group"):
            issues.append(f"Business is outside the selected business group: {pid}")
    query_by_id = {str(q["id"]): q for q in queries}
    if len(query_by_id) != len(queries):
        issues.append("Duplicate saved query identities")
    expected = defaultdict(set)
    coordinates = {(int(q.get("base_prompt_order") or q.get("prompt_order") or 0), int(q.get("repeat_index") or 1)): str(q["id"]) for q in queries}
    for order, family in families.items():
        for repeat in range(1, int(config.get("repeat_count") or 1)+1):
            query_id = coordinates.get((int(order), repeat), f"missing-query:{order}:{repeat}")
            for provider in providers:
                expected[(family, provider)].add(query_id)
    if config:
        planned = len(config.get("prompts", [])) * int(config.get("repeat_count") or 1)
        if len(queries) != planned:
            issues.append("Saved query count differs from the frozen panel")
        seen_coordinates = set()
        for q in queries:
            order = int(q.get("base_prompt_order") or q.get("prompt_order") or 0)
            repeat = int(q.get("repeat_index") or 1)
            coordinate = (order, repeat)
            prompts = config.get("prompts", [])
            if (not 1 <= order <= len(prompts) or not 1 <= repeat <= int(config["repeat_count"])
                    or coordinate in seen_coordinates or q.get("prompt_text") != prompts[order-1]["text"]):
                issues.append("Saved query text/repetition differs from the frozen panel")
            seen_coordinates.add(coordinate)
    valid, lookup, metadata = [], {}, []
    for row in results:
        key = (str(row.get("query_id")), row.get("provider"))
        if key in lookup:
            issues.append("Multiple saved answers for a query/provider; resolve retries explicitly")
        lookup[key] = row
        q = query_by_id.get(key[0])
        if q is None or key[1] not in providers:
            issues.append("Saved answer is outside the panel's query/provider grid")
            continue
        item = {**row, **{k: q.get(k) for k in ("base_prompt_order", "prompt_order", "repeat_index", "prompt_text", "prompt_category")}}
        if (row.get("status") == "completed" and row.get("response_complete") is True
                and not row.get("error_message") and str(row.get("raw_response") or "").strip()):
            valid.append(item)
            meta = row.get("report_metadata") or {}
            metadata.append({"query_id": key[0], "provider": key[1],
                "response_id": str(row.get("id") or ""), "saved_at": str(row.get("created_at") or ""),
                "reported_model": meta.get("reported_model"), "citation_status": meta.get("citation_status", "unavailable"),
                "citations": meta.get("citations", []), "search_use_status": meta.get("search_use_status", "unavailable"),
                "search_calls": meta.get("search_calls", [])})
    records = build_recommendation_records(results=pd.DataFrame(valid), businesses=pd.DataFrame(businesses),
        aliases=aliases, target_google_place_id=target, commercial_competitor_ids=set(ids[1:]),
        primary_group=run.get("primary_group") or "").to_dict("records") if valid else []
    linked, unapproved = [], []
    for record in records:
        if record.get("resolution_status") in {"exact", "exact_group"} and record.get("google_place_id"):
            linked.append(record)
        else:
            unapproved.append(record)
    rows = []
    for (family, provider), query_ids in sorted(expected.items()):
        completed = {str(r["query_id"]) for r in valid if r["provider"] == provider and str(r["query_id"]) in query_ids}
        for pid in ids:
            appeared = {str(r["query_id"]) for r in linked if r["provider"] == provider and str(r["query_id"]) in completed and str(r["google_place_id"]) == pid}
            names = [{"business_name": r["raw_business_name"], "recommendations": 1} for r in unapproved
                     if r["provider"] == provider and str(r["query_id"]) in completed]
            possible = find_possible_target_names(str(directory.get(pid, {}).get("business_name") or ""), names)
            identity_unknown = bool(possible) or pid not in directory
            rows.append({"google_place_id": pid, "business_name": directory.get(pid, {}).get("business_name"),
                "family": family, "provider": provider, "expected_answers": len(query_ids),
                "completed_answers": len(completed), "missing_or_excluded": len(query_ids)-len(completed),
                "appearances": len(appeared), "appearance_rate": len(appeared)/len(completed) if completed and not identity_unknown else None,
                "identity_status": "needs_review" if identity_unknown else "linked", "unapproved_possible_names": possible})
    versions, reported = {}, {}
    for provider in providers:
        values = {m["reported_model"] for m in metadata if m["provider"] == provider and m["reported_model"]}
        reports = [m for m in metadata if m["provider"] == provider]
        reported[provider] = sorted(values)
        if len(values) == 1 and reports and all(_versioned_identifier(m["reported_model"], provider) for m in reports):
            versions[provider] = next(iter(values))
    return {"version": VERSION, "run_id": str(run["id"]), "target_google_place_id": target,
        "started_at": str(run.get("started_at") or ""), "wave": wave,
        "issues": sorted(set(issues)), "served_versions": versions, "reported_models": reported,
        "rows": rows, "answer_metadata": metadata, "linked_recommendations": linked,
        "unapproved_recommendations": unapproved,
        "limitations": ["Rates count recommendations per completed answer, not raw mentions or market share.",
            "Fuzzy names remain unapproved; possible names keep a business's rate unknown.",
            "Name linking reads the current canonical directory/aliases; linked records retain the resolution basis. This is a projection, not a frozen historical identity assessment.",
            "Reported dated/versioned identifiers do not verify the provider's internal model weights."]}


def compare_waves(before, after, *, interventions=(), evidence=(), minimum_comparators=3):
    if isinstance(minimum_comparators, bool) or minimum_comparators < 1:
        raise ValueError("A positive comparator threshold is required")
    compatibility = comparison_compatibility(before.get("wave"), after.get("wave"),
        before_model_versions=before["served_versions"], after_model_versions=after["served_versions"])
    reasons = [*compatibility["reasons"], *before["issues"], *after["issues"]]
    if before["target_google_place_id"] != after["target_google_place_id"]:
        reasons.append("Waves belong to different target businesses")
    start, finish = _date(before["started_at"]), _date(after["started_at"])
    if before["run_id"] == after["run_id"] or not start or not finish or finish <= start:
        reasons.append("Select distinct dated waves in before/after order")
    b_rows = {(r["google_place_id"], r["family"], r["provider"]): r for r in before["rows"]}
    a_rows = {(r["google_place_id"], r["family"], r["provider"]): r for r in after["rows"]}
    if b_rows.keys() != a_rows.keys():
        reasons.append("Family/provider/cohort coverage differs")
    if any(r["completed_answers"] != r["expected_answers"] for r in [*before["rows"], *after["rows"]]):
        reasons.append("Incomplete waves: completion/denominator differences prevent a strict comparison")
    reasons = sorted(set(reasons))
    compatible = not reasons
    rows, warnings = [], []
    target = before["target_google_place_id"]
    for key, b in b_rows.items():
        if key[0] != target:
            continue
        a = a_rows.get(key)
        if not a:
            continue
        delta = a["appearance_rate"]-b["appearance_rate"] if compatible and a["appearance_rate"] is not None and b["appearance_rate"] is not None else None
        comparator_deltas = []
        excluded = []
        for ckey, cb in b_rows.items():
            if ckey[0] == target or ckey[1:] != key[1:]:
                continue
            ca = a_rows.get(ckey)
            if compatible and ca and cb["appearance_rate"] is not None and ca["appearance_rate"] is not None:
                comparator_deltas.append(ca["appearance_rate"]-cb["appearance_rate"])
            else:
                excluded.append(ckey[0])
        enough = len(comparator_deltas) >= minimum_comparators
        centre = median(comparator_deltas) if enough else None
        if compatible and not enough:
            warnings.append(f"Insufficient eligible comparators for {key[1]} / {key[2]}: {len(comparator_deltas)} of {minimum_comparators} required")
        if delta is None and compatible:
            warnings.append(f"Target identity needs review for {key[1]} / {key[2]}")
        rows.append({"family": key[1], "provider": key[2], "before_appearances": b["appearances"],
            "before_completed": b["completed_answers"], "before_expected": b["expected_answers"],
            "after_appearances": a["appearances"], "after_completed": a["completed_answers"], "after_expected": a["expected_answers"],
            "target_delta_pp": delta*100 if delta is not None else None,
            "eligible_comparators": len(comparator_deltas), "excluded_comparator_ids": excluded,
            "median_comparator_delta_pp": centre*100 if centre is not None else None,
            "contextual_delta_pp": (delta-centre)*100 if delta is not None and centre is not None else None})
    relevant = []
    family_labels = {r["family"] for r in rows}
    for item in interventions:
        action = item.get("record", item)
        if str(action.get("google_place_id")) != target:
            continue
        if action.get("focused_families") and not family_labels.intersection(action["focused_families"]):
            continue
        if action.get("baseline_run_id") and str(action["baseline_run_id"]) != before["run_id"]:
            warnings.append(f"Action {action.get('action_id')} is linked to another baseline run")
        day = action.get("implemented_date")
        if not day:
            warnings.append(f"Implementation date unknown for action {action.get('action_id')}")
        elif start and finish and start.date() <= datetime.fromisoformat(str(day)).date() <= finish.date():
            relevant.append(action)
            warnings.append("Implementation dates have day precision; within-day ordering is unknown")
    if len(relevant) > 1:
        warnings.append("Overlapping actions in the measurement interval; individual effects cannot be separated")
    if any(a.get("bundle_id") for a in relevant):
        warnings.append("A simultaneous-action bundle falls in the measurement interval")
    freshness = []
    for item in evidence:
        observed = _date(item.get("captured_at"))
        status = "unknown" if not observed or not start else "available_by_baseline" if observed <= start else "captured_after_baseline"
        freshness.append({**item, "baseline_timing": status,
            "age_days_at_followup": (finish-observed).total_seconds()/86400 if observed and finish else None})
    if not evidence:
        warnings.append("Evidence freshness has not been selected")
    elif any(e["baseline_timing"] != "available_by_baseline" for e in freshness):
        warnings.append("Some evidence dates are unknown or after baseline; do not treat it as baseline exposure")
    return {"version": VERSION, "before_run_id": before["run_id"], "after_run_id": after["run_id"],
        "compatible": compatible, "reasons": reasons, "rows": rows, "warnings": sorted(set(warnings)),
        "evidence_freshness": freshness, "interval_actions": relevant,
        "interpretation": "Target change minus the median eligible comparator change is descriptive context, not a causal effect. Comparators share the same answers, family, provider and panel; repeats are not independent experiments."}
