from __future__ import annotations

from typing import Any

from sqlalchemy.engine import Engine

from src.poc_audit_assembler import assemble_poc_audit_payload
from src.poc_audit_cisco_assembler import NON_BUSINESS_PREFIXES


RUN_ID = "34253ecf-1bfd-4a5b-92f8-6d326979f34a"
TARGET_PLACE_ID = "ChIJN8lvy9Ua-GYR0S9eO8irHIE"
TARGET_WEBSITE_AUDIT_RUN_ID = "da2f50a2-2dfe-43ef-90bb-45e781ec82fb"
TARGET_REVIEW_BATCH_ID = "ee724dec-5155-416d-82a5-d3e6b955edd3"
COMPARISON_REVIEW_BATCH_ID = "c8af2161-a2fd-4975-bb1c-499d082c5815"
CLEANOLOGY_REVIEW_BATCH_ID = "cae15f14-4050-4cc1-9003-f290b9d4fda2"
DECISION_VERSION = "udr_owner_services_review_draft_v1"


COHORT = (
    {
        "google_place_id": "ChIJAQADir6FdUgRyk0gZdQ9QfE",
        "business_name": "The Brighton Cleaning Company",
        "website_audit_run_id": "ce01d9d0-9df3-468e-9680-05afe1c7313a",
        "selection_reason": (
            "The strongest evidence-complete local business in the benchmark: "
            "recommended 14 times across seven of the eight questions by OpenAI and Gemini."
        ),
    },
    {
        "google_place_id": "ChIJZfPqoIGadUgRQpTQiBdp3ZE",
        "business_name": "Silver Star Cleaning Ltd",
        "website_audit_run_id": "291443cb-c3be-4115-b8d9-8e9c3e45d46c",
        "selection_reason": (
            "A Brighton comparison business recommended six times across three questions, "
            "with a usable local website and customer-review evidence."
        ),
    },
    {
        "google_place_id": "ChIJvfAqzVEEdkgRJFum4j03d-s",
        "business_name": "Cleanology",
        "website_audit_run_id": "45b2bfc5-080a-4bb7-a46f-89f97d9b997b",
        "selection_reason": (
            "Recommended four times by OpenAI and Gemini, usually near the top of the list, "
            "and useful as a deeper commercial-cleaning comparison."
        ),
    },
)


WEBSITE_AUDITS = (
    {
        "google_place_id": TARGET_PLACE_ID,
        "business_name": "UDR Properties",
        "website_audit_run_id": TARGET_WEBSITE_AUDIT_RUN_ID,
    },
    *COHORT,
)


REVIEW_SETS = (
    {
        "google_place_id": TARGET_PLACE_ID,
        "business_name": "UDR Properties",
        "record_count": 78,
        "import_batch_id": TARGET_REVIEW_BATCH_ID,
    },
    {
        "google_place_id": COHORT[0]["google_place_id"],
        "business_name": COHORT[0]["business_name"],
        "record_count": 1,
        "import_batch_id": COMPARISON_REVIEW_BATCH_ID,
    },
    {
        "google_place_id": COHORT[1]["google_place_id"],
        "business_name": COHORT[1]["business_name"],
        "record_count": 53,
        "import_batch_id": COMPARISON_REVIEW_BATCH_ID,
    },
    {
        "google_place_id": COHORT[2]["google_place_id"],
        "business_name": COHORT[2]["business_name"],
        "record_count": 100,
        "import_batch_id": CLEANOLOGY_REVIEW_BATCH_ID,
    },
)


ANALYST_DECISIONS: dict[str, Any] = {
    "version": DECISION_VERSION,
    "status": "review_draft",
    "provenance": (
        "Owner-priority cleaning services supplied in September 2026; new three-platform "
        "benchmark, website reviews and exact customer-review evidence."
    ),
    "introduction": {
        "owner_priority": (
            "UDR wants to be known for more than Airbnb changeovers: commercial and office "
            "cleaning, end-of-tenancy work, carpets, upholstery and laundry services."
        ),
        "method_steps": [
            {
                "title": "We turned your priorities into customer questions",
                "body": (
                    "We used eight realistic questions covering the cleaning services and "
                    "customers the owner said matter most."
                ),
            },
            {
                "title": "We tested visibility across three AI platforms",
                "body": (
                    "We used the OpenAI, Anthropic and Google APIs three times per question, then "
                    "checked all 72 answers and the businesses they named."
                ),
            },
            {
                "title": "We studied the businesses that were most visible",
                "body": (
                    "We compared selected AI-recommended businesses with UDR using their "
                    "websites and customer reviews to find practical opportunities."
                ),
            },
        ],
        "scope_note": (
            "This is a snapshot of how these platforms answered this exact set of questions "
            "on the audit date. Results can change, and no individual action guarantees an AI recommendation."
        ),
    },
    "executive_summary": {
        "headline": "UDR was not recommended in 72 tests of its priority cleaning services.",
        "summary": (
            "All 72 answers were valid. UDR already has a strong website and useful customer "
            "proof, so the opportunity is to make the brand and its priority services more "
            "consistent, distinctive and widely corroborated online."
        ),
        "strengths": [],
        "action_statement": (
            "Make UDR's commercial-cleaning proposition unmistakable, connect every priority "
            "service to specific local proof, and build recognition beyond the website."
        ),
        "non_causality": (
            "These actions strengthen the public evidence available to customers and digital "
            "platforms; they do not guarantee a change in AI recommendations."
        ),
    },
    "strengths": [
        {
            "strength_id": "strength_site_foundation",
            "title": "Strong website basics",
            "body": (
                "The 20-page review found service pages, pricing, FAQs, booking routes and "
                "structured business data."
            ),
            "evidence_refs": ["website:target:audit", "website:target:pages"],
        },
        {
            "strength_id": "strength_commercial_proof",
            "title": "Relevant customer proof",
            "body": (
                "Reviews cover office carpets, deep cleaning, property changeovers and "
                "responsive professional service."
            ),
            "evidence_refs": ["reviews:target:set", "diagnostic:review_benchmark"],
        },
        {
            "strength_id": "strength_local_service",
            "title": "Clear Brighton presence",
            "body": (
                "The homepage and services page clearly connect UDR with professional "
                "cleaning in Brighton and Hove."
            ),
            "evidence_refs": ["website:target:pages"],
        },
    ],
    "strengths_note": (
        "UDR is not starting from scratch. The report focuses on making a good foundation more "
        "specific to the work the business wants to win."
    ),
    "review_quotes": [
        {
            "review_id": "Ci9DQUlRQUNvZENodHljRjlvT2sxSlgybFhkVTR0UWpsTGRFVm1Xazk0V1d0dGFGRRAB",
            "google_place_id": TARGET_PLACE_ID,
            "business_name": "UDR Properties",
            "quote": "My go to for carpet and upholstery cleans, great service always",
            "takeaway": "Direct customer proof for two of UDR's priority services.",
        },
        {
            "review_id": "Ci9DQUlRQUNvZENodHljRjlvT2pGSFF6VTRYMXB2YUhabFZrVXpTRU01VURSVFpuYxAB",
            "google_place_id": TARGET_PLACE_ID,
            "business_name": "UDR Properties",
            "quote": "UDR team did a great job of End of Tenancy cleaning for me. Definitely recommend.",
            "takeaway": "A customer names the exact end-of-tenancy service UDR wants to grow.",
        },
        {
            "review_id": "Ci9DQUlRQUNvZENodHljRjlvT2kxalNEZElRVzEyVUcxaU5rNDVTRkI0TW1GS1pYYxAB",
            "google_place_id": TARGET_PLACE_ID,
            "business_name": "UDR Properties",
            "quote": "Very efficient and affordable. Would definitely use again",
            "takeaway": "Efficiency, value and repeat intent are clear customer benefits.",
        },
        {
            "review_id": "ChZDSUhNMG9nS0VJQ0FnSURZbm9YclF3EAE",
            "google_place_id": COHORT[1]["google_place_id"],
            "business_name": "Silver Star Cleaning Ltd",
            "quote": (
                "Had the house carpets cleaned last week & very happy with the results. The lads were "
                "friendly, courteous & did a great job. Would thoroughly recommend."
            ),
            "takeaway": "The review connects a specific service with the result and experience.",
        },
        {
            "review_id": "Ci9DQUlRQUNvZENodHljRjlvT2pKcVUwdDZUSEJIZDJRdFFrTlJPVW80V0UxRVRHYxAB",
            "google_place_id": COHORT[2]["google_place_id"],
            "business_name": "Cleanology",
            "quote": "Cleanology are amazing! We were so impressed with our deep clean!",
            "takeaway": "A short review still names a specific service and a clear reaction.",
        },
    ],
    "gaps": [
        {
            "gap_id": "gap_visibility",
            "title": "Turn a broad cleaning offer into clear reasons to recommend UDR",
            "observed": "UDR was not named in any of the 72 valid answers across eight priority questions.",
            "comparison": (
                "The Brighton Cleaning Company appeared across seven questions; Silver Star across "
                "three; and Cleanology across two commercial-cleaning questions."
            ),
            "relevance": (
                "Clear service-by-service positioning gives customers and digital platforms more "
                "specific evidence about when UDR is the right choice."
            ),
            "confidence": "High",
            "evidence_refs": ["market:target", "market:brighton", "market:silver", "market:cleanology"],
        },
        {
            "gap_id": "gap_brand_identity",
            "title": "Use one clear relationship between UDR Properties and UDR Cleaning",
            "observed": (
                "The Google business is UDR Properties while the website uses the UDR Cleaning domain "
                "and also presents UDR Properties Limited."
            ),
            "comparison": "The comparison businesses use their cleaning name consistently in their public-facing websites.",
            "relevance": (
                "A simple, consistent identity makes it easier to connect the business, website, "
                "reviews, Brighton location and cleaning services."
            ),
            "confidence": "High",
            "evidence_refs": ["website:target:audit", "diagnostic:entity_matrix"],
        },
        {
            "gap_id": "gap_service_focus",
            "title": "Give every priority service its own useful local evidence",
            "observed": (
                "The reviewed pages give far more space to washroom locations than to UDR's six "
                "priority service journeys."
            ),
            "comparison": (
                "The comparison sites use dedicated commercial, tenancy, laundry, lettings, office "
                "and sector pages."
            ),
            "relevance": (
                "Dedicated pages can answer buying questions about scope, process, location, proof and next steps."
            ),
            "confidence": "High",
            "evidence_refs": ["website:target:pages", "website:brighton:pages", "website:silver:pages", "website:cleanology:pages"],
        },
        {
            "gap_id": "gap_external_proof",
            "title": "Build recognition and proof beyond UDR's own website",
            "observed": (
                "UDR has 78 usable reviews and strong examples, but those strengths did not translate "
                "into a recommendation in this benchmark."
            ),
            "comparison": (
                "Visible names recur across different assistants even though their websites and review "
                "profiles vary, suggesting that no single asset explains the result."
            ),
            "relevance": (
                "Relevant local profiles, partner references, case studies and service-specific reviews "
                "can reinforce the same proposition across more independent sources."
            ),
            "confidence": "Moderate",
            "evidence_refs": ["reviews:target:set", "market:brighton", "market:silver", "market:cleanology"],
        },
    ],
    "provider_hypotheses": [
        {
            "business_name": "The Brighton Cleaning Company",
            "hypothesis": (
                "Its visibility across OpenAI and Gemini coincides with a strongly local name and "
                "pages for commercial, end-of-tenancy and laundry-related needs."
            ),
            "evidence_refs": ["market:brighton", "website:brighton:pages"],
        },
        {
            "business_name": "Silver Star Cleaning Ltd",
            "hypothesis": (
                "Its Gemini visibility coincides with dedicated local pages for commercial, lettings "
                "and specialist cleaning."
            ),
            "evidence_refs": ["market:silver", "website:silver:pages"],
        },
        {
            "business_name": "Cleanology",
            "hypothesis": (
                "Its OpenAI and Gemini visibility on commercial questions coincides with deep office "
                "and sector-specific content."
            ),
            "evidence_refs": ["market:cleanology", "website:cleanology:pages"],
        },
    ],
    "actions": [
        {
            "action_id": "action_identity",
            "title": "Choose and apply one clear public brand identity",
            "category": "Business identity",
            "steps": (
                "Decide how UDR Properties and UDR Cleaning relate, explain that relationship plainly, "
                "and use the same name, service description, address and contact details across the website, "
                "Google profile and relevant directories."
            ),
            "intended_improvement": "A clearer connection between the business entity, location and cleaning offer.",
            "timing": "Weeks 1-2",
            "evidence_refs": ["gap:gap_brand_identity", "website:target:audit"],
        },
        {
            "action_id": "action_service_pages",
            "title": "Build six strong Brighton service journeys",
            "category": "Priority services",
            "steps": (
                "Create a Brighton page for each of the six priority services. Explain who it is for, "
                "what is included, how it works, where it is available and how to request a quote."
            ),
            "intended_improvement": "Specific first-party evidence for every customer question tested.",
            "timing": "Weeks 1-6",
            "evidence_refs": ["gap:gap_service_focus", "website:target:pages"],
        },
        {
            "action_id": "action_commercial_proof",
            "title": "Turn completed work into convincing commercial proof",
            "category": "Expertise and proof",
            "steps": (
                "Publish short case studies for offices, landlords and property managers. Include the need, "
                "service delivered, location, practical result, relevant training or process, and a genuine "
                "customer comment where permission allows."
            ),
            "intended_improvement": "A more distinctive and credible explanation of why buyers should choose UDR.",
            "timing": "Weeks 2-8",
            "evidence_refs": ["gap:gap_visibility", "reviews:target:set"],
        },
        {
            "action_id": "action_reviews",
            "title": "Ask for reviews that naturally describe the job",
            "category": "Customer evidence",
            "steps": (
                "Use a compliant, non-incentivised follow-up after each job. Invite customers to describe "
                "the service, type of property, area and result in their own words, without scripting the review."
            ),
            "intended_improvement": "More current independent evidence across the services UDR wants to grow.",
            "timing": "Weeks 1-12",
            "evidence_refs": ["gap:gap_external_proof", "reviews:target:set"],
        },
        {
            "action_id": "action_local_authority",
            "title": "Strengthen relevant local and industry references",
            "category": "Recognition beyond the website",
            "steps": (
                "Complete the most relevant local and trade profiles, seek genuine supplier or partner references, "
                "and make sector experience easy to verify. Prioritise quality and consistency over a large number of listings."
            ),
            "intended_improvement": "Broader corroboration of UDR's Brighton commercial-cleaning proposition.",
            "timing": "Weeks 3-10",
            "evidence_refs": ["gap:gap_external_proof", "diagnostic:entity_matrix"],
        },
    ],
    "priority_action_ids": ["action_identity", "action_service_pages", "action_commercial_proof"],
    "provider_observation": (
        "UDR was not recommended by OpenAI, Claude or Gemini. The businesses that did appear varied "
        "substantially by assistant and question, so this report preserves those differences."
    ),
    "matrix_dimensions": [
        {"label": "Recommendations in the benchmark", "evidence_refs": ["market:target", "market:brighton", "market:silver", "market:cleanology"], "values": {"UDR Properties": "0 | not ranked", "Brighton Cleaning Co.": "14", "Silver Star": "6", "Cleanology": "4"}},
        {"label": "AI assistants recommending them", "evidence_refs": ["market:target", "market:brighton", "market:silver", "market:cleanology"], "values": {"UDR Properties": "0 / 3", "Brighton Cleaning Co.": "2 / 3", "Silver Star": "1 / 3", "Cleanology": "2 / 3"}},
        {"label": "Questions they appeared for", "evidence_refs": ["market:target", "market:brighton", "market:silver", "market:cleanology"], "values": {"UDR Properties": "0 / 8", "Brighton Cleaning Co.": "7 / 8", "Silver Star": "3 / 8", "Cleanology": "2 / 8"}},
        {"label": "Website pages reviewed", "evidence_refs": ["website:target:audit", "website:brighton:audit", "website:silver:audit", "website:cleanology:audit"], "values": {"UDR Properties": "20 pages", "Brighton Cleaning Co.": "20 pages", "Silver Star": "10 pages", "Cleanology": "20 pages"}},
        {"label": "Clear business details for digital systems", "evidence_refs": ["website:target:audit", "website:brighton:audit", "website:silver:audit", "website:cleanology:audit"], "values": {"UDR Properties": "Local business data detected", "Brighton Cleaning Co.": "Local schema not detected", "Silver Star": "Local schema not detected", "Cleanology": "Local schema not detected"}},
        {"label": "Relevant service evidence", "evidence_refs": ["website:target:pages", "website:brighton:pages", "website:silver:pages", "website:cleanology:pages"], "values": {"UDR Properties": "General services and deep washroom pages", "Brighton Cleaning Co.": "Commercial, tenancy and laundry pages", "Silver Star": "Commercial, lettings and specialist pages", "Cleanology": "Deep office and sector content"}},
        {"label": "Customer reviews analysed", "evidence_refs": ["reviews:target:set", "reviews:brighton:set", "reviews:silver:set", "reviews:cleanology:set"], "values": {"UDR Properties": "78", "Brighton Cleaning Co.": "1 - interpret cautiously", "Silver Star": "53", "Cleanology": "100"}},
    ],
    "matrix_note": (
        "The comparison set comes from businesses actually named in the AI answers and with sufficient "
        "evidence for useful analysis. Website and review differences are comparisons, not proven causes."
    ),
    "roadmap": {
        "phases": [
            {"timing": "Weeks 1-2", "title": "Clarify the brand and offer", "body": "Align UDR's public identity and map the six priority service journeys."},
            {"timing": "Weeks 2-8", "title": "Publish services and proof", "body": "Build useful pages and connect them to real commercial case studies."},
            {"timing": "Weeks 1-12", "title": "Grow independent evidence", "body": "Maintain service-specific review follow-up and strengthen relevant profiles."},
            {"timing": "Weeks 10-12", "title": "Remeasure", "body": "Repeat the same questions and disclose any platform or model changes."},
        ],
        "options": [
            {"title": "Implement internally", "body": "Use the action plan with existing web and marketing partners."},
            {"title": "Supported implementation", "body": "Work collaboratively on messaging, pages, proof and business profiles."},
            {"title": "Implementation + remeasurement", "body": "Complete delivery, verification and a comparable follow-up benchmark."},
        ],
        "remeasurement_note": "Suggested follow-up: 8-12 weeks after meaningful implementation.",
    },
}

ANALYST_DECISIONS["executive_summary"]["strengths"] = ANALYST_DECISIONS["strengths"][:3]


CONFIG: dict[str, Any] = {
    "report_format": "beta_accessible_v2",
    "run_id": RUN_ID,
    "target_google_place_id": TARGET_PLACE_ID,
    "target_business_name": "UDR Properties",
    "category": "Professional cleaning services",
    "location": "Brighton",
    "primary_group": "cleaning_services",
    "review_profile": "cleaning_services",
    "expected_responses": 72,
    "expected_eligible_slots": 286,
    "baseline_validation_status": "verified_zero",
    "verification_method_version": "owner_services_raw_response_reconciliation_v1",
    "target_explicit_terms": ("udr properties", "udr cleaning", "udr properties limited"),
    "target_indirect_terms": (),
    "response_verification_note": "Complete UDR owner-services benchmark reconciled against the target business identity.",
    "verification_statement": "All 72 responses completed. No explicit UDR recommendation or credible indirect target reference was found.",
    "slot_adjudications": {},
    "non_business_prefixes": tuple(NON_BUSINESS_PREFIXES) + (
        "checkatrade", "trustpilot", "facebook", "facebook local", "google reviews",
        "local directories", "ask your letting agent", "yell",
    ),
    "cohort": COHORT,
    "website_audits": WEBSITE_AUDITS,
    "review_sets": REVIEW_SETS,
    "analyst_decisions": ANALYST_DECISIONS,
    "matrix_businesses": ("UDR Properties", "Brighton Cleaning Co.", "Silver Star", "Cleanology"),
    "matrix_business_place_ids": {
        "UDR Properties": TARGET_PLACE_ID,
        "Brighton Cleaning Co.": COHORT[0]["google_place_id"],
        "Silver Star": COHORT[1]["google_place_id"],
        "Cleanology": COHORT[2]["google_place_id"],
    },
    "market_note": (
        "Business Share of Recommendation uses the named-business recommendations remaining after "
        "non-business suggestions are excluded. It describes this benchmark, not commercial market share."
    ),
    "provider_caveat": (
        "The report describes what each assistant recommended. It does not claim to know how or why "
        "any platform chose its answers."
    ),
    "cohort_note": (
        "The detailed comparison uses three AI-recommended businesses with usable website and review evidence. "
        "Other names remain in the full measured market even when a reliable local profile could not be confirmed."
    ),
    "gap_caveat": "Observed differences are evidence-backed opportunities, not proven causes of AI recommendations.",
    "action_caveat": "The actions strengthen public evidence; no AI visibility improvement is guaranteed.",
    "methodology_validation": (
        "72/72 valid responses: 24 per AI assistant",
        "Eight owner-priority cleaning questions, each asked three times per assistant",
        "286 recommendation items remained after obvious advice and platform names were removed",
        "No UDR recommendation or credible indirect reference",
        "Comparison businesses selected from the measured AI responses",
    ),
    "methodology_limitations": (
        "This is a model-memory benchmark, not a live web-search test.",
        "Results depend on the exact questions, model identifiers and audit date.",
        "AI outputs can vary between repetitions and over time.",
        "Some AI-named businesses could not be matched safely to a verified local profile.",
        "Website and review differences are observational, not causal.",
        "Business Share of Recommendation is not commercial market share.",
    ),
    "non_causality": "No website, identity or review difference is presented as a proven AI ranking factor or guaranteed cause of visibility.",
    "revision": {"snapshot_revision": 1, "supersedes_snapshot_id": None, "revision_reason": "UDR owner-priority services review draft"},
    "evidence_registry": {
        "market:target": {"google_place_id": TARGET_PLACE_ID},
        "market:brighton": {"google_place_id": COHORT[0]["google_place_id"]},
        "market:silver": {"google_place_id": COHORT[1]["google_place_id"]},
        "market:cleanology": {"google_place_id": COHORT[2]["google_place_id"]},
        "website:target:audit": {"source": TARGET_WEBSITE_AUDIT_RUN_ID},
        "website:target:pages": {"source": TARGET_WEBSITE_AUDIT_RUN_ID},
        "website:brighton:audit": {"source": COHORT[0]["website_audit_run_id"]},
        "website:brighton:pages": {"source": COHORT[0]["website_audit_run_id"]},
        "website:silver:audit": {"source": COHORT[1]["website_audit_run_id"]},
        "website:silver:pages": {"source": COHORT[1]["website_audit_run_id"]},
        "website:cleanology:audit": {"source": COHORT[2]["website_audit_run_id"]},
        "website:cleanology:pages": {"source": COHORT[2]["website_audit_run_id"]},
        "reviews:target:set": {"google_place_id": TARGET_PLACE_ID},
        "reviews:brighton:set": {"google_place_id": COHORT[0]["google_place_id"]},
        "reviews:silver:set": {"google_place_id": COHORT[1]["google_place_id"]},
        "reviews:cleanology:set": {"google_place_id": COHORT[2]["google_place_id"]},
        "diagnostic:review_benchmark": {"source": "deterministic cleaning-services review profile"},
        "diagnostic:entity_matrix": {"source": DECISION_VERSION},
        **{f"gap:{item['gap_id']}": {"source": DECISION_VERSION} for item in ANALYST_DECISIONS["gaps"]},
    },
}


def assemble_udr_owner_services_payload(*, engine: Engine | None = None) -> dict[str, Any]:
    return assemble_poc_audit_payload(CONFIG, engine=engine)
