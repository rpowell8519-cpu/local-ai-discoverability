from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from typing import Any

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.ai_recommendation_intelligence import (
    build_business_share_table,
    build_recommendation_records,
    normalise_name,
)
from src.database import get_engine
from src.poc_audit_payload import (
    build_baseline_validation,
    build_poc_audit_payload,
    freeze_ai_response,
    freeze_review_set,
)
from src.review_analysis import build_review_benchmark
from src.review_profiles import get_review_profile


PROVIDER_LABELS = {
    "openai": "OpenAI",
    "anthropic": "Claude",
    "claude": "Claude",
    "gemini": "Gemini",
}


def _rows(connection, statement: str, parameters: Mapping[str, Any] | None = None):
    return [
        dict(row)
        for row in connection.execute(text(statement), dict(parameters or {})).mappings().all()
    ]


def _freeze_responses(
    results: list[dict[str, Any]], *, config: Mapping[str, Any]
) -> dict[str, Any]:
    explicit_terms = tuple(str(item).casefold() for item in config["target_explicit_terms"])
    indirect_terms = tuple(str(item).casefold() for item in config.get("target_indirect_terms", ()))
    frozen = []
    for result in results:
        raw = str(result.get("raw_response") or "")
        lowered = raw.casefold()
        explicit = [
            {"term": term, "credible": True}
            for term in explicit_terms
            if term in lowered
        ]
        indirect = [
            {
                "term": term,
                "credible": False,
                "assessment": "Inspected and not a uniquely identifying target reference.",
            }
            for term in indirect_terms
            if term in lowered
        ]
        persisted_recommended = bool(result.get("target_recommended"))
        frozen.append(
            freeze_ai_response(
                result,
                explicit_matches=explicit,
                indirect_matches=indirect,
                parser_reconciliation={
                    "target_correct": bool(explicit) == persisted_recommended,
                    "persisted_target_mentioned": bool(result.get("target_mentioned")),
                    "persisted_target_recommended": persisted_recommended,
                    "excluded_from_metrics": not (
                        str(result.get("status")) == "completed"
                        and bool(result.get("response_complete"))
                    ),
                },
                verification_notes=config["response_verification_note"],
            )
        )
    return build_baseline_validation(
        frozen,
        expected_responses=int(config["expected_responses"]),
        status=str(config["baseline_validation_status"]),
        verification_method_version=str(config["verification_method_version"]),
    )


def _recommendation_evidence(
    results: pd.DataFrame,
    businesses: pd.DataFrame,
    aliases: pd.DataFrame,
    *,
    config: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records = build_recommendation_records(
        results=results,
        businesses=businesses,
        aliases=aliases,
        target_google_place_id=config["target_google_place_id"],
        commercial_competitor_ids=set(),
        primary_group=config["primary_group"],
    )
    adjudications = config.get("slot_adjudications", {})
    slots: list[dict[str, Any]] = []
    business_rows: list[dict[str, Any]] = []
    for source in records.to_dict("records"):
        item = dict(source)
        raw_name = str(item["raw_business_name"])
        item["source_raw_business_name"] = raw_name
        decision = adjudications.get(raw_name)
        if decision:
            item["google_place_id"] = decision.get("google_place_id")
            item["business_name"] = decision["business_name"]
            item["resolution_method"] = decision["resolution_method"]
            if not decision.get("google_place_id"):
                item["raw_business_name"] = decision["business_name"]
        else:
            item["resolution_method"] = item.get("resolution_status")
        non_business = normalise_name(raw_name).startswith(
            tuple(config.get("non_business_prefixes", ()))
        )
        item["slot_disposition"] = "non_business" if non_business else "business"
        slots.append(item)
        if not non_business:
            business_rows.append(item)
    market = build_business_share_table(pd.DataFrame(business_rows)).to_dict("records")
    target_id = str(config["target_google_place_id"])
    if not any(str(item.get("google_place_id")) == target_id for item in market):
        market.append({
            "google_place_id": target_id,
            "business_name": config["target_business_name"],
            "classification": "Target",
            "recommendations": 0,
            "share_of_recommendation": 0.0,
            "position_weighted_share": 0.0,
            "average_position": None,
            "providers": 0,
        })
    return slots, market


def _freeze_websites(connection, definitions: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    audits = []
    for definition in definitions:
        run_rows = _rows(
            connection,
            "select * from website_audit_runs where id = :run_id",
            {"run_id": definition["website_audit_run_id"]},
        )
        if len(run_rows) != 1:
            raise ValueError(f"Missing website audit {definition['website_audit_run_id']}")
        if run_rows[0].get("audit_status") not in {"completed", "partial"}:
            raise ValueError(f"Website audit is not complete: {definition['website_audit_run_id']}")
        pages = _rows(
            connection,
            """
            select * from website_audit_pages
            where audit_run_id = :run_id
            order by crawled_at, id
            """,
            {"run_id": definition["website_audit_run_id"]},
        )
        if not pages:
            raise ValueError(f"Website audit has no pages: {definition['website_audit_run_id']}")
        audits.append({**run_rows[0], **dict(definition), "pages": pages})
    return audits


def _freeze_reviews(connection, definitions: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    review_sets = []
    for definition in definitions:
        status = str(definition.get("status", "complete"))
        if status == "exception":
            review_sets.append(
                freeze_review_set(
                    google_place_id=definition["google_place_id"],
                    business_name=definition["business_name"],
                    records=[],
                    status="exception",
                    exception=dict(definition["exception"]),
                )
            )
            continue

        limit = int(definition.get("record_count", 0))
        batch_id = definition.get("import_batch_id")
        batch_clause = (
            "and import_batch_id = cast(:batch_id as uuid)"
            if batch_id
            else ""
        )
        records = _rows(
            connection,
            f"""
            select id, review_id, google_place_id, business_name,
                   review_text, review_rating, review_timestamp,
                   review_datetime_utc, review_link, source,
                   source_file_name, import_batch_id, imported_at,
                   updated_at, owner_answer
            from business_reviews
            where google_place_id = :place_id
              {batch_clause}
            order by review_datetime_utc desc nulls last,
                     imported_at desc, id desc
            limit :record_limit
            """,
            {
                "place_id": definition["google_place_id"],
                "batch_id": definition["import_batch_id"],
                "record_limit": limit,
            },
        )
        if len(records) != limit:
            raise ValueError(
                f"Expected {limit} reviews for {definition['business_name']}; found {len(records)}"
            )
        review_sets.append(
            freeze_review_set(
                google_place_id=definition["google_place_id"],
                business_name=definition["business_name"],
                records=records,
                status="complete",
            )
        )
    return review_sets


def _review_diagnostic(
    review_sets: list[dict[str, Any]], *, target_place_id: str, profile_key: str
) -> dict[str, Any]:
    records = [
        record
        for item in review_sets
        if item["status"] == "complete"
        for record in item["records"]
    ]
    frame = pd.DataFrame(records)
    frame["owner_answer"] = frame["owner_response_present"].map(
        lambda present: "present" if bool(present) else ""
    )
    benchmark = build_review_benchmark(
        target_google_place_id=target_place_id,
        reviews=frame,
        business_names={item["google_place_id"]: item["business_name"] for item in review_sets},
        profile=get_review_profile(profile_key),
    )
    return {key: value.to_dict("records") for key, value in benchmark.items()}


def _market_row(market: list[dict[str, Any]], place_id: str) -> dict[str, Any]:
    matches = [row for row in market if str(row.get("google_place_id")) == place_id]
    if len(matches) != 1:
        raise ValueError(f"Canonical market has {len(matches)} rows for {place_id}")
    return matches[0]


def _question_performance(
    *,
    baseline: Mapping[str, Any],
    slots: list[dict[str, Any]],
    target_place_id: str,
    providers: list[str],
    prompt_count: int,
) -> list[dict[str, Any]]:
    """Summarise canonically resolved recommendations for each customer question."""
    complete_responses = [
        item for item in baseline["responses"]
        if item["response_complete"] and item["status"] == "completed"
    ]
    resolved_slots = [
        item for item in slots
        if item["slot_disposition"] == "business" and item.get("google_place_id")
    ]

    def summarise(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for record in records:
            grouped[str(record["google_place_id"])].append(record)
        rows = [
            {
                "google_place_id": place_id,
                "business_name": items[0]["business_name"],
                "appearances": len(items),
                "best_position": min(int(item["position"]) for item in items),
                "average_position": sum(float(item["position"]) for item in items) / len(items),
                "providers": sorted({
                    PROVIDER_LABELS.get(str(item["provider"]).lower(), str(item["provider"]))
                    for item in items
                }),
            }
            for place_id, items in grouped.items()
        ]
        return sorted(
            rows,
            key=lambda item: (
                -int(item["appearances"]),
                float(item["average_position"]),
                str(item["business_name"]),
            ),
        )

    result = []
    for order in range(1, prompt_count + 1):
        responses = [
            item for item in complete_responses if int(item["base_prompt_order"]) == order
        ]
        question_slots = [
            item for item in resolved_slots if int(item["base_prompt_order"]) == order
        ]
        target_slots = [
            item for item in question_slots
            if str(item["google_place_id"]) == str(target_place_id)
        ]
        provider_results = []
        for provider in providers:
            provider_slots = [
                item for item in question_slots
                if PROVIDER_LABELS.get(str(item["provider"]).lower(), str(item["provider"])) == provider
            ]
            provider_responses = [
                item for item in responses
                if PROVIDER_LABELS.get(str(item["provider"]).lower(), str(item["provider"])) == provider
            ]
            provider_results.append({
                "provider": provider,
                "answer_count": len(provider_responses),
                "leaders": summarise(provider_slots)[:2],
            })
        result.append({
            "order": order,
            "prompt_category": responses[0]["prompt_category"],
            "prompt_text": responses[0]["prompt_text"],
            "answer_count": len(responses),
            "target_appearances": len(target_slots),
            "target_best_position": (
                min(int(item["position"]) for item in target_slots) if target_slots else None
            ),
            "leaders": summarise(question_slots)[:3],
            "provider_results": provider_results,
        })
    return result


def _build_report(
    *,
    config: Mapping[str, Any],
    run: Mapping[str, Any],
    baseline: Mapping[str, Any],
    slots: list[dict[str, Any]],
    market: list[dict[str, Any]],
    websites: list[dict[str, Any]],
    review_sets: list[dict[str, Any]],
) -> dict[str, Any]:
    decisions = config["analyst_decisions"]
    providers = [PROVIDER_LABELS.get(str(item).lower(), str(item)) for item in run["providers"]]
    business_slots = [item for item in slots if item["slot_disposition"] == "business"]
    non_business_slots = [item for item in slots if item["slot_disposition"] == "non_business"]
    target_id = config["target_google_place_id"]
    target_name = config["target_business_name"]
    target_slots = [item for item in business_slots if str(item.get("google_place_id")) == target_id]
    sorted_market = sorted(
        market, key=lambda item: (-int(item["recommendations"]), str(item["business_name"]))
    )
    target_market = _market_row(market, target_id)
    target_rank = next(
        index for index, item in enumerate(sorted_market, start=1)
        if str(item.get("google_place_id")) == target_id
    )
    cohort_rows = []
    for member in config["cohort"]:
        row = _market_row(market, member["google_place_id"])
        matching = [
            item for item in business_slots
            if str(item.get("google_place_id")) == member["google_place_id"]
        ]
        cohort_rows.append({
            **dict(member),
            "recommendations": int(row["recommendations"]),
            "business_sor_pct": float(row["share_of_recommendation"]) * 100,
            "provider_names": sorted({
                PROVIDER_LABELS.get(str(item["provider"]).lower(), str(item["provider"]))
                for item in matching
            }),
            "provider_breadth": len({item["provider"] for item in matching}),
            "intent_breadth": len({item["base_prompt_order"] for item in matching}),
            "selection_reason": member["selection_reason"],
        })
    comparison_businesses = [*config["cohort"], {
        "business_name": target_name, "google_place_id": target_id
    }]
    provider_rows = []
    for business in comparison_businesses:
        matching = [
            item for item in business_slots
            if str(item.get("google_place_id")) == business["google_place_id"]
        ]
        counts = defaultdict(int)
        for item in matching:
            counts[PROVIDER_LABELS.get(str(item["provider"]).lower(), str(item["provider"]))] += 1
        provider_rows.append({
            "business": business["business_name"],
            **{provider: counts[provider] for provider in providers},
            "provider_breadth": len([value for value in counts.values() if value]),
            "intent_breadth": len({item["base_prompt_order"] for item in matching}),
        })
    pages_by_id = {str(item["google_place_id"]): len(item["pages"]) for item in websites}
    reviews_by_id = {item["google_place_id"]: item["record_count"] for item in review_sets}
    priority_ids = decisions["priority_action_ids"]
    priority_actions = [
        action for action in decisions["actions"] if action["action_id"] in priority_ids
    ]
    complete_responses = [
        item for item in baseline["responses"]
        if item["response_complete"] and item["status"] == "completed"
    ]
    visibility_provider_rows = []
    for source_provider, display in zip(run["providers"], providers):
        matching = [item for item in complete_responses if item["provider"] == source_provider]
        visibility_provider_rows.append({
            "name": display,
            "complete": len(matching),
            "expected": int(run["prompt_count"]) * int(run["repeat_count"]),
            "recommendations": sum(
                bool(item["parser_reconciliation"].get("persisted_target_recommended"))
                for item in matching
            ),
        })
    question_performance = _question_performance(
        baseline=baseline,
        slots=slots,
        target_place_id=target_id,
        providers=providers,
        prompt_count=int(run["prompt_count"]),
    )
    return {
        "report_format": str(config.get("report_format") or "poc_audit_v1"),
        "introduction": dict(decisions.get("introduction") or {}),
        "review_quotes": list(decisions.get("review_quotes") or []),
        "question_performance": question_performance,
        "client_context": {"category": config["category"], "location": config["location"]},
        "executive_summary": decisions["executive_summary"],
        "visibility": {
            "responses_complete": len(complete_responses),
            "responses_expected": int(config["expected_responses"]),
            "mentions": sum(bool(item["parser_reconciliation"].get("persisted_target_mentioned")) for item in complete_responses),
            "recommendations": len(target_slots),
            "response_appearance_pct": len(target_slots) / len(complete_responses) * 100,
            "business_sor_pct": float(target_market["share_of_recommendation"]) * 100,
            "market_rank": target_rank if target_slots else None,
            "market_business_count": len(sorted_market),
            "average_position": (
                sum(float(item["position"]) for item in target_slots) / len(target_slots)
                if target_slots else None
            ),
            "best_position": (
                min(int(item["position"]) for item in target_slots)
                if target_slots else None
            ),
            "providers": visibility_provider_rows,
            "intents": [
                next(item["prompt_category"] for item in baseline["responses"] if item["base_prompt_order"] == order)
                for order in range(1, int(run["prompt_count"]) + 1)
            ],
            "verification_statement": config["verification_statement"],
        },
        "recommendation_market": {
            "original_slots": len(slots),
            "business_slots": len(business_slots),
            "excluded_slots": len(non_business_slots),
            "target_rank": target_rank,
            "business_count": len(sorted_market),
            "businesses": [{**item, "business_sor_pct": float(item["share_of_recommendation"]) * 100} for item in sorted_market],
            "market_note": config["market_note"],
        },
        "provider_comparison": provider_rows,
        "provider_observation": decisions["provider_observation"],
        "provider_caveat": config["provider_caveat"],
        "diagnostic_cohort": cohort_rows,
        "cohort_note": config["cohort_note"],
        "evidence_matrix": {
            "businesses": list(config["matrix_businesses"]),
            "business_place_ids": dict(config["matrix_business_place_ids"]),
            "dimensions": list(decisions["matrix_dimensions"]),
            "note": decisions["matrix_note"],
        },
        "strengths": decisions["strengths"],
        "strengths_note": decisions["strengths_note"],
        "priority_gaps": decisions["gaps"],
        "gap_caveat": config["gap_caveat"],
        "full_action_plan": decisions["actions"],
        "priority_action_ids": priority_ids,
        "priority_actions": priority_actions,
        "action_caveat": config["action_caveat"],
        "roadmap": decisions["roadmap"],
        "methodology": {
            "providers": providers,
            "models": dict(run["models"]),
            "prompt_count": int(run["prompt_count"]),
            "repetitions": int(run["repeat_count"]),
            "expected_responses": int(config["expected_responses"]),
            "complete_responses": len(complete_responses),
            "benchmark": "Model-memory recommendation visibility",
            "validation": list(config["methodology_validation"]),
            "evidence_inventory": [
                f"{len(slots)} eligible parsed slots; {len(business_slots)} named-business recommendations; {len(non_business_slots)} non-business slots excluded",
                f"Four completed website audits; {sum(len(item['pages']) for item in websites)} pages frozen",
                f"Exact review sets: {', '.join(f'{item['business_name']} {reviews_by_id[item['google_place_id']]}' for item in review_sets)}",
            ],
            "limitations": list(config["methodology_limitations"]),
            "non_causality": config["non_causality"],
        },
    }


def assemble_poc_audit_payload(
    config: Mapping[str, Any], *, engine: Engine | None = None
) -> dict[str, Any]:
    """Assemble a POC audit from persisted evidence plus explicit decisions."""
    database = engine or get_engine()
    with database.connect() as connection:
        transaction = connection.begin()
        try:
            connection.exec_driver_sql("set transaction read only")
            runs = _rows(connection, "select * from ai_visibility_runs where id = :id", {"id": config["run_id"]})
            if len(runs) != 1:
                raise ValueError(f"Expected one baseline run; found {len(runs)}")
            run = runs[0]
            queries = _rows(connection, "select * from ai_visibility_queries where run_id = :id order by base_prompt_order, repeat_index, prompt_order", {"id": config["run_id"]})
            results = _rows(connection, """
                select r.*, q.prompt_order, q.base_prompt_order, q.repeat_index,
                       q.prompt_category, q.prompt_source, q.prompt_text
                from ai_visibility_results r join ai_visibility_queries q on q.id = r.query_id
                where r.run_id = :id
                order by q.base_prompt_order, q.repeat_index, r.provider
            """, {"id": config["run_id"]})
            businesses = pd.DataFrame(_rows(connection, "select google_place_id, business_name, primary_group, business_format from business_features"))
            aliases = pd.DataFrame(_rows(connection, "select alias_name, google_place_id, canonical_business_name, alias_type, source_note, source_url from business_entity_aliases"))
            websites = _freeze_websites(connection, list(config["website_audits"]))
            review_sets = _freeze_reviews(connection, list(config["review_sets"]))
        finally:
            transaction.rollback()
    if len(queries) != int(run["prompt_count"]) * int(run["repeat_count"]):
        raise ValueError("Frozen query count does not match the run methodology")
    if len(results) != int(config["expected_responses"]):
        raise ValueError("Frozen response count does not match expected responses")
    baseline = _freeze_responses(results, config=config)
    slots, market = _recommendation_evidence(
        pd.DataFrame(results), businesses, aliases, config=config
    )
    if len(slots) != int(config["expected_eligible_slots"]):
        raise ValueError(f"Expected {config['expected_eligible_slots']} eligible slots; found {len(slots)}")
    review_diagnostic = _review_diagnostic(
        review_sets,
        target_place_id=config["target_google_place_id"],
        profile_key=config["review_profile"],
    )
    report = _build_report(
        config=config, run=run, baseline=baseline, slots=slots,
        market=market, websites=websites, review_sets=review_sets,
    )
    decisions = config["analyst_decisions"]
    registry = dict(config["evidence_registry"])
    payload = build_poc_audit_payload(
        audit={
            "baseline_run_id": config["run_id"],
            "target_google_place_id": config["target_google_place_id"],
            "target_business_name": config["target_business_name"],
            "audit_date": run["started_at"].date().isoformat(),
        },
        revision=dict(config.get("revision", {
            "snapshot_revision": 1,
            "supersedes_snapshot_id": None,
            "revision_reason": "Original POC audit",
        })),
        methodology={"providers": run["providers"], "models": run["models"], "prompt_count": run["prompt_count"], "repetitions": run["repeat_count"], "queries": queries},
        baseline_validation=baseline,
        source_traceability={
            "ai_run_id": config["run_id"],
            "query_ids": [str(item["id"]) for item in queries],
            "response_ids": [str(item["id"]) for item in results],
            "website_audit_run_ids": [str(item["id"]) for item in websites],
            "review_import_batch_ids": sorted({str(record["import_batch_id"]) for item in review_sets for record in item["records"]}),
        },
        recommendation_market={"original_slot_count": len(slots), "business_slot_count": sum(item["slot_disposition"] == "business" for item in slots), "non_business_slot_count": sum(item["slot_disposition"] == "non_business" for item in slots), "slot_evidence": slots, "canonical_businesses": market},
        website_evidence={"audits": websites},
        review_evidence={"review_sets": review_sets, "derived_review_benchmark": review_diagnostic},
        diagnostic={"cohort": list(config["cohort"]), "analyst_decisions": decisions, "provider_hypotheses": decisions["provider_hypotheses"], "evidence_registry": registry},
        report=report,
    )
    return payload
