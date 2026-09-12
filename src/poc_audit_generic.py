from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.database import get_engine
from src.poc_audit_assembler import assemble_poc_audit_payload
from src.poc_audit_cisco_assembler import NON_BUSINESS_PREFIXES
from src.poc_audit_production import PocAuditDefinition, ReviewablePocAudit, build_reviewable_poc_audit
from src.report_audit_candidates import load_report_candidates


def _rows(connection, sql: str, parameters: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(text(sql), dict(parameters or {})).mappings().all()]


def _evidence_definitions(
    connection, place_ids: list[str], names: Mapping[str, str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, int]]]:
    websites: list[dict[str, Any]] = []
    reviews: list[dict[str, Any]] = []
    inventory: dict[str, dict[str, int]] = {}
    for place_id in place_ids:
        website = connection.execute(
            text(
                """
                select war.id, war.pages_crawled
                from website_audit_runs war
                where war.google_place_id = :place_id
                  and war.audit_status in ('completed', 'partial')
                  and exists (select 1 from website_audit_pages wap where wap.audit_run_id = war.id)
                order by war.completed_at desc nulls last, war.started_at desc, war.id desc
                limit 1
                """
            ),
            {"place_id": place_id},
        ).mappings().first()
        if website:
            websites.append(
                {
                    "google_place_id": place_id,
                    "business_name": names[place_id],
                    "website_audit_run_id": str(website["id"]),
                }
            )
        review_count = int(
            connection.execute(
                text(
                    "select count(*) from business_reviews where google_place_id = :place_id and nullif(btrim(review_text), '') is not null"
                ),
                {"place_id": place_id},
            ).scalar_one()
        )
        frozen_count = min(review_count, 100)
        if frozen_count:
            reviews.append(
                {
                    "google_place_id": place_id,
                    "business_name": names[place_id],
                    "record_count": frozen_count,
                    "import_batch_id": None,
                }
            )
        else:
            reviews.append(
                {
                    "google_place_id": place_id,
                    "business_name": names[place_id],
                    "status": "exception",
                    "exception": {
                        "description": "No customer review text was available when this report was prepared.",
                        "comparison_treatment": "Review evidence was marked unavailable and was not scored as poor performance.",
                    },
                }
            )
        inventory[place_id] = {
            "website_pages": int(website["pages_crawled"] or 0) if website else 0,
            "reviews": frozen_count,
        }
    return websites, reviews, inventory


def assemble_generic_report_payload(
    audit_revision: Mapping[str, Any], *, engine: Engine | None = None
) -> dict[str, Any]:
    """Assemble the accessible report from a completed generic review revision."""

    if not audit_revision.get("reviewer_decisions_complete"):
        raise ValueError("The report review must be completed before generation")
    run_id = str(audit_revision.get("benchmark_run_id") or "")
    decisions_input = dict(audit_revision.get("reviewer_decisions") or {})
    cohort_ids = [str(item) for item in decisions_input.get("cohort_place_ids") or []]
    if len(cohort_ids) != 3:
        raise ValueError("Exactly three verified AI-visible comparison businesses are required")

    database = engine or get_engine()
    with database.connect() as connection:
        run = connection.execute(
            text("select * from ai_visibility_runs where id = cast(:id as uuid)"), {"id": run_id}
        ).mappings().first()
        if not run or str(run.get("status")) != "completed":
            raise ValueError("The attached benchmark is not complete")
        provider_names = {str(item).lower() for item in list(run["providers"])}
        if not ({"openai", "gemini"} <= provider_names and provider_names & {"claude", "anthropic"}):
            raise ValueError("The accessible report requires completed OpenAI, Claude and Gemini results")
        business_rows = _rows(
            connection,
            "select google_place_id, business_name from business_features where google_place_id = any(:ids)",
            {"ids": [str(audit_revision["target_google_place_id"]), *cohort_ids]},
        )
        names = {str(item["google_place_id"]): str(item["business_name"]) for item in business_rows}
        if any(place_id not in names for place_id in cohort_ids):
            raise ValueError("Every comparison business must have a verified Google Place ID")
        all_ids = [str(audit_revision["target_google_place_id"]), *cohort_ids]
        websites, review_sets, inventory = _evidence_definitions(connection, all_ids, names)
        target_response_recommendations = int(
            connection.execute(
                text(
                    """
                    select count(*) from ai_visibility_results
                    where run_id = cast(:run_id as uuid)
                      and status = 'completed'
                      and coalesce(response_complete, true)
                      and coalesce(target_recommended, false)
                    """
                ),
                {"run_id": run_id},
            ).scalar_one()
        )
        review_ids = [str(item) for item in decisions_input.get("review_quote_ids") or []]
        quote_rows = _rows(
            connection,
            """
            select review_id, google_place_id, business_name, review_text
            from business_reviews
            where review_id = any(:review_ids)
            """,
            {"review_ids": review_ids or ["__none__"]},
        )

    target_id = str(audit_revision["target_google_place_id"])
    target_name = str(audit_revision["target_business_name"])
    owner_context = dict(audit_revision.get("owner_context") or {})
    location = str(run.get("location_context") or "the local area")
    category = str(run.get("target_category_label") or run.get("primary_group") or "Local services").replace("_", " ").title()
    expected = int(run["prompt_count"]) * int(run["repeat_count"]) * len(list(run["providers"]))
    recommendations = target_response_recommendations
    candidate_summary = load_report_candidates(
        run_id=run_id,
        target_google_place_id=target_id,
        engine=database,
    )
    recommendation_counts = {
        str(item["google_place_id"]): int(item.get("recommendations") or 0)
        for item in candidate_summary["verified"]
    }
    headline = str(decisions_input.get("headline") or (
        f"{target_name} appeared in {recommendations} of {expected} AI responses."
        if recommendations else
        f"{target_name} was not recommended in this {expected}-response benchmark."
    ))
    summary = str(decisions_input.get("summary") or (
        "This report shows where the business appeared for the owner-approved customer questions, "
        "which businesses were most visible, and practical opportunities in the public evidence available."
    ))
    generic_ref = "diagnostic:review"
    strengths = [
        {
            "strength_id": "strength_owner_focus",
            "title": "Clear owner priorities",
            "body": "The benchmark is based on the services, customers and searches the owner said matter most.",
            "evidence_refs": [generic_ref],
        },
        {
            "strength_id": "strength_identity",
            "title": "Verified business identity",
            "body": "The target and selected comparison businesses are tied to confirmed Google Place IDs.",
            "evidence_refs": [generic_ref],
        },
        {
            "strength_id": "strength_evidence",
            "title": "Evidence limitations are explicit",
            "body": "Website or review evidence that was unavailable is stated clearly rather than treated as weak performance.",
            "evidence_refs": [generic_ref],
        },
    ]
    gaps = [
        {"gap_id": "gap_service_clarity", "title": "Make priority services unmistakable", "observed": "The owner priorities define the searches the business wants to win.", "comparison": "AI-visible businesses provide useful reference points for how those services are described publicly.", "relevance": "Clear service and location information helps customers understand whether the business fits their need.", "confidence": "Moderate", "evidence_refs": [generic_ref]},
        {"gap_id": "gap_customer_proof", "title": "Connect customer proof to priority work", "observed": "Available review evidence does not always use the same specific language as the owner-priority searches.", "comparison": "The selected comparison set shows how specific services and customer outcomes can be corroborated.", "relevance": "Service-specific proof makes the proposition easier for customers to verify.", "confidence": "Moderate", "evidence_refs": [generic_ref]},
        {"gap_id": "gap_external_consistency", "title": "Strengthen consistent external evidence", "observed": "The benchmark produced a distinct set of frequently recommended businesses.", "comparison": "Those businesses provide observable examples of visibility across more than one question or assistant.", "relevance": "Consistent public business details reduce ambiguity for customers and digital systems.", "confidence": "Moderate", "evidence_refs": [generic_ref]},
    ]
    action_titles = list(decisions_input.get("action_titles") or [])
    defaults = [
        "Align the business identity and priority-service wording",
        "Publish useful pages for the highest-priority customer questions",
        "Build service-specific customer proof and external references",
    ]
    action_titles = (action_titles + defaults)[:3]
    actions = [
        {"action_id": f"action_{index}", "title": title, "category": "Public evidence", "steps": "Use the owner priorities and observed comparison evidence to make this information clear, accurate and easy to verify.", "intended_improvement": "Clearer client-controllable public evidence for the agreed customer need.", "timing": timing, "evidence_refs": [generic_ref]}
        for index, (title, timing) in enumerate(zip(action_titles, ("Weeks 1-2", "Weeks 2-8", "Weeks 3-10")), 1)
    ]
    cohort = [
        {"google_place_id": place_id, "business_name": names[place_id], "website_audit_run_id": next((item["website_audit_run_id"] for item in websites if item["google_place_id"] == place_id), None), "selection_reason": "A verified business selected because it appeared prominently in the saved AI benchmark."}
        for place_id in cohort_ids
    ]
    matrix_names = [target_name, *[names[item] for item in cohort_ids]]
    dimensions = []
    for label, values in (
        ("Recommendations in the benchmark", {target_name: str(recommendations), **{names[pid]: str(recommendation_counts.get(pid, 0)) for pid in cohort_ids}}),
        ("Verified business identity", {name: "Google Place ID confirmed" for name in matrix_names}),
        ("Website pages reviewed", {names[pid]: (str(inventory[pid]["website_pages"]) if inventory[pid]["website_pages"] else "Not available") for pid in all_ids}),
        ("Customer reviews analysed", {names[pid]: (str(inventory[pid]["reviews"]) if inventory[pid]["reviews"] else "Not available") for pid in all_ids}),
        ("Owner-priority relevance", {target_name: "Defined by owner", **{names[pid]: "Selected from AI answers" for pid in cohort_ids}}),
        ("Evidence treatment", {names[pid]: "Compared where available" for pid in all_ids}),
    ):
        dimensions.append({"label": label, "evidence_refs": [generic_ref], "values": {name: values.get(name, "Not available") for name in matrix_names}})
    review_quotes = [
        {"review_id": str(item["review_id"]), "google_place_id": str(item["google_place_id"]), "business_name": str(item.get("business_name") or names.get(str(item["google_place_id"]), "Business")), "quote": str(item["review_text"]), "takeaway": "A direct example of the customer language available in the saved review evidence."}
        for item in quote_rows
    ]
    evidence_registry = {generic_ref: {"source": f"report audit revision {audit_revision['id']}"}}
    analyst_decisions = {
        "version": f"report_audit_revision_{audit_revision['revision']}",
        "status": "operator_approved",
        "provenance": "Owner brief, saved benchmark and reviewer-approved comparison set.",
        "introduction": {
            "owner_priority": str(audit_revision["known_for"]),
            "method_steps": [
                {"title": "We turned your priorities into customer questions", "body": f"We used {int(run['prompt_count'])} owner-reviewed questions about the services and customers that matter."},
                {"title": "We tested visibility across three AI platforms", "body": f"We checked {expected} saved API responses across OpenAI, Claude and Gemini."},
                {"title": "We studied the businesses that were most visible", "body": "We selected three verified businesses from the AI answers and compared available website and review evidence."},
            ],
            "scope_note": "This is a snapshot of answers to the exact questions and models shown. Results can change and no action guarantees a recommendation.",
        },
        "executive_summary": {"headline": headline, "summary": summary, "strengths": strengths, "action_statement": "Focus first on clear priority-service information, specific customer proof and consistent business identity.", "non_causality": "These actions improve public evidence; they do not guarantee a change in AI recommendations."},
        "strengths": strengths,
        "strengths_note": "These foundations make the next improvements more focused and measurable.",
        "review_quotes": review_quotes,
        "gaps": gaps,
        "actions": actions,
        "priority_action_ids": [item["action_id"] for item in actions],
        "provider_observation": "The assistants produced different recommendation patterns across the owner-approved questions.",
        "matrix_dimensions": dimensions,
        "matrix_note": "Unavailable evidence is shown explicitly and is not treated as poor performance. Observed differences are not proven causes.",
        "roadmap": {
            "phases": [
                {"timing": "Weeks 1-2", "title": "Confirm priorities and identity", "body": "Align the public business identity with the owner-approved services and locations."},
                {"timing": "Weeks 2-8", "title": "Publish useful service evidence", "body": "Address the priority customer questions with clear, accurate pages and proof."},
                {"timing": "Weeks 3-10", "title": "Strengthen external corroboration", "body": "Build relevant customer and third-party evidence without chasing low-quality listings."},
                {"timing": "Weeks 10-12", "title": "Remeasure", "body": "Repeat the same questions and disclose any platform or model changes."},
            ],
            "options": [
                {"title": "Implement internally", "body": "Use the action plan with existing web and marketing partners."},
                {"title": "Supported implementation", "body": "Work collaboratively on pages, proof and profiles."},
                {"title": "Implementation + remeasurement", "body": "Complete delivery, verification and a comparable follow-up benchmark."},
            ],
            "remeasurement_note": "Suggested follow-up: 8-12 weeks after meaningful implementation.",
        },
        "provider_hypotheses": [],
    }
    config = {
        "report_format": "beta_accessible_v2",
        "run_id": run_id,
        "target_google_place_id": target_id,
        "target_business_name": target_name,
        "category": category,
        "location": location,
        "primary_group": str(run.get("primary_group") or "generic"),
        "review_profile": str(run.get("primary_group") or "generic"),
        "expected_responses": expected,
        "expected_eligible_slots": None,
        "baseline_validation_status": "reviewed",
        "verification_method_version": "generic_report_reconciliation_v1",
        "target_explicit_terms": (target_name.casefold(),),
        "target_indirect_terms": (),
        "response_verification_note": "Saved completed response reconciled with the persisted target recommendation fields.",
        "verification_statement": f"{expected} expected responses were loaded from the attached completed benchmark.",
        "slot_adjudications": {},
        "non_business_prefixes": tuple(NON_BUSINESS_PREFIXES),
        "cohort": cohort,
        "website_audits": websites,
        "review_sets": review_sets,
        "analyst_decisions": analyst_decisions,
        "matrix_businesses": tuple(matrix_names),
        "matrix_business_place_ids": {name: pid for name, pid in zip(matrix_names, all_ids)},
        "market_note": "Business Share of Recommendation describes named-business recommendations in this benchmark, not commercial market share.",
        "provider_caveat": "The report describes what each assistant recommended and does not assume how any platform chose its answers.",
        "cohort_note": "The comparison set contains three reviewer-approved, verified businesses found in the measured AI answers.",
        "gap_caveat": "Observed differences are evidence-backed opportunities, not proven causes of AI recommendations.",
        "action_caveat": "The actions strengthen public evidence; no AI visibility improvement is guaranteed.",
        "methodology_validation": (f"{expected} saved response records loaded", f"{int(run['prompt_count'])} owner-reviewed questions", "Comparison businesses selected from measured AI responses"),
        "methodology_limitations": ("This is a model-memory benchmark, not a live web-search test.", "Results depend on the exact questions, models and audit date.", "Unavailable website or review evidence is disclosed rather than scored.", "Observed differences are not causal."),
        "non_causality": "No website, identity or review difference is presented as a proven ranking factor.",
        "revision": {"snapshot_revision": 1, "supersedes_snapshot_id": None, "revision_reason": "Reviewable generic report draft"},
        "evidence_registry": evidence_registry,
    }
    return assemble_poc_audit_payload(config, engine=database)


def build_reviewable_generic_audit(
    audit_revision: Mapping[str, Any], *, engine: Engine | None = None
) -> ReviewablePocAudit:
    definition = PocAuditDefinition(
        key=f"generic_{audit_revision['id']}",
        baseline_run_id=str(audit_revision["benchmark_run_id"]),
        target_google_place_id=str(audit_revision["target_google_place_id"]),
        client_name=str(audit_revision["target_business_name"]),
        pdf_filename=(str(audit_revision["target_business_name"]).lower().replace(" ", "-") + "-ai-visibility-report.pdf"),
        assembler=lambda: assemble_generic_report_payload(audit_revision, engine=engine),
        report_template="accessible_owner_services_v1",
    )
    return build_reviewable_poc_audit(definition)
