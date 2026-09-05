from __future__ import annotations

from src.poc_audit_payload import build_baseline_validation, build_poc_audit_payload, freeze_ai_response, freeze_review_set


def synthetic_poc_audit_payload() -> dict:
    """Return generic structural data, never client report truth."""
    providers = [("OpenAI", "model-a"), ("Claude", "model-b"), ("Gemini", "model-c")]
    prompt_panel = [
        ("General recommendation", "core_market", "Recommend an example local service business."),
        ("Quality", "core_market", "Which example businesses are known for quality?"),
        ("Friendly service", "core_market", "Recommend a friendly example business."),
        ("Expertise", "core_market", "Which example businesses are known for expertise?"),
        ("Consultation", "core_market", "Where can I get a useful example consultation?"),
        ("Results", "core_market", "Which example businesses deliver consistent results?"),
        ("Client proposition", "client_proposition", "Recommend an example business for service alpha."),
        ("Client proposition", "client_proposition", "Recommend an example business for service beta."),
    ]
    queries = [
        {"id": f"query-{order}", "base_prompt_order": order, "repeat_index": 1,
         "prompt_category": category, "prompt_source": source, "prompt_text": prompt}
        for order, (category, source, prompt) in enumerate(prompt_panel, 1)
    ]
    responses = [freeze_ai_response({"id": f"response-{order}-{provider}", "query_id": f"query-{order}",
        "provider": provider, "model": model, "base_prompt_order": order, "prompt_category": category,
        "prompt_text": prompt, "repeat_index": 1,
        "raw_response": f"Synthetic complete response from {provider} for prompt {order}.", "status": "completed",
        "response_complete": True, "finish_reason": "stop", "created_at": "2026-01-01T00:00:00+00:00"},
        parser_reconciliation={"target_correct": True, "persisted_target_mentioned": False,
                               "persisted_target_recommended": False})
        for order, (category, source, prompt) in enumerate(prompt_panel, 1)
        for provider, model in providers]
    baseline = build_baseline_validation(responses, expected_responses=24, status="verified_zero",
                                         verification_method_version="synthetic_test_v1")
    leaders = [("place-a", "Alpha Salon"), ("place-b", "Beta Salon"), ("place-c", "Gamma Salon")]
    slots = [{"slot_disposition": "business", "google_place_id": pid, "business_name": name,
              "recommendation_position": 1} for pid, name in leaders]
    market = [{"google_place_id": pid, "business_name": name, "recommendations": 1,
               "share_of_recommendation": 1 / 3} for pid, name in leaders]
    audits = [{"id": f"audit-{pid}", "google_place_id": pid, "business_name": name,
               "pages": [{"id": f"page-{pid}", "url": f"https://example.test/{pid}"}]}
              for pid, name in [("target-place", "Example Salon"), *leaders]]
    review_sets = [freeze_review_set(google_place_id=pid, business_name=name,
        records=[{"id": f"internal-{pid}", "review_id": f"review-{pid}", "google_place_id": pid,
                  "business_name": name, "review_text": "A useful synthetic review.", "review_rating": 5}])
        for pid, name in [("target-place", "Example Salon"), leaders[0], leaders[1]]]
    review_sets.append(freeze_review_set(google_place_id="place-c", business_name="Gamma Salon", records=[],
        status="exception", exception={"description": "Synthetic review evidence unavailable.",
                                        "comparison_treatment": "Excluded from review comparison."}))
    refs = {name: {"source": "synthetic"} for name in ("website:target:audit", "website:target:pages",
        "reviews:target:set", "diagnostic:entity", "gap:entity", "market:a", "market:b", "market:c")}
    refs["website:target:audit"]["source"] = "audit-target-place"
    refs["website:target:pages"]["source"] = "audit-target-place"
    strengths = [{"title": f"Synthetic strength {i}", "body": "Observed structural evidence.",
                  "evidence_refs": ["website:target:pages"]} for i in range(1, 5)]
    gaps = [{"title": f"Synthetic gap {i}", "observed": "Target evidence is limited.",
             "comparison": "Comparator evidence is clearer.", "relevance": "This is an observable comparison.",
             "confidence": "Moderate", "evidence_refs": ["diagnostic:entity"]} for i in range(1, 5)]
    actions = [{"action_id": f"action-{i}", "title": f"Synthetic action {i}", "timing": "Weeks 1-2",
                "steps": "Improve the represented evidence.", "intended_improvement": "Clearer underlying public evidence.",
                "evidence_refs": ["gap:entity"]} for i in range(1, 4)]
    cohort = [{"google_place_id": pid, "business_name": name, "recommendations": 1,
               "business_sor_pct": 100 / 3, "provider_names": [providers[i][0]], "provider_breadth": 1,
               "intent_breadth": 1, "selection_reason": "Provides a distinct synthetic comparison."}
              for i, (pid, name) in enumerate(leaders)]
    names = ["Example Salon", "Alpha Salon", "Beta Salon", "Gamma Salon"]
    dimensions = [{"label": label, "evidence_refs": ["diagnostic:entity"],
                   "values": {name: value for name in names}} for label, value in (
        ("AI visibility", "Measured"), ("Provider breadth", "1 / 3"), ("Intent breadth", "1 / 1"),
        ("Site footprint", "1 page"), ("Structured data", "Synthetic observation"),
        ("Service evidence", "Synthetic evidence"), ("Review evidence", "Synthetic set"))]
    report = {
        "client_context": {"category": "Example services", "location": "Exampletown"},
        "executive_summary": {"headline": "The target was absent from this synthetic benchmark.",
            "summary": "All synthetic responses were inspected.", "strengths": strengths[:3],
            "action_statement": "Improve the represented public evidence.",
            "non_causality": "Observed differences are not proven ranking factors."},
        "visibility": {"responses_complete": 24, "responses_expected": 24, "mentions": 0, "recommendations": 0,
            "business_sor_pct": 0.0, "providers": [{"name": p, "complete": 8, "expected": 8,
            "recommendations": 0} for p, _ in providers], "intents": [item[0] for item in prompt_panel],
            "verification_statement": "All synthetic raw text was inspected."},
        "recommendation_market": {"original_slots": 3, "business_slots": 3, "excluded_slots": 0,
            "businesses": [{**item, "business_sor_pct": 100 / 3} for item in market],
            "market_note": "Synthetic business slots only."},
        "provider_comparison": [{"business": name, "OpenAI": int(i == 0), "Claude": int(i == 1),
            "Gemini": int(i == 2), "provider_breadth": 1, "intent_breadth": 1}
            for i, (_, name) in enumerate(leaders)] + [{"business": "Example Salon", "OpenAI": 0,
            "Claude": 0, "Gemini": 0, "provider_breadth": 0, "intent_breadth": 0}],
        "provider_observation": "Synthetic providers differ.", "provider_caveat": "No undocumented mechanism is inferred.",
        "diagnostic_cohort": cohort, "cohort_note": "Synthetic comparison subset.",
        "evidence_matrix": {"businesses": names,
            "business_place_ids": dict(zip(names, ["target-place", "place-a", "place-b", "place-c"])),
            "dimensions": dimensions, "note": "Gamma review evidence is unavailable."},
        "strengths": strengths, "strengths_note": "Build on represented strengths.", "priority_gaps": gaps,
        "gap_caveat": "These are observations, not causes.", "full_action_plan": actions,
        "priority_action_ids": [a["action_id"] for a in actions], "priority_actions": actions,
        "action_caveat": "No visibility outcome is guaranteed.",
        "roadmap": {"phases": [{"timing": f"Phase {i}", "title": f"Step {i}", "body": "Synthetic delivery step."}
            for i in range(1, 5)], "options": [{"title": f"Option {i}", "body": "Synthetic delivery option."}
            for i in range(1, 4)], "remeasurement_note": "Remeasure after meaningful implementation."},
        "methodology": {"providers": [p for p, _ in providers], "models": dict(providers), "prompt_count": 8,
            "repetitions": 1, "expected_responses": 24, "complete_responses": 24,
            "benchmark": "Synthetic model-memory benchmark", "validation": ["24/24 complete"],
            "evidence_inventory": ["Synthetic evidence only"], "limitations": ["This fixture is not client evidence."],
            "non_causality": "No observed difference is a proven AI ranking factor."}}
    decisions = {"version": "synthetic_v1", "status": "operator_approved", "strengths": strengths,
                 "gaps": gaps, "actions": actions, "provider_hypotheses": []}
    return build_poc_audit_payload(
        audit={"baseline_run_id": "synthetic-run", "target_google_place_id": "target-place",
               "target_business_name": "Example Salon", "audit_date": "2026-01-01"},
        revision={"snapshot_revision": 1, "supersedes_snapshot_id": None, "revision_reason": "Synthetic fixture"},
        methodology={"providers": [p for p, _ in providers], "models": dict(providers), "prompt_count": 8,
                     "repetitions": 1, "queries": queries}, baseline_validation=baseline,
        source_traceability={"ai_run_id": "synthetic-run"}, recommendation_market={"original_slot_count": 3,
            "business_slot_count": 3, "non_business_slot_count": 0, "slot_evidence": slots,
            "canonical_businesses": market}, website_evidence={"audits": audits},
        review_evidence={"review_sets": review_sets}, diagnostic={"cohort": cohort,
            "analyst_decisions": decisions, "evidence_registry": refs}, report=report)
