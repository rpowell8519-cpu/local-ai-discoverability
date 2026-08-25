from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.ai_recommendation_intelligence import (
    build_business_share_table,
    build_recommendation_records,
    extract_numbered_recommendations,
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


RUN_ID = "631f46d0-8361-47b0-aa8c-6e544de0eca3"
TARGET_PLACE_ID = "ChIJP6-pRwqFdUgRZotaM4dbr7w"

COHORT = (
    {
        "google_place_id": "ChIJOR25DHWFdUgRDYAPbn_RN7Y",
        "business_name": "Cuttlefish Eco Salons - Brighton",
        "website_audit_run_id": "2959d4fd-8b77-4b2f-8ae0-e33b482c2f41",
    },
    {
        "google_place_id": "ChIJ0xRwsguFdUgRGxt2HHbtI7k",
        "business_name": "Trevor Sorbie Brighton",
        "website_audit_run_id": "4224590b-7914-4bab-9ab3-e1041201ce93",
    },
    {
        "google_place_id": "ChIJ6TgKMnWFdUgRbt_lTxyb6lg",
        "business_name": "Simon Webster Hair",
        "website_audit_run_id": "07f9d61a-4e4f-48ba-b989-58d1dabbc681",
    },
)

TARGET_WEBSITE_AUDIT_RUN_ID = "76b2362e-3c42-44f7-a843-30b5d6e6ec4a"
ANALYST_DECISION_VERSION = "ciscos_karma_stage3_approved_v1"


# These are the approved Stage 3 interpretations. They are deliberately
# separate from measured evidence and remain visible in the canonical
# payload with evidence references and a version identifier.
APPROVED_ANALYST_DECISIONS: dict[str, Any] = {
    "version": ANALYST_DECISION_VERSION,
    "status": "operator_approved",
    "provenance": (
        "Cisco's Karma Stages 2B and 3 operator approvals; report "
        "specification refinements approved before renderer implementation."
    ),
    "strengths": [
        {
            "strength_id": "strength_service_evidence",
            "title": "Relevant service evidence",
            "body": (
                "Hair extensions and children's haircuts are already "
                "represented on the website."
            ),
            "evidence_refs": [
                "website:target:pages",
                "diagnostic:proposition_coverage",
            ],
        },
        {
            "strength_id": "strength_site_presence",
            "title": "Credible site presence",
            "body": (
                "The adaptive audit completed successfully across a "
                "crawlable 10-page footprint."
            ),
            "evidence_refs": ["website:target:audit"],
        },
        {
            "strength_id": "strength_review_sentiment",
            "title": "Positive customer sentiment",
            "body": (
                "The exact 63-review diagnostic set provides positive "
                "customer evidence rather than an absence of proof."
            ),
            "evidence_refs": ["reviews:target:set", "reviews:target:themes"],
        },
        {
            "strength_id": "strength_local_human",
            "title": "Local and human proposition",
            "body": (
                "The existing public information provides a foundation "
                "for clearer Brighton, expertise and customer-experience evidence."
            ),
            "evidence_refs": ["website:target:pages", "reviews:target:themes"],
        },
    ],
    "gaps": [
        {
            "gap_id": "gap_entity_schema",
            "title": "Entity and structured-data clarity",
            "observed": "No LocalBusiness or HairSalon schema was detected.",
            "comparison": (
                "The AI-visible cohort provides useful entity-clarity comparisons."
            ),
            "relevance": (
                "Clear, consistent and corroborated public information makes "
                "it easier for digital systems to understand and associate a "
                "business with its location, services and areas of expertise."
            ),
            "confidence": "High",
            "evidence_refs": ["website:target:audit", "diagnostic:entity_matrix"],
        },
        {
            "gap_id": "gap_service_depth",
            "title": "Service and expertise depth",
            "observed": (
                "Extensions and children's evidence exists but can be reinforced."
            ),
            "comparison": (
                "The visible leaders provide broader comparison evidence."
            ),
            "relevance": (
                "Deeper first-party evidence can explain services and expertise "
                "more clearly."
            ),
            "confidence": "Moderate",
            "evidence_refs": ["diagnostic:proposition_coverage"],
        },
        {
            "gap_id": "gap_review_scale",
            "title": "Review scale and recency",
            "observed": "63 reviews formed the exact analysed set.",
            "comparison": (
                "Cuttlefish and Trevor Sorbie each contributed 100 analysed reviews."
            ),
            "relevance": (
                "A larger, current corpus can strengthen independent customer "
                "corroboration."
            ),
            "confidence": "High",
            "evidence_refs": [
                "reviews:target:set",
                "reviews:cuttlefish:set",
                "reviews:trevor:set",
            ],
        },
        {
            "gap_id": "gap_authority",
            "title": "Authority and corroboration",
            "observed": (
                "Existing strengths are not always reinforced across evidence types."
            ),
            "comparison": (
                "The leader set supplies different authority and entity comparisons."
            ),
            "relevance": (
                "Consistent corroboration can improve public understanding of expertise."
            ),
            "confidence": "Moderate",
            "evidence_refs": ["diagnostic:entity_matrix", "diagnostic:review_benchmark"],
        },
    ],
    "provider_hypotheses": [
        {
            "business_name": "Cuttlefish Eco Salons - Brighton",
            "hypothesis": (
                "Its OpenAI and Gemini prominence coincides with broad intent "
                "coverage and a distinctive, consistently presented local proposition."
            ),
            "evidence_refs": ["market:cuttlefish", "website:cuttlefish:audit"],
        },
        {
            "business_name": "Trevor Sorbie Brighton",
            "hypothesis": (
                "Its cross-provider breadth coincides with an established brand "
                "entity and a comparatively deep public content footprint."
            ),
            "evidence_refs": ["market:trevor", "website:trevor:audit"],
        },
        {
            "business_name": "Simon Webster Hair",
            "hypothesis": (
                "Its Gemini-only concentration is an observed provider pattern; "
                "the audit does not infer an undocumented provider mechanism."
            ),
            "evidence_refs": ["market:simon", "website:simon:audit"],
        },
    ],
    "actions": [
        {
            "action_id": "action_entity_consistency",
            "title": "Reinforce canonical business identity",
            "category": "Entity and identity",
            "steps": (
                "Verify and align the official name, address, telephone, Brighton "
                "location and profile references across controlled properties."
            ),
            "intended_improvement": (
                "More consistent public identity evidence across first-party and "
                "business-profile sources."
            ),
            "timing": "Weeks 1-2",
            "evidence_refs": ["diagnostic:entity_matrix"],
        },
        {
            "action_id": "action_structured_data",
            "title": "Implement accurate HairSalon structured data",
            "category": "Structured data",
            "steps": (
                "Add and validate appropriate HairSalon/LocalBusiness structured "
                "data with location, contact and official-profile references."
            ),
            "intended_improvement": (
                "A clearer machine-readable representation of the business, "
                "location and official profiles."
            ),
            "timing": "Weeks 1-2",
            "evidence_refs": ["website:target:audit", "gap:gap_entity_schema"],
        },
        {
            "action_id": "action_service_evidence",
            "title": "Develop stronger priority-service evidence hubs",
            "category": "Content and propositions",
            "steps": (
                "Deepen service, consultation, expertise, FAQ and proof content; "
                "improve internal linking and Brighton relevance."
            ),
            "intended_improvement": (
                "Clearer, connected first-party evidence for priority services "
                "and areas of expertise."
            ),
            "timing": "Weeks 2-5",
            "evidence_refs": ["diagnostic:proposition_coverage", "gap:gap_service_depth"],
        },
        {
            "action_id": "action_review_programme",
            "title": "Build stronger and more current customer corroboration",
            "category": "Reviews and profile evidence",
            "steps": (
                "Introduce a compliant review-request process; monitor cadence, "
                "responses and honest service-specific evidence."
            ),
            "intended_improvement": (
                "A larger and more current body of independent evidence about "
                "service quality and customer experience."
            ),
            "timing": "Weeks 1-8",
            "evidence_refs": ["reviews:target:set", "gap:gap_review_scale"],
        },
        {
            "action_id": "action_authority_evidence",
            "title": "Strengthen expertise and authority evidence",
            "category": "Authority and trust",
            "steps": (
                "Reinforce stylist expertise, consultations, recognised credentials "
                "and appropriate third-party corroboration where available."
            ),
            "intended_improvement": (
                "More complete public evidence of expertise, trust and distinctive value."
            ),
            "timing": "Weeks 3-8",
            "evidence_refs": ["gap:gap_authority", "reviews:target:themes"],
        },
    ],
    "priority_action_ids": [
        "action_structured_data",
        "action_service_evidence",
        "action_review_programme",
    ],
}


NON_BUSINESS_PREFIXES = (
    "checking ",
    "looking ",
    "asking ",
    "searching ",
    "calling ",
    "check ",
    "ask ",
    "word of mouth",
    "google maps",
    "treatwell",
    "local facebook",
    "instagram",
)


APPROVED_ALIAS_FAMILIES = {
    "cuttlefish": {
        "business_name": "Cuttlefish Eco Salons - Brighton",
        "google_place_id": "ChIJOR25DHWFdUgRDYAPbn_RN7Y",
    },
    "paint": {"business_name": "Paint salon family", "google_place_id": None},
    "cinch": {"business_name": "Cinch Hair", "google_place_id": None},
    "hair lounge": {"business_name": "The Hair Lounge", "google_place_id": None},
    "kinki": {"business_name": "Kinki Hair", "google_place_id": None},
    "parlour": {"business_name": "The Parlour", "google_place_id": None},
    "sassoon": {"business_name": "Sassoon Salon Brighton", "google_place_id": None},
}


def _rows(connection, statement: str, parameters: Mapping[str, Any] | None = None):
    return [
        dict(row)
        for row in connection.execute(
            text(statement), dict(parameters or {})
        ).mappings().all()
    ]


def _approved_family(raw_name: str) -> dict[str, Any] | None:
    normalized = normalise_name(raw_name)
    if normalized.startswith("cuttlefish"):
        return APPROVED_ALIAS_FAMILIES["cuttlefish"]
    if any(term in normalized for term in ("paint pot", "paint shop", "paint box", "paintbox", "paintworks")):
        return APPROVED_ALIAS_FAMILIES["paint"]
    for key in ("cinch", "hair lounge", "kinki", "parlour", "sassoon"):
        if key in normalized:
            return APPROVED_ALIAS_FAMILIES[key]
    return None


def _freeze_responses(results: list[dict[str, Any]]) -> dict[str, Any]:
    explicit_terms = (
        "cisco's karma", "cisco’s karma", "ciscos karma", "cisco karma"
    )
    indirect_terms = (
        "5 bartholomews", "east street arcade", "alex martinez",
        "lydia", "keeley", "adam lawton",
    )
    frozen = []
    for result in results:
        raw = str(result.get("raw_response") or "")
        lowered = raw.lower()
        explicit = [
            {"term": term, "credible": True}
            for term in explicit_terms if term in lowered
        ]
        indirect = [
            {
                "term": term,
                "credible": False,
                "assessment": "Inspected during Stage 3A; not a credible target identification.",
            }
            for term in indirect_terms if term in lowered
        ]
        frozen.append(
            freeze_ai_response(
                result,
                explicit_matches=explicit,
                indirect_matches=indirect,
                parser_reconciliation={
                    "target_correct": True,
                    "persisted_target_mentioned": bool(result.get("target_mentioned")),
                    "persisted_target_recommended": bool(result.get("target_recommended")),
                },
                verification_notes=(
                    "Complete raw response independently inspected in Stage 3A."
                ),
            )
        )
    return build_baseline_validation(
        frozen,
        expected_responses=72,
        status="verified_zero",
        verification_method_version="independent_raw_response_audit_v1",
    )


def _recommendation_evidence(
    results_frame: pd.DataFrame,
    businesses: pd.DataFrame,
    aliases: pd.DataFrame,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    resolved = build_recommendation_records(
        results=results_frame,
        businesses=businesses,
        aliases=aliases,
        target_google_place_id=TARGET_PLACE_ID,
        commercial_competitor_ids=set(),
        primary_group="hair_services",
    )
    slots: list[dict[str, Any]] = []
    business_rows = []
    for row in resolved.to_dict("records"):
        normalized = normalise_name(row["raw_business_name"])
        non_business = normalized.startswith(NON_BUSINESS_PREFIXES)
        family = _approved_family(row["raw_business_name"])
        item = dict(row)
        item["source_raw_business_name"] = item["raw_business_name"]
        item["slot_disposition"] = "non_business" if non_business else "business"
        item["resolution_method"] = row.get("resolution_status")
        if not non_business and family:
            item["business_name"] = family["business_name"]
            item["google_place_id"] = family["google_place_id"]
            item["resolution_method"] = "approved_stage2b_alias_family"
            # The existing market builder groups unresolved entities by raw
            # name. Use the approved canonical family label as that grouping
            # key while retaining the original parsed text above.
            if not family["google_place_id"]:
                item["raw_business_name"] = family["business_name"]
        slots.append(item)
        if not non_business:
            business_rows.append(item)

    business_frame = pd.DataFrame(business_rows)
    market = build_business_share_table(business_frame).to_dict("records")
    return slots, market


def _freeze_websites(connection) -> list[dict[str, Any]]:
    definitions = (
        {
            "google_place_id": TARGET_PLACE_ID,
            "business_name": "Cisco's Karma",
            "website_audit_run_id": TARGET_WEBSITE_AUDIT_RUN_ID,
        },
        *COHORT,
    )
    audits = []
    for definition in definitions:
        run_rows = _rows(
            connection,
            "select * from website_audit_runs where id = :run_id",
            {"run_id": definition["website_audit_run_id"]},
        )
        if len(run_rows) != 1:
            raise ValueError(f"Missing website audit {definition['website_audit_run_id']}")
        pages = _rows(
            connection,
            """
            select * from website_audit_pages
            where audit_run_id = :run_id
            order by crawled_at, id
            """,
            {"run_id": definition["website_audit_run_id"]},
        )
        audits.append({**run_rows[0], **definition, "pages": pages})
    return audits


def _freeze_reviews(connection) -> list[dict[str, Any]]:
    definitions = (
        (TARGET_PLACE_ID, "Cisco's Karma", 63, "complete"),
        (COHORT[0]["google_place_id"], COHORT[0]["business_name"], 100, "complete"),
        (COHORT[1]["google_place_id"], COHORT[1]["business_name"], 100, "complete"),
    )
    review_sets = []
    for place_id, name, limit, status in definitions:
        records = _rows(
            connection,
            """
            select id, review_id, google_place_id, business_name,
                   review_text, review_rating, review_timestamp,
                   review_datetime_utc, review_link, source,
                   source_file_name, import_batch_id, imported_at,
                   updated_at, owner_answer
            from business_reviews
            where google_place_id = :place_id
            order by review_datetime_utc desc nulls last,
                     imported_at desc, id desc
            limit :record_limit
            """,
            {"place_id": place_id, "record_limit": limit},
        )
        if len(records) != limit:
            raise ValueError(f"Expected {limit} reviews for {name}; found {len(records)}")
        review_sets.append(
            freeze_review_set(
                google_place_id=place_id,
                business_name=name,
                records=records,
                status=status,
            )
        )
    review_sets.append(
        freeze_review_set(
            google_place_id=COHORT[2]["google_place_id"],
            business_name=COHORT[2]["business_name"],
            records=[],
            status="exception",
            exception={
                "exception_code": "approved_profile_returned_no_review_result",
                "description": (
                    "The approved Simon Webster Google Place ID returned no "
                    "review result through the approved collection mechanism."
                ),
                "comparison_treatment": (
                    "Review evidence unavailable; excluded from review comparisons "
                    "and not treated as zero reviews."
                ),
                "approved_stage": "Stage 3",
            },
        )
    )
    return review_sets


def _review_diagnostic(review_sets: list[dict[str, Any]]) -> dict[str, Any]:
    records = [
        record
        for review_set in review_sets if review_set["status"] == "complete"
        for record in review_set["records"]
    ]
    frame = pd.DataFrame(records)
    frame["owner_answer"] = frame["owner_response_present"].map(
        lambda present: "present" if bool(present) else ""
    )
    business_names = {
        review_set["google_place_id"]: review_set["business_name"]
        for review_set in review_sets
    }
    benchmark = build_review_benchmark(
        target_google_place_id=TARGET_PLACE_ID,
        reviews=frame,
        business_names=business_names,
        profile=get_review_profile("hair_services"),
    )
    return {
        key: value.to_dict("records")
        for key, value in benchmark.items()
    }


def _market_row(market: list[dict[str, Any]], place_id: str) -> dict[str, Any]:
    matches = [row for row in market if str(row.get("google_place_id")) == place_id]
    if len(matches) != 1:
        raise ValueError(f"Canonical market has {len(matches)} rows for {place_id}")
    return matches[0]


def _build_report(
    *,
    run: dict[str, Any],
    baseline: dict[str, Any],
    slots: list[dict[str, Any]],
    market: list[dict[str, Any]],
    websites: list[dict[str, Any]],
    review_sets: list[dict[str, Any]],
    review_diagnostic: dict[str, Any],
) -> dict[str, Any]:
    cohort_rows = []
    for member in COHORT:
        row = _market_row(market, member["google_place_id"])
        providers = sorted(
            {
                {"openai": "OpenAI", "anthropic": "Claude", "claude": "Claude", "gemini": "Gemini"}.get(
                    str(slot["provider"]).lower(), str(slot["provider"])
                ) for slot in slots
                if slot["slot_disposition"] == "business"
                and str(slot.get("google_place_id")) == member["google_place_id"]
            }
        )
        intents = {
            int(slot["base_prompt_order"]) for slot in slots
            if slot["slot_disposition"] == "business"
            and str(slot.get("google_place_id")) == member["google_place_id"]
        }
        cohort_rows.append(
            {
                **member,
                "recommendations": int(row["recommendations"]),
                "business_sor_pct": float(row["share_of_recommendation"]) * 100,
                "provider_names": providers,
                "provider_breadth": len(providers),
                "intent_breadth": len(intents),
                "selection_reason": next(
                    item["hypothesis"]
                    for item in APPROVED_ANALYST_DECISIONS["provider_hypotheses"]
                    if item["business_name"] == member["business_name"]
                ),
            }
        )

    provider_labels = {
        "openai": "OpenAI",
        "anthropic": "Claude",
        "claude": "Claude",
        "gemini": "Gemini",
    }
    configured_providers = [str(item) for item in run["providers"]]
    display_providers = [
        provider_labels.get(item.lower(), item) for item in configured_providers
    ]
    provider_rows = []
    for business_name, place_id in [
        *[(item["business_name"], item["google_place_id"]) for item in COHORT],
        ("Cisco's Karma", TARGET_PLACE_ID),
    ]:
        matching = [
            slot for slot in slots
            if slot["slot_disposition"] == "business"
            and str(slot.get("google_place_id")) == place_id
        ]
        counts = defaultdict(int)
        for item in matching:
            label = provider_labels.get(
                str(item["provider"]).lower(), str(item["provider"])
            )
            counts[label] += 1
        provider_rows.append(
            {
                "business": business_name,
                **{label: counts[label] for label in display_providers},
                "provider_breadth": len([value for value in counts.values() if value]),
                "intent_breadth": len({item["base_prompt_order"] for item in matching}),
            }
        )

    pages_by_id = {
        str(audit["google_place_id"]): len(audit["pages"])
        for audit in websites
    }
    reviews_by_id = {
        item["google_place_id"]: item["record_count"]
        for item in review_sets
    }
    full_actions = APPROVED_ANALYST_DECISIONS["actions"]
    priority_ids = APPROVED_ANALYST_DECISIONS["priority_action_ids"]
    priority_actions = [
        action for action in full_actions if action["action_id"] in priority_ids
    ]
    business_slots = [item for item in slots if item["slot_disposition"] == "business"]
    non_business_slots = [item for item in slots if item["slot_disposition"] == "non_business"]

    return {
        "client_context": {
            "category": run.get("target_category_label") or "Hair services",
            "location": run.get("location_context") or "Brighton",
        },
        "executive_summary": {
            "headline": (
                "The target did not appear in this frozen AI recommendation benchmark."
            ),
            "summary": (
                "The result was independently verified across every complete "
                "response, provider and tested consumer intent."
            ),
            "strengths": APPROVED_ANALYST_DECISIONS["strengths"][:3],
            "action_statement": (
                "Clarify the business entity, deepen service and expertise "
                "evidence, and build stronger customer corroboration."
            ),
            "non_causality": (
                "These are evidence-backed opportunities, not proven AI ranking "
                "factors or guaranteed visibility interventions."
            ),
        },
        "visibility": {
            "responses_complete": baseline["complete_raw_responses"],
            "responses_expected": baseline["expected_responses"],
            "mentions": sum(
                bool(item["parser_reconciliation"].get("persisted_target_mentioned"))
                for item in baseline["responses"]
            ),
            "recommendations": sum(
                bool(item["parser_reconciliation"].get("persisted_target_recommended"))
                for item in baseline["responses"]
            ),
            "business_sor_pct": 0.0,
            "providers": [
                {
                    "name": provider_labels.get(provider.lower(), provider),
                    "complete": sum(
                        item["provider"] == provider and item["response_complete"]
                        for item in baseline["responses"]
                    ),
                    "expected": int(run["prompt_count"]) * int(run["repeat_count"]),
                    "recommendations": sum(
                        item["provider"] == provider
                        and bool(item["parser_reconciliation"].get("persisted_target_recommended"))
                        for item in baseline["responses"]
                    ),
                }
                for provider in configured_providers
            ],
            "intents": [
                next(
                    item["prompt_category"] for item in baseline["responses"]
                    if item["base_prompt_order"] == order
                )
                for order in range(1, 9)
            ],
            "verification_statement": (
                "All original response texts were inspected. No explicit or "
                "credible indirect target reference, parser miss or identity-"
                "resolution error was found."
            ),
        },
        "recommendation_market": {
            "original_slots": len(slots),
            "business_slots": len(business_slots),
            "excluded_slots": len(non_business_slots),
            "businesses": [
                {
                    **item,
                    "business_sor_pct": float(item["share_of_recommendation"]) * 100,
                }
                for item in sorted(
                    market,
                    key=lambda item: (-int(item["recommendations"]), item["business_name"]),
                )
            ],
            "market_note": (
                "Business Share of Recommendation uses valid business slots. "
                "Generic advice and discovery platforms remain frozen response "
                "evidence but are excluded from business metrics."
            ),
        },
        "provider_comparison": provider_rows,
        "provider_observation": (
            "The approved leaders exhibit materially different provider patterns."
        ),
        "provider_caveat": (
            "These are measured provider patterns. The audit does not claim "
            "knowledge of undocumented provider ranking or retrieval systems."
        ),
        "diagnostic_cohort": cohort_rows,
        "cohort_note": (
            "The cohort is an operator-approved evidence comparison group. It "
            "does not curate or replace the complete measured market."
        ),
        "evidence_matrix": {
            "businesses": ["Cisco's Karma", "Cuttlefish", "Trevor Sorbie", "Simon Webster"],
            "business_place_ids": {
                "Cisco's Karma": TARGET_PLACE_ID,
                "Cuttlefish": COHORT[0]["google_place_id"],
                "Trevor Sorbie": COHORT[1]["google_place_id"],
                "Simon Webster": COHORT[2]["google_place_id"],
            },
            "dimensions": [
                {"label": "AI visibility", "evidence_refs": ["market:cuttlefish", "market:trevor", "market:simon"], "values": {
                    "Cisco's Karma": "0.00% SOR",
                    "Cuttlefish": f"{cohort_rows[0]['business_sor_pct']:.2f}% SOR",
                    "Trevor Sorbie": f"{cohort_rows[1]['business_sor_pct']:.2f}% SOR",
                    "Simon Webster": f"{cohort_rows[2]['business_sor_pct']:.2f}% SOR",
                }},
                {"label": "Provider breadth", "evidence_refs": ["market:cuttlefish", "market:trevor", "market:simon"], "values": {
                    "Cisco's Karma": "0 / 3",
                    "Cuttlefish": f"{cohort_rows[0]['provider_breadth']} / 3",
                    "Trevor Sorbie": f"{cohort_rows[1]['provider_breadth']} / 3",
                    "Simon Webster": f"{cohort_rows[2]['provider_breadth']} / 3",
                }},
                {"label": "Tested intent breadth", "evidence_refs": ["market:cuttlefish", "market:trevor", "market:simon"], "values": {
                    "Cisco's Karma": "0 / 8",
                    "Cuttlefish": f"{cohort_rows[0]['intent_breadth']} / 8",
                    "Trevor Sorbie": f"{cohort_rows[1]['intent_breadth']} / 8",
                    "Simon Webster": f"{cohort_rows[2]['intent_breadth']} / 8",
                }},
                {"label": "Audited site footprint", "evidence_refs": ["website:target:audit", "website:cuttlefish:audit", "website:trevor:audit", "website:simon:audit"], "values": {
                    "Cisco's Karma": f"{pages_by_id[TARGET_PLACE_ID]} pages",
                    "Cuttlefish": f"{pages_by_id[COHORT[0]['google_place_id']]} pages",
                    "Trevor Sorbie": f"{pages_by_id[COHORT[1]['google_place_id']]} pages",
                    "Simon Webster": f"{pages_by_id[COHORT[2]['google_place_id']]} pages",
                }},
                {"label": "Structured business data", "evidence_refs": ["website:target:audit", "diagnostic:entity_matrix"], "values": {
                    "Cisco's Karma": "Local/business schema not detected",
                    "Cuttlefish": "See frozen website audit",
                    "Trevor Sorbie": "See frozen website audit",
                    "Simon Webster": "See frozen website audit",
                }},
                {"label": "Priority services", "evidence_refs": ["diagnostic:proposition_coverage"], "values": {
                    "Cisco's Karma": "Extensions + children's evidence present",
                    "Cuttlefish": "See proposition evidence",
                    "Trevor Sorbie": "See proposition evidence",
                    "Simon Webster": "See proposition evidence",
                }},
                {"label": "Review evidence analysed", "evidence_refs": ["reviews:target:set", "reviews:cuttlefish:set", "reviews:trevor:set"], "values": {
                    "Cisco's Karma": f"{reviews_by_id[TARGET_PLACE_ID]} reviews | positive overall",
                    "Cuttlefish": f"{reviews_by_id[COHORT[0]['google_place_id']]} reviews",
                    "Trevor Sorbie": f"{reviews_by_id[COHORT[1]['google_place_id']]} reviews",
                    "Simon Webster": "Evidence unavailable",
                }},
            ],
            "note": review_sets[3]["exception"]["comparison_treatment"],
        },
        "strengths": APPROVED_ANALYST_DECISIONS["strengths"],
        "strengths_note": (
            "The opportunity is to clarify and reinforce existing strengths, "
            "not to replace the business's proposition."
        ),
        "priority_gaps": APPROVED_ANALYST_DECISIONS["gaps"],
        "gap_caveat": (
            "Observed differences are evidence-backed opportunities. They are "
            "not proven causes of the measured AI recommendation result."
        ),
        "full_action_plan": full_actions,
        "priority_action_ids": priority_ids,
        "priority_actions": priority_actions,
        "action_caveat": (
            "The intended outcomes concern the underlying business, entity, "
            "content and customer evidence. No AI visibility improvement is guaranteed."
        ),
        "roadmap": {
            "phases": [
                {"timing": "Weeks 1-2", "title": "Entity foundations", "body": "Confirm identity data and implement structured data."},
                {"timing": "Weeks 2-5", "title": "Content and propositions", "body": "Deepen priority service, consultation and expertise content."},
                {"timing": "Weeks 1-8", "title": "Review programme", "body": "Establish a compliant request workflow and monitor evidence."},
                {"timing": "Weeks 8-12", "title": "Remeasure", "body": "Run a comparable frozen benchmark and disclose model changes."},
            ],
            "options": [
                {"title": "Implement internally", "body": "Use the prioritised plan and evidence references."},
                {"title": "Supported implementation", "body": "Deliver technical, content and profile work collaboratively."},
                {"title": "Implementation + remeasurement", "body": "Complete delivery, verification and follow-up audit."},
            ],
            "remeasurement_note": "Suggested follow-up: 8-12 weeks after meaningful implementation.",
        },
        "methodology": {
            "providers": list(run["providers"]),
            "models": dict(run["models"]),
            "prompt_count": int(run["prompt_count"]),
            "repetitions": int(run["repeat_count"]),
            "expected_responses": 72,
            "complete_responses": baseline["complete_raw_responses"],
            "benchmark": "Model-memory recommendation visibility",
            "validation": [
                "24/24 complete responses per provider",
                "Every intent represented by all three providers",
                "72/72 raw response texts independently inspected",
                "0 explicit or credible indirect target occurrences",
                "0 target parser or canonicalisation errors",
            ],
            "evidence_inventory": [
                f"{len(slots)} parsed slots; {len(business_slots)} valid business slots; {len(non_business_slots)} non-business slots excluded",
                f"Four completed website audits; {sum(len(item['pages']) for item in websites)} pages frozen",
                "Exact review sets: target 63, Cuttlefish 100, Trevor Sorbie 100",
                "Simon Webster review evidence unavailable under a documented exception",
            ],
            "limitations": [
                "This is a model-memory benchmark, not a live web-search test.",
                "Results depend on prompts, provider models and the audit date.",
                "AI outputs may vary between repetitions and over time.",
                "Website and review differences are observational, not causal.",
                "The diagnostic cohort is an analyst-selected comparison subset.",
                "Business SOR is benchmark-specific and is not commercial market share.",
                "Simon Webster is excluded from review comparisons because collection returned no result.",
            ],
            "non_causality": (
                "No observed website, entity or review difference is presented "
                "as a proven AI ranking factor or guaranteed cause of visibility."
            ),
        },
    }


def assemble_ciscos_karma_payload(*, engine: Engine | None = None) -> dict[str, Any]:
    """Reconstruct the approved Cisco audit using read-only persisted evidence."""

    database = engine or get_engine()
    with database.connect() as connection:
        transaction = connection.begin()
        try:
            connection.exec_driver_sql("set transaction read only")
            runs = _rows(connection, "select * from ai_visibility_runs where id = :id", {"id": RUN_ID})
            if len(runs) != 1:
                raise ValueError(f"Expected one baseline run; found {len(runs)}")
            run = runs[0]
            queries = _rows(
                connection,
                "select * from ai_visibility_queries where run_id = :id order by base_prompt_order, repeat_index, prompt_order",
                {"id": RUN_ID},
            )
            results = _rows(
                connection,
                """
                select r.*, q.prompt_order, q.base_prompt_order, q.repeat_index,
                       q.prompt_category, q.prompt_source, q.prompt_text
                from ai_visibility_results r
                join ai_visibility_queries q on q.id = r.query_id
                where r.run_id = :id
                order by q.base_prompt_order, q.repeat_index, r.provider
                """,
                {"id": RUN_ID},
            )
            businesses = pd.DataFrame(_rows(
                connection,
                "select google_place_id, business_name, primary_group, business_format from business_features",
            ))
            aliases = pd.DataFrame(_rows(
                connection,
                "select alias_name, google_place_id, canonical_business_name, alias_type, source_note, source_url from business_entity_aliases",
            ))
            websites = _freeze_websites(connection)
            review_sets = _freeze_reviews(connection)
        finally:
            transaction.rollback()

    if len(queries) != 24 or len(results) != 72:
        raise ValueError(f"Expected 24 queries and 72 results; found {len(queries)} and {len(results)}")

    baseline = _freeze_responses(results)
    slots, market = _recommendation_evidence(
        pd.DataFrame(results), businesses, aliases
    )
    review_diagnostic = _review_diagnostic(review_sets)
    report = _build_report(
        run=run,
        baseline=baseline,
        slots=slots,
        market=market,
        websites=websites,
        review_sets=review_sets,
        review_diagnostic=review_diagnostic,
    )
    payload = build_poc_audit_payload(
        audit={
            "baseline_run_id": RUN_ID,
            "target_google_place_id": TARGET_PLACE_ID,
            "target_business_name": run["target_business_name"],
            "audit_date": run["started_at"].date().isoformat(),
        },
        revision={
            "snapshot_revision": 1,
            "supersedes_snapshot_id": None,
            "revision_reason": "Original POC audit",
        },
        methodology={
            "providers": run["providers"],
            "models": run["models"],
            "prompt_count": run["prompt_count"],
            "repetitions": run["repeat_count"],
            "queries": queries,
        },
        baseline_validation=baseline,
        source_traceability={
            "ai_run_id": RUN_ID,
            "query_ids": [str(item["id"]) for item in queries],
            "response_ids": [str(item["id"]) for item in results],
            "website_audit_run_ids": [str(item["id"]) for item in websites],
            "review_import_batch_ids": sorted({
                str(record["import_batch_id"])
                for review_set in review_sets
                for record in review_set["records"]
                if record.get("import_batch_id")
            }),
        },
        recommendation_market={
            "original_slot_count": len(slots),
            "business_slot_count": sum(item["slot_disposition"] == "business" for item in slots),
            "non_business_slot_count": sum(item["slot_disposition"] == "non_business" for item in slots),
            "slot_evidence": slots,
            "canonical_businesses": market,
        },
        website_evidence={"audits": websites},
        review_evidence={
            "review_sets": review_sets,
            "derived_review_benchmark": review_diagnostic,
        },
        diagnostic={
            "cohort": list(COHORT),
            "analyst_decisions": APPROVED_ANALYST_DECISIONS,
            "provider_hypotheses": APPROVED_ANALYST_DECISIONS["provider_hypotheses"],
            "evidence_registry": {
                "website:target:audit": {"source": TARGET_WEBSITE_AUDIT_RUN_ID},
                "website:target:pages": {"source": TARGET_WEBSITE_AUDIT_RUN_ID},
                "website:cuttlefish:audit": {"source": COHORT[0]["website_audit_run_id"]},
                "website:trevor:audit": {"source": COHORT[1]["website_audit_run_id"]},
                "website:simon:audit": {"source": COHORT[2]["website_audit_run_id"]},
                "reviews:target:set": {"google_place_id": TARGET_PLACE_ID},
                "reviews:target:themes": {"source": "derived_review_benchmark"},
                "reviews:cuttlefish:set": {"google_place_id": COHORT[0]["google_place_id"]},
                "reviews:trevor:set": {"google_place_id": COHORT[1]["google_place_id"]},
                "diagnostic:review_benchmark": {"source": "derived_review_benchmark"},
                "diagnostic:entity_matrix": {"source": "approved_stage3_comparison"},
                "diagnostic:proposition_coverage": {"source": "approved_stage3_comparison"},
                "market:cuttlefish": {"google_place_id": COHORT[0]["google_place_id"]},
                "market:trevor": {"google_place_id": COHORT[1]["google_place_id"]},
                "market:simon": {"google_place_id": COHORT[2]["google_place_id"]},
                **{
                    f"gap:{item['gap_id']}": {"source": ANALYST_DECISION_VERSION}
                    for item in APPROVED_ANALYST_DECISIONS["gaps"]
                },
            },
        },
        report=report,
    )
    return payload
