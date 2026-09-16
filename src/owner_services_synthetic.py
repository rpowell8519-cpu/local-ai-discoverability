"""Coherent demonstration evidence; never use this fixture as client research."""
from src.poc_audit_payload import build_baseline_validation, build_poc_audit_payload, freeze_ai_response, freeze_review_set
from src.owner_services_report import FORMAT


def synthetic_owner_services_payload():
    providers = {"OpenAI": "synthetic-model-a", "Claude": "synthetic-model-b", "Gemini": "synthetic-model-c"}
    prompts = ["Which salons offer hair colouring in Exampletown?", "Where can I get balayage in Exampletown?",
               "Which salons offer curly haircuts in Exampletown?", "Who offers bridal hairstyling in Exampletown?"]
    queries, responses, slots = [], [], []
    for order, prompt in enumerate(prompts, 1):
        for repeat in (1, 2):
            query_id = f"synthetic-q{order}-r{repeat}"
            queries.append({"id": query_id, "base_prompt_order": order, "repeat_index": repeat, "prompt_text": prompt})
            for index, (provider, model) in enumerate(providers.items()):
                target_present = (repeat - 1) * 3 + index < {1: 6, 2: 4, 3: 2, 4: 0}[order]
                named = [("synthetic-other", "Example Colour Studio")]
                if target_present:
                    named.insert(0, ("synthetic-target", "Example Salon"))
                raw = "SYNTHETIC DEMONSTRATION ANSWER\n" + "\n".join(f"{n}. {name} — fictional recommendation." for n, (_, name) in enumerate(named, 1))
                responses.append(freeze_ai_response({"id": f"{query_id}-{provider}", "query_id": query_id, "provider": provider,
                    "model": model, "base_prompt_order": order, "prompt_text": prompt, "prompt_category": "Synthetic priority",
                    "repeat_index": repeat, "raw_response": raw, "status": "completed", "response_complete": True,
                    "created_at": "2026-01-15T10:00:00Z"}, parser_reconciliation={"target_correct": True},
                    explicit_matches=[{"business_name": "Example Salon", "credible": True}] if target_present else []))
                for pos, (pid, name) in enumerate(named, 1):
                    slots.append({"slot_disposition": "business", "google_place_id": pid, "business_name": name,
                                  "raw_business_name": name, "query_id": query_id, "provider": provider,
                                  "position": pos, "base_prompt_order": order, "repeat_index": repeat})
    pages = [
        {"id": "synthetic-colour", "url": "https://example.test/colour", "page_title": "Colour consultations — synthetic", "text_excerpt": "Colour consultations include a discussion of your desired result, maintenance and a patch test where required.", "crawled_at": "2026-01-14T12:00:00Z"},
        {"id": "synthetic-bridal", "url": "https://example.test/bridal", "page_title": "Bridal hair — synthetic", "text_excerpt": "Bridal hair. Page under construction. Contact us.", "crawled_at": "2026-01-14T12:01:00Z"},
    ]
    reviews = freeze_review_set(google_place_id="synthetic-target", business_name="Example Salon", records=[{
        "id": "synthetic-review-row", "review_id": "synthetic-review", "google_place_id": "synthetic-target", "business_name": "Example Salon",
        "review_text": "The colour consultation helped me understand the upkeep before booking.", "review_rating": 5,
        "review_datetime_utc": "2026-01-10T12:00:00Z", "source": "synthetic demonstration", "review_link": "https://example.test/review",
        "import_batch_id": "synthetic-reviews", "imported_at": "2026-01-14T13:00:00Z"}])
    config = {
        "synthetic": True, "evidence_index": "Owner Services Template - V4 - Synthetic - Evidence Index.html",
        "priority_context": "The fictional owner wants more colour, curly-cut and bridal enquiries. Hair extensions are also an owner priority.",
        "implication": "Colour is a measured strength in this example. Bridal visibility is missing in the chosen questions, while curly-cut appearances are mixed. These are different starting points—not a single negative score.",
        "coverage_note": "Colour has two questions; curly cuts and bridal each have one. Extensions were not tested. Only Exampletown and generic customers are covered; no nearby towns or separate customer groups were tested.",
        "services": [{"name": "Colour / balayage", "questions": [1, 2]}, {"name": "Curly cuts", "questions": [3]},
                     {"name": "Bridal hair", "questions": [4]}, {"name": "Hair extensions", "questions": []}],
        "sources": [{"ref": "W1", "kind": "website", "record_id": "synthetic-colour", "title": "Synthetic colour page", "excerpt": pages[0]["text_excerpt"]},
                    {"ref": "W2", "kind": "website", "record_id": "synthetic-bridal", "title": "Synthetic bridal page", "excerpt": pages[1]["text_excerpt"]},
                    {"ref": "R1", "kind": "review", "record_id": "synthetic-review", "title": "Synthetic colour review", "excerpt": reviews["records"][0]["review_text"]}],
        "strengths": [{"title": "Colour is a measured strength", "body": "The colour questions produce frequent appearances. The demonstration page explains consultations and upkeep, and the invented review supports that customer experience. This does not establish why the model answers named the salon.", "refs": ["Q1", "Q2", "W1", "R1"]}],
        "gaps": [{"title": "Bridal information is unfinished in the captured page", "body": "The complete short demonstration snapshot says the page is under construction. This supports checking and completing that existing page; it does not explain the zero bridal appearances.", "refs": ["W2", "Q4"]},
                 {"title": "Curly-cut evidence needs investigation", "body": "No curly-cut page was collected. We cannot conclude that the website lacks this content.", "refs": ["INVENTORY", "Q3"]}],
        "actions": [
            {"title": "1. Complete the existing bridal information", "need": "Bridal customers need to know whether a trial is offered and what the booking includes.", "observation": "The synthetic bridal page is explicitly under construction; the measured question also has no target appearances, without proving a connection.", "deliverable": "An owner-approved update to the existing bridal page explaining the trial, booking process, areas covered and enquiry route.", "supplier": "Salon owner: confirm actual services, dates and terms.", "implementer": "Website editor.", "effort": "Estimate: 2–4 hours for a small update after information is supplied.", "dependencies": "Owner confirmation of the service and availability; editor access.", "check": "The agreed customer questions are answered accurately and the enquiry route works on mobile.", "refs": ["W2", "Q4"]},
            {"title": "2. Investigate curly-cut information before changing it", "need": "A curly-haired customer needs to assess whether the salon can help.", "observation": "The website sample contains no curly-cut page. This is missing collected evidence, not a finding that such a page does not exist.", "deliverable": "A list of existing relevant pages and a short assessment of the information and customer proof they contain.", "supplier": "Salon owner: confirm services and provide page addresses.", "implementer": "Audit reviewer with the website editor.", "effort": "Estimate: 1–2 hours for investigation; no implementation estimate yet.", "dependencies": "Access to complete page content and owner-confirmed service scope.", "check": "Record the inspected URLs, dates and exact observations. Recommend a change only if a specific gap is established.", "refs": ["INVENTORY", "Q3"]},
        ],
    }
    return build_poc_audit_payload(
        audit={"baseline_run_id": "synthetic-owner-services-v4", "target_google_place_id": "synthetic-target", "target_business_name": "Example Salon", "audit_date": "2026-01-15"},
        revision={"snapshot_revision": 1, "revision_reason": "Synthetic demonstration; no database snapshot", "supersedes_snapshot_id": None},
        methodology={"providers": list(providers), "models": providers, "prompt_count": 4, "repetitions": 2, "queries": queries, "benchmark_mode": "model_memory"},
        baseline_validation=build_baseline_validation(responses, expected_responses=24, status="reviewed", verification_method_version="synthetic-v4"),
        source_traceability={"ai_run_id": "synthetic-owner-services-v4"},
        recommendation_market={"original_slot_count": len(slots), "business_slot_count": len(slots), "non_business_slot_count": 0, "slot_evidence": slots, "canonical_businesses": []},
        website_evidence={"audits": [{"id": "synthetic-site", "google_place_id": "synthetic-target", "business_name": "Example Salon", "pages": pages}]},
        review_evidence={"review_sets": [reviews]},
        diagnostic={"cohort": [{"google_place_id": "synthetic-other", "business_name": "Example Colour Studio", "location_reason": "Location unknown in this demonstration; do not label this a verified local comparator."}], "analyst_decisions": {"version": "synthetic-v4"}, "evidence_registry": {}},
        report={"report_format": FORMAT, "owner_report": config, "owner_competitors": []})
