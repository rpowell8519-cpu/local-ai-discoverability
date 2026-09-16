from __future__ import annotations

from typing import Any

from sqlalchemy.engine import Engine

from src.poc_audit_assembler import assemble_poc_audit_payload
from src.poc_audit_cisco_assembler import NON_BUSINESS_PREFIXES


RUN_ID = "6126a8f0-698a-41a1-8893-f954d2a5e92c"
TARGET_PLACE_ID = "ChIJN8lvy9Ua-GYR0S9eO8irHIE"
TARGET_WEBSITE_AUDIT_RUN_ID = "da2f50a2-2dfe-43ef-90bb-45e781ec82fb"
TARGET_REVIEW_BATCH_ID = "ee724dec-5155-416d-82a5-d3e6b955edd3"
COMPARISON_REVIEW_BATCH_ID = "c8af2161-a2fd-4975-bb1c-499d082c5815"
CLEANOLOGY_REVIEW_BATCH_ID = "cae15f14-4050-4cc1-9003-f290b9d4fda2"
DECISION_VERSION = "udr_search_grounded_owner_services_v4"


COHORT = (
    {
        "google_place_id": "ChIJ2au3qUGFdUgR1WGegTirnu0",
        "business_name": "Why Bother Cleaning we'll do it for you",
        "website_audit_run_id": "5e28adae-26ae-433e-a43f-e0c47096d14f",
        "location_classification": "local",
        "location_reason": "Located in Brighton, within UDR's stated service area.",
        "selection_reason": (
            "The most frequently recommended verified Brighton business in the new benchmark, "
            "appearing across OpenAI, Claude and Gemini."
        ),
    },
    {
        "google_place_id": "ChIJZfPqoIGadUgRQpTQiBdp3ZE",
        "business_name": "Silver Star Cleaning Ltd",
        "website_audit_run_id": "291443cb-c3be-4115-b8d9-8e9c3e45d46c",
        "location_classification": "local",
        "location_reason": "Located in Hove, within UDR's stated service area.",
        "selection_reason": (
            "A local comparison business recommended 11 times across all three assistants, "
            "with a usable website and customer-review evidence."
        ),
    },
    {
        "google_place_id": "ChIJYYIhcgaFdUgRHbtHf_xaFns",
        "business_name": "Stellar End of Tenancy Cleaning Brighton",
        "website_audit_run_id": "0e26a751-2590-46eb-91b0-3d3e200c2c05",
        "location_classification": "local",
        "location_reason": "Located in Hove, within UDR's stated service area.",
        "selection_reason": (
            "A Hove-based owner-nominated competitor that was also recommended by Claude and Gemini, "
            "making it useful in both the owner and measured competitor views."
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
        "status": "exception",
        "exception": {
            "description": "No customer review text was available when this report was prepared.",
            "comparison_treatment": "Review evidence was marked unavailable and was not scored as poor performance.",
        },
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
        "status": "exception",
        "exception": {
            "description": "No customer review text was available when this report was prepared.",
            "comparison_treatment": "Review evidence was marked unavailable and was not scored as poor performance.",
        },
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
    "story": {
        "headline": "UDR appeared for Airbnb cleaning, but not for the other five cleaning questions tested.",
        "segments": [
            {
                "label": "Airbnb cleaning and changeovers (3 questions)",
                "appearances": 17,
                "answers": 27,
                "detail": "UDR appeared in the saved answers for all three Airbnb-focused questions.",
            },
            {
                "label": "Commercial, office, tenancy, carpet and upholstery (5 questions)",
                "appearances": 0,
                "answers": 45,
                "detail": "UDR did not appear in the saved answers for these five questions.",
            },
        ],
        "overall": "Overall: UDR appeared in 17 of 72 answers after UDR Properties and UDR Cleaning were reconciled.",
        "coverage_note": "Laundry is an owner priority but had no dedicated question in this benchmark. Keep this run unchanged for comparison and version a more balanced question set before any future authorised measurement.",
    },
    "service_evidence_businesses": ["UDR Properties", "Why Bother", "Silver Star", "Stellar"],
    "service_evidence_matrix": [
        {"question": "Does the website clearly explain office cleaning?", "values": {"UDR Properties": "Partly shown; needs a clearer dedicated explanation", "Why Bother": "Observed on local cleaning pages", "Silver Star": "Observed on commercial pages", "Stellar": "Not captured in pages reviewed"}},
        {"question": "Does it show a relevant local example?", "values": {"UDR Properties": "Customer evidence available; local examples to make clearer", "Why Bother": "Not captured in pages reviewed", "Silver Star": "Customer-review evidence available", "Stellar": "Not captured in pages reviewed"}},
        {"question": "Does it explain what is included?", "values": {"UDR Properties": "General service information; scope can be clearer", "Why Bother": "Observed on local cleaning pages", "Silver Star": "Observed on specialist pages", "Stellar": "End-of-tenancy scope observed"}},
        {"question": "Does it give a clear enquiry route?", "values": {"UDR Properties": "Pricing, FAQs, booking and contact routes observed", "Why Bother": "Not captured in pages reviewed", "Silver Star": "Not captured in pages reviewed", "Stellar": "Not captured in pages reviewed"}},
    ],
    "confidence_definition": "Confidence describes how strongly the available evidence supports the observed finding. It does not estimate the chance that an action will improve AI visibility.",
    "executive_summary": {
        "headline": "UDR appeared in 17 of the 72 answers after its trading-name variants were combined.",
        "summary": (
            "All 72 search-grounded answers were valid. UDR appeared under both UDR Properties and "
            "UDR Cleaning, while several local businesses appeared more often."
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
                "The 20-page review found useful service information and structured business data."
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
        {
            "strength_id": "strength_customer_journey",
            "title": "Easy ways to take the next step",
            "body": (
                "Pricing information, FAQs, booking routes and contact options help customers "
                "move from research to an enquiry."
            ),
            "evidence_refs": ["website:target:audit", "website:target:pages"],
        },
    ],
    "strengths_note": (
        "UDR is not starting from scratch. The report focuses on making a good foundation more "
        "specific to the work the business wants to win."
    ),
    "owner_competitors": [
        {"owner_name": "Daisy Fresh", "google_place_id": None, "business_name": "Daisyfresh Cleaning Services", "match_status": "matched", "recommendations": 13, "visibility_status": "Recommended 13 times; exact identity needs confirmation"},
        {"owner_name": "SEB Services", "google_place_id": "ChIJaUDAAKGFdUgRIgXR6nQD4f0", "business_name": "Seb-services Ltd", "match_status": "matched", "recommendations": 0, "visibility_status": "Not recommended in this benchmark"},
        {"owner_name": "Diamond Cleaning", "google_place_id": "ChIJ_Vo5lsSFdUgRGQOJqg1tRz8", "business_name": "Diamond Cleaning", "match_status": "matched", "recommendations": 2, "visibility_status": "Recommended 2 times across two name variants"},
        {"owner_name": "Why Bother Cleaning", "google_place_id": COHORT[0]["google_place_id"], "business_name": COHORT[0]["business_name"], "match_status": "matched", "recommendations": 21, "visibility_status": "Recommended 21 times"},
        {"owner_name": "Stellar End of Tenancy", "google_place_id": COHORT[2]["google_place_id"], "business_name": COHORT[2]["business_name"], "match_status": "matched", "recommendations": 13, "visibility_status": "Recommended 13 times across related Stellar names"},
    ],
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
    ],
    "gaps": [
        {
            "gap_id": "gap_visibility",
            "title": "Turn a broad cleaning offer into clear reasons to recommend UDR",
            "observed": "UDR appeared in 17 of the 72 valid answers after UDR Properties and UDR Cleaning were treated as one business.",
            "comparison": (
                "Why Bother was the strongest verified local result, while Silver Star and Stellar "
                "also appeared across the priority cleaning questions."
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
                "priority services."
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
            "title": "Investigate relevant recognition beyond UDR's own website",
            "observed": (
                "UDR has 78 usable reviews and strong examples, but this report did not yet assess which "
                "relevant external profiles or publications are missing or weaker."
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
            "business_name": "Why Bother Cleaning we'll do it for you",
            "hypothesis": (
                "Its visibility across all three assistants coincides with a clearly local cleaning "
                "identity and a verified Brighton presence."
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
            "business_name": "Stellar End of Tenancy Cleaning Brighton",
            "hypothesis": (
                "Its Claude and Gemini visibility coincides with a highly specific end-of-tenancy proposition "
                "and a verified Hove presence."
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
            "deliverable": "A one-page identity decision and a consistent name, address, service description and contact block.",
            "owner": "UDR owner",
            "effort": "1-2 hours to agree and check the public details",
            "completion_check": "The website, Google profile and selected directories show the same relationship between UDR Properties and UDR Cleaning.",
            "evidence_refs": ["gap:gap_brand_identity", "website:target:audit"],
        },
        {
            "action_id": "action_service_pages",
            "title": "Start with one highest-value service page",
            "category": "Priority services",
            "steps": (
                "Create a Brighton page for each of the six priority services. Explain who it is for, "
                "what is included, how it works, where it is available and how to request a quote."
            ),
            "intended_improvement": "Specific first-party evidence for every customer question tested.",
            "timing": "Weeks 1-6",
            "deliverable": "One improved or newly created Brighton page for the highest-value service, with scope, location, proof and enquiry route.",
            "owner": "UDR owner with web partner",
            "effort": "Half-day review, then 1-2 days to improve or create the page",
            "completion_check": "A customer can tell who the service is for, what is included, where it is available and how to enquire.",
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
            "deliverable": "One short case study for an office, landlord or property manager.",
            "owner": "UDR owner or account lead",
            "effort": "1-2 hours to gather evidence and permission, plus a short write-up",
            "completion_check": "The published case study names the need, service, location, result and supporting customer evidence where permitted.",
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
        "UDR appeared across OpenAI, Claude and Gemini after its UDR Properties and UDR Cleaning names were combined. "
        "The wider recommendation patterns varied substantially by assistant and question."
    ),
    "matrix_dimensions": [
        {"label": "Recommendations in the benchmark", "evidence_refs": ["market:target", "market:brighton", "market:silver", "market:cleanology"], "values": {"UDR Properties": "17", "Why Bother": "21", "Silver Star": "11", "Stellar": "13"}},
        {"label": "AI assistants recommending them", "evidence_refs": ["market:target", "market:brighton", "market:silver", "market:cleanology"], "values": {"UDR Properties": "3 / 3", "Why Bother": "3 / 3", "Silver Star": "3 / 3", "Stellar": "2 / 3"}},
        {"label": "Questions they appeared for", "evidence_refs": ["market:target", "market:brighton", "market:silver", "market:cleanology"], "values": {"UDR Properties": "3 / 8", "Why Bother": "3 / 8", "Silver Star": "2 / 8", "Stellar": "3 / 8"}},
        {"label": "Website pages reviewed", "evidence_refs": ["website:target:audit", "website:brighton:audit", "website:silver:audit", "website:cleanology:audit"], "values": {"UDR Properties": "20 pages", "Why Bother": "20 pages", "Silver Star": "10 pages", "Stellar": "20 pages"}},
        {"label": "Clear business details for digital systems", "evidence_refs": ["website:target:audit", "website:brighton:audit", "website:silver:audit", "website:cleanology:audit"], "values": {"UDR Properties": "Local business data detected", "Why Bother": "Compared where available", "Silver Star": "Local schema not detected", "Stellar": "Compared where available"}},
        {"label": "Relevant service evidence", "evidence_refs": ["website:target:pages", "website:brighton:pages", "website:silver:pages", "website:cleanology:pages"], "values": {"UDR Properties": "General services and deep washroom pages", "Why Bother": "Local cleaning proposition", "Silver Star": "Commercial, lettings and specialist pages", "Stellar": "End-of-tenancy proposition"}},
        {"label": "Customer reviews analysed", "evidence_refs": ["reviews:target:set", "reviews:brighton:set", "reviews:silver:set", "reviews:cleanology:set"], "values": {"UDR Properties": "78", "Why Bother": "Not available", "Silver Star": "53", "Stellar": "Not available"}},
    ],
    "matrix_note": (
        "The comparison set comes from businesses actually named in the AI answers and with sufficient "
        "evidence for useful analysis. Website and review differences are comparisons, not proven causes."
    ),
    "roadmap": {
        "phases": [
            {"timing": "Weeks 1-2", "title": "Clarify the brand and offer", "body": "Align UDR's public identity and map the six priority service journeys."},
            {"timing": "Weeks 2-8", "title": "Publish services and proof", "body": "Build useful service pages with clear enquiry routes and connect them to real commercial case studies."},
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


OWNER_REPORT = {
    "benchmark_mode": "search_grounded",
    "recommendation_validation": "All 17 counted UDR appearances were checked against numbered business entries in the saved answers.",
    "evidence_index": "UDR Properties - V2 - Evidence Index.html",
    "priority_context": "The owner wants UDR to be known for work beyond Airbnb changeovers: commercial, office, end-of-tenancy, carpet, upholstery and laundry services, serving Brighton and Hove, including landlords and property managers.",
    "implication": "The visibility found in this test is concentrated in Airbnb cleaning, not the wider work the owner wants to win. UDR already describes a wider range of services online. The next step is to check whether the existing pages answer the practical questions those customers ask.",
    "coverage_note": "Three questions cover Airbnb-related needs, while each of the other five tested services has one. Laundry has no dedicated question. Brighton is named in the questions; Hove and the wider service area were not separately tested. One question explicitly covers landlords; no separate office-buyer or property-manager segment was measured.",
    "services": [
        {"name": "Commercial cleaning", "questions": [1]},
        {"name": "Office cleaning", "questions": [2]},
        {"name": "End-of-tenancy cleaning", "questions": [3]},
        {"name": "Carpet cleaning", "questions": [4]},
        {"name": "Upholstery cleaning", "questions": [5]},
        {"name": "Airbnb cleaning / changeovers", "questions": [6, 7, 8]},
        {"name": "Laundry", "questions": []},
    ],
    "sources": [
        {"ref": "W1", "kind": "website", "record_id": "eb721af5-7f9f-40e1-af9e-5bb06ff02b9f", "title": "UDR homepage", "excerpt": "UDR Properties Limited | Cleaning Services Hove & Brighton and Hove", "additional_excerpts": ["We’ve been proudly serving the local community since 2018"]},
        {"ref": "W2", "kind": "website", "record_id": "9b698bc1-9056-499c-9790-33476f91bd32", "title": "UDR services overview", "excerpt": "Office Cleaning: Daily, weekly, or custom out-of-hours cleaning schedules to prevent operational disruption.", "additional_excerpts": ["Est. 2017 • Hove & Brighton"]},
        {"ref": "W3", "kind": "website", "record_id": "b177bba5-b7a4-4eb9-9910-191b89de9f8c", "title": "Why Bother homepage", "excerpt": ""},
        {"ref": "W4", "kind": "website", "record_id": "54961702-633f-43ad-ba23-5706f6a5bfb9", "title": "Silver Star commercial-cleaning page", "excerpt": ""},
        {"ref": "W5", "kind": "website", "record_id": "bdf2dda0-8a73-45c4-abb8-5397869bed1c", "title": "Stellar homepage", "excerpt": ""},
        {"ref": "R1", "kind": "review", "record_id": "Ci9DQUlRQUNvZENodHljRjlvT2sxSlgybFhkVTR0UWpsTGRFVm1Xazk0V1d0dGFGRRAB", "title": "UDR carpet and upholstery review", "excerpt": "My go to for carpet and upholstery cleans, great service always"},
        {"ref": "R2", "kind": "review", "record_id": "Ci9DQUlRQUNvZENodHljRjlvT2pGSFF6VTRYMXB2YUhabFZrVXpTRU01VURSVFpuYxAB", "title": "UDR end-of-tenancy review", "excerpt": "UDR team did a great job of End of Tenancy cleaning for me. Definitely recommend."},
        {"ref": "R3", "kind": "review", "record_id": "Ci9DQUlRQUNvZENodHljRjlvT2kxalNEZElRVzEyVUcxaU5rNDVTRkI0TW1GS1pYYxAB", "title": "UDR service review", "excerpt": "Very efficient and affordable. Would definitely use again"},
        {"ref": "R4", "kind": "review", "record_id": "ChZDSUhNMG9nS0VJQ0FnSURZbm9YclF3EAE", "title": "Silver Star historical carpet review (2019)", "excerpt": "Had the house carpets cleaned last week & very happy with the results. The lads were friendly, courteous & did a great job. Would thoroughly recommend."},
    ],
    "strengths": [
        {"title": "A clear local offer already exists", "body": "The saved homepage links UDR Properties Limited with cleaning in Hove and Brighton. The services overview describes office, tenancy, carpet, upholstery, Airbnb and laundry work. This is a foundation to improve, not a blank sheet.", "refs": ["W1", "W2"]},
        {"title": "Customer proof extends beyond Airbnb", "body": "The collected reviews include explicit carpet, upholstery and end-of-tenancy experiences. They support those service claims even though UDR did not appear for those questions in this test.", "refs": ["R1", "R2", "Q3", "Q4", "Q5"]},
        {"title": "There is a direct next step for customers", "body": "The services overview offers a free quote, a telephone number and an online enquiry route. Keep these easy to find when improving service information.", "refs": ["W2"]},
    ],
    "gaps": [
        {"title": "The website sample cannot settle the service-page question", "body": "Of 20 saved page records, two are homepage variants, one is the services overview and 17 concern washroom services. The overview already names the priority services, but their dedicated page content was not captured. This is a research gap, not proof that those pages are missing.", "refs": ["INVENTORY", "W2"]},
    ],
    "comparisons": [
        {"place_id": COHORT[0]["google_place_id"], "title": "Why Bother: office and commercial clarity", "body": "Its saved homepage foregrounds office, commercial and deep cleaning in Brighton. This is a useful example of making the work offered immediately clear; UDR's overview already describes office schedules too.", "refs": ["W3", "W2", "Q1", "Q2"]},
        {"place_id": COHORT[1]["google_place_id"], "title": "Silver Star: relevant customer proof", "body": "Its commercial-cleaning page includes an office-cleaning testimonial. UDR has useful service-specific reviews of its own. Check which proof can be placed beside the service it describes.", "refs": ["W4", "R1", "R2"]},
        {"place_id": COHORT[2]["google_place_id"], "title": "Stellar: tenancy is a relevant comparison", "body": "Its saved homepage describes tenancy and office cleaning. For a landlord, compare how clearly each business explains the cleaning scope and next steps—not which company is better overall.", "refs": ["W5", "Q3"]},
    ],
    "actions": [
        {"title": "1. Check one priority service before commissioning new pages", "need": "Customers considering non-Airbnb work need to understand what UDR will do, where and how to enquire.", "observation": "UDR was absent for Q1–Q5, but the services overview already describes those services. Their dedicated pages were not captured in the washroom-heavy sample. A content gap has not yet been established.", "deliverable": "An inventory of existing service-page addresses, then one annotated page brief for the service the owner selects. Check scope, customer type, area, practical booking questions and enquiry steps. Improve an existing page first if suitable.", "supplier": "Owner: choose the first service and confirm scope, exclusions, areas and availability. No commercial ranking has been agreed.", "implementer": "Audit reviewer maps the pages; website manager implements only the approved changes.", "effort": "Estimate: 2–3 hours to investigate and brief one service; allow 2–4 more hours for a modest page update if needed.", "dependencies": "Owner's choice; current page addresses and access; assessment of the complete page, not just a saved excerpt.", "check": "Owner approves the factual brief. The chosen page answers the agreed customer questions, is linked from Services, and its enquiry route works on mobile.", "refs": ["Q1", "Q2", "Q3", "Q4", "Q5", "W2", "INVENTORY"]},
        {"title": "2. Put existing customer proof beside the service it supports", "need": "A landlord or carpet-cleaning customer needs relevant reassurance, not only Airbnb testimonials.", "observation": "The collected review set contains specific tenancy, carpet and upholstery feedback. The saved overview describes those services, but this limited sample does not establish how well that proof is presented on each dedicated page.", "deliverable": "For the first approved service, prepare one small proof block using a verified, relevant review with its source and date. If the page already has good proof, record that and avoid duplicating it. A case study is optional, not a prerequisite.", "supplier": "Owner: verify the job context and approve permissions and wording. Never invent a customer story or service outcome.", "implementer": "Website manager or copywriter, following the reviewed brief.", "effort": "Estimate: 1–2 hours to check and prepare proof; 1–2 hours to publish and test a small block, if needed.", "dependencies": "Action 1 selects the page; source attribution and permission requirements must be checked before republication.", "check": "Published wording matches its source exactly, relates to that service, links to the source where appropriate, and contains no unsupported claims.", "refs": ["R1", "R2", "W2", "INVENTORY"]},
        {"title": "3. Investigate and agree the public business facts", "need": "Customers should understand that UDR Cleaning and UDR Properties refer to the same business and receive consistent factual information.", "observation": "The cleaning-domain homepage already uses UDR Properties Limited, so different names do not justify a rebrand. Saved pages refer to both 2017 and 2018 for the business's history; these may describe different milestones and need owner confirmation.", "deliverable": "A short owner-approved facts sheet: trading name, legal name and their relationship, contact details, service areas and an explanation of the establishment dates. List only verified inconsistencies for correction.", "supplier": "Owner: confirm the legal/trading relationship and what each date means.", "implementer": "Owner and website manager; profile administrator only if a separately checked profile needs correction.", "effort": "Estimate: 1 hour to agree the facts; 1–2 hours for small approved corrections. Wider profile work is not yet scoped.", "dependencies": "Owner confirmation and access to the exact affected pages. Business profiles were not independently compared in this historical evidence set.", "check": "Each retained date has a clear meaning and the agreed name relationship is understandable. Do not rename the business or change profiles simply to make strings identical.", "refs": ["W1", "W2"]},
    ],
}

CONFIG: dict[str, Any] = {
    "report_format": "accessible_owner_services_v4",
    "owner_report": OWNER_REPORT,
    "run_id": RUN_ID,
    "target_google_place_id": TARGET_PLACE_ID,
    "target_business_name": "UDR Properties",
    "category": "Professional cleaning services",
    "location": "Brighton",
    "primary_group": "cleaning_services",
    "review_profile": "cleaning_services",
    "expected_responses": 72,
    "expected_eligible_slots": None,
    "baseline_validation_status": "reviewed",
    "verification_method_version": "search_grounded_owner_services_alias_reconciliation_v2",
    "target_explicit_terms": ("udr properties", "udr cleaning", "udr properties limited"),
    "target_indirect_terms": (),
    "response_verification_note": "Complete UDR owner-services benchmark reconciled against the target business identity.",
    "verification_statement": "All 72 responses completed. UDR Properties and UDR Cleaning references were reconciled as one business.",
    "slot_adjudications": {
        "UDR Cleaning": {"google_place_id": TARGET_PLACE_ID, "business_name": "UDR Properties", "resolution_method": "analyst_confirmed_trading_name"},
        "UDR Cleaning (UDR Properties Limited)": {"google_place_id": TARGET_PLACE_ID, "business_name": "UDR Properties", "resolution_method": "analyst_confirmed_trading_name"},
        "UDR Cleaning / UDR Properties": {"google_place_id": TARGET_PLACE_ID, "business_name": "UDR Properties", "resolution_method": "analyst_confirmed_trading_name"},
        "Stellar Airbnb Cleaning": {"google_place_id": COHORT[2]["google_place_id"], "business_name": COHORT[2]["business_name"], "resolution_method": "analyst_confirmed_brand_variant"},
        "Stellar Airbnb Cleaning Services": {"google_place_id": COHORT[2]["google_place_id"], "business_name": COHORT[2]["business_name"], "resolution_method": "analyst_confirmed_brand_variant"},
        "Stellar AirBnb Cleaning Services": {"google_place_id": COHORT[2]["google_place_id"], "business_name": COHORT[2]["business_name"], "resolution_method": "analyst_confirmed_brand_variant"},
        "Stellar Cleaning": {"google_place_id": COHORT[2]["google_place_id"], "business_name": COHORT[2]["business_name"], "resolution_method": "analyst_confirmed_brand_variant"},
    },
    "non_business_prefixes": tuple(NON_BUSINESS_PREFIXES) + (
        "checkatrade", "trustpilot", "facebook", "facebook local", "google reviews",
        "local directories", "ask your letting agent", "yell",
    ),
    "cohort": COHORT,
    "website_audits": WEBSITE_AUDITS,
    "review_sets": REVIEW_SETS,
    "analyst_decisions": ANALYST_DECISIONS,
    "matrix_businesses": ("UDR Properties", "Why Bother", "Silver Star", "Stellar"),
    "matrix_business_place_ids": {
        "UDR Properties": TARGET_PLACE_ID,
        "Why Bother": COHORT[0]["google_place_id"],
        "Silver Star": COHORT[1]["google_place_id"],
        "Stellar": COHORT[2]["google_place_id"],
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
        "The detailed comparison uses three locally relevant businesses from the AI answers. Missing comparison-review "
        "evidence is shown as unavailable rather than treated as poor performance."
    ),
    "gap_caveat": "Observed differences are evidence-backed opportunities, not proven causes of AI recommendations.",
    "action_caveat": "The actions strengthen public evidence; no AI visibility improvement is guaranteed.",
    "methodology_validation": (
        "72/72 valid responses: 24 per AI assistant",
        "Eight owner-priority cleaning questions, each asked three times per assistant",
        "UDR Properties and UDR Cleaning references reconciled as one business",
        "Owner-nominated competitors shown separately from the AI-discovered comparison set",
        "Comparison businesses selected from locally relevant measured AI responses",
    ),
    "methodology_limitations": (
        "This run used the platform's search-grounded benchmark mode.",
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
