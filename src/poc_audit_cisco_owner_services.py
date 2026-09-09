from __future__ import annotations

from typing import Any

from sqlalchemy.engine import Engine

from src.poc_audit_assembler import assemble_poc_audit_payload
from src.poc_audit_cisco_assembler import (
    COHORT as LEGACY_COHORT,
    NON_BUSINESS_PREFIXES,
    TARGET_PLACE_ID,
    TARGET_WEBSITE_AUDIT_RUN_ID,
)


RUN_ID = "80cf853d-4e7c-4f7c-a446-bf7f40d6dddf"
REVIEW_BATCH_ID = "b6dac5f1-2e01-4814-bf98-b6e4c75cb3ee"
DECISION_VERSION = "ciscos_karma_owner_services_review_draft_v1"


COHORT = tuple(
    {
        **item,
        "selection_reason": reason,
    }
    for item, reason in zip(
        LEGACY_COHORT,
        (
            "An owner-nominated competitor was one of the most frequently recommended businesses and appeared through OpenAI and Gemini across seven service questions.",
            "An owner-nominated competitor was one of the most frequently recommended businesses, appeared through OpenAI and Gemini, and covered all eight service questions.",
            "An owner-nominated competitor appeared for every service question, although all of those recommendations came from Gemini.",
        ),
    )
)

WEBSITE_AUDITS = (
    {
        "google_place_id": TARGET_PLACE_ID,
        "business_name": "Cisco's Karma",
        "website_audit_run_id": TARGET_WEBSITE_AUDIT_RUN_ID,
    },
    *COHORT,
)

REVIEW_SETS = (
    {
        "google_place_id": TARGET_PLACE_ID,
        "business_name": "Cisco's Karma",
        "record_count": 63,
        "import_batch_id": REVIEW_BATCH_ID,
    },
    {
        "google_place_id": COHORT[0]["google_place_id"],
        "business_name": COHORT[0]["business_name"],
        "record_count": 100,
        "import_batch_id": REVIEW_BATCH_ID,
    },
    {
        "google_place_id": COHORT[1]["google_place_id"],
        "business_name": COHORT[1]["business_name"],
        "record_count": 100,
        "import_batch_id": REVIEW_BATCH_ID,
    },
    {
        "google_place_id": COHORT[2]["google_place_id"],
        "business_name": COHORT[2]["business_name"],
        "status": "exception",
        "exception": {
            "exception_code": "approved_profile_returned_no_review_result",
            "description": (
                "The approved Simon Webster Google Place ID returned no review "
                "result through the approved collection mechanism."
            ),
            "comparison_treatment": (
                "Review evidence unavailable; excluded from review comparisons "
                "and not treated as zero reviews."
            ),
            "approved_stage": "Original Cisco Stage 3",
        },
    },
)


ANALYST_DECISIONS: dict[str, Any] = {
    "version": DECISION_VERSION,
    "status": "review_draft",
    "provenance": (
        "Owner-priority services and named competitors supplied in September 2026; "
        "new model-memory benchmark reconciled against the original Cisco website "
        "and review evidence. Conclusions remain subject to operator approval."
    ),
    "introduction": {
        "owner_priority": (
            "Cisco's Karma wants to be more visible when people look for a Brighton "
            "hairdresser or salon, especially for highlights, hair up, wedding hair, "
            "gents' hair, balayage and colour."
        ),
        "method_steps": [
            {
                "title": "We turned your priorities into customer questions",
                "body": (
                    "We used eight realistic recommendation questions based on the "
                    "services and searches the owner said matter most."
                ),
            },
            {
                "title": "We tested visibility across three AI platforms",
                "body": (
                    "We used the OpenAI, Anthropic and Google APIs three times per question, "
                    "then checked every completed answer and the businesses it named."
                ),
            },
            {
                "title": "We compared the strongest visible businesses",
                "body": (
                    "We reviewed their websites and customer reviews alongside yours "
                    "to identify existing strengths and practical opportunities."
                ),
            },
        ],
        "scope_note": (
            "This is a snapshot of how the three platforms answered this set of questions "
            "on the audit date. It is designed to guide a useful conversation, not to claim "
            "that any single website or review change controls an AI recommendation."
        ),
    },
    "executive_summary": {
        "headline": (
            "Cisco's Karma was not recommended in 72 tests of eight priority services."
        ),
        "summary": (
            "All 72 responses were valid. The three principal comparison businesses "
            "appeared repeatedly, while Toni & Guy and Electric had lower visibility "
            "and Mooch did not appear in the measured results."
        ),
        "strengths": [],
        "action_statement": (
            "Turn existing colour, balayage, bridal and styling material into clearer "
            "Brighton service evidence supported by expertise and customer proof."
        ),
        "non_causality": (
            "These actions strengthen public evidence; they do not guarantee a change "
            "in any AI assistant's recommendations."
        ),
    },
    "strengths": [
        {
            "strength_id": "strength_priority_services_present",
            "title": "Priority services are covered",
            "body": (
                "The site already covers colour, balayage, highlights, hair up, "
                "wedding hair, team and gallery content."
            ),
            "evidence_refs": ["website:target:pages"],
        },
        {
            "strength_id": "strength_site_presence",
            "title": "A credible owned-site footprint",
            "body": "The completed adaptive audit preserved a crawlable 10-page target footprint.",
            "evidence_refs": ["website:target:audit"],
        },
        {
            "strength_id": "strength_customer_evidence",
            "title": "Positive customer evidence is available",
            "body": "The exact 63-review set provides customer evidence rather than an absence of proof.",
            "evidence_refs": ["reviews:target:set", "diagnostic:review_benchmark"],
        },
    ],
    "strengths_note": (
        "The report treats existing service material as a foundation to clarify and deepen, not as absent."
    ),
    "review_quotes": [
        {
            "review_id": "Ci9DQUlRQUNvZENodHljRjlvT2tZNU1WWkdTM0JzUWpFNFNXOXRlbk56ZUZoaFpVRRAB",
            "google_place_id": TARGET_PLACE_ID,
            "business_name": "Cisco's Karma",
            "quote": "Wouldn't go anywhere else for my hair in Brighton, Alex is brilliant and I love the cut and colour every time",
            "takeaway": "Strong evidence for Brighton, cut and colour in one customer account.",
        },
        {
            "review_id": "Ci9DQUlRQUNvZENodHljRjlvT25kNGRrZG9aV0V4VkhGdldYSlpSSFV6WjFKV2VtYxAB",
            "google_place_id": TARGET_PLACE_ID,
            "business_name": "Cisco's Karma",
            "quote": "Alex and his team are amazing. I have been having my hair styled there for years and how attention to detail and his knowledge of adapting my style over the years has been great.",
            "takeaway": "Customers already describe trusted expertise and a long-term relationship.",
        },
        {
            "review_id": "ChZDSUhNMG9nS0VJQ0FnSUNuNDlybVdBEAE",
            "google_place_id": TARGET_PLACE_ID,
            "business_name": "Cisco's Karma",
            "quote": "Seldom have I been this happy with my hair than when I went to Ciscos Karma. Such a cosy place and friendly staff! Keeley truly did a great job and really listened to what I wanted. I will definitely come back!",
            "takeaway": "The personal atmosphere and careful listening are distinctive strengths.",
        },
        {
            "review_id": "Ci9DQUlRQUNvZENodHljRjlvT21kWmRXSTRSelZYVGxsRVNsVkNVMlZsWjAxc1dFRRAB",
            "google_place_id": COHORT[0]["google_place_id"],
            "business_name": "Cuttlefish Eco Salons - Brighton",
            "quote": "Another fab haircut by Jasmine at Cuttlefish. A great experience from start to finish. Highly recommend for a 5 star curly haircut",
            "takeaway": "A customer names a specific specialist service: curly hair.",
        },
        {
            "review_id": "Ci9DQUlRQUNvZENodHljRjlvT214SVIxSkZjelJ2VWtWUlRtaDRYMUkzYlc1U1oxRRAB",
            "google_place_id": COHORT[1]["google_place_id"],
            "business_name": "Trevor Sorbie Brighton",
            "quote": "I got half a head of highlights and Kitty did such an amazing job. All the team were so lovely, constantly offering refreshments and making you feel so welcome and comfortable! Will definitely be back in the future.",
            "takeaway": "A specific service is connected to a named stylist and the salon experience.",
        },
    ],
    "gaps": [
        {
            "gap_id": "gap_service_discovery",
            "title": "Make every priority service easy to find and understand",
            "observed": (
                "Cisco's Karma received no recommendation across the 72 valid "
                "responses and eight priority-service questions."
            ),
            "comparison": (
                "Trevor Sorbie and Simon Webster appeared across all eight questions; "
                "Cuttlefish appeared across seven."
            ),
            "relevance": (
                "Dedicated, connected service information can state who each service is for, "
                "how it is delivered, where it is available and what supports the expertise claim."
            ),
            "confidence": "High",
            "evidence_refs": ["market:target", "market:cuttlefish", "market:trevor", "market:simon", "website:target:pages"],
        },
        {
            "gap_id": "gap_entity_schema",
            "title": "Make your business and location details clear and consistent",
            "observed": "No LocalBusiness or HairSalon structured information was detected in Cisco's Karma website review.",
            "comparison": "The visible businesses provide useful entity and location comparisons.",
            "relevance": "Consistent public identity helps digital systems associate the salon, Brighton location and services.",
            "confidence": "High",
            "evidence_refs": ["website:target:audit", "diagnostic:entity_matrix"],
        },
        {
            "gap_id": "gap_service_proof",
            "title": "Show who delivers each service and the results customers can expect",
            "observed": (
                "The site mentions relevant services, but does not yet present them "
                "as a consistent set of decision pages."
            ),
            "comparison": (
                "The comparison sites expose broader combinations of service menus, colour content, "
                "team expertise, FAQs and supporting editorial material."
            ),
            "relevance": "Specific proof makes the proposition clearer to prospective customers and digital systems.",
            "confidence": "Moderate",
            "evidence_refs": ["website:target:pages", "website:cuttlefish:pages", "website:trevor:pages", "website:simon:pages"],
        },
        {
            "gap_id": "gap_review_scale",
            "title": "Build more current, service-specific customer reviews",
            "observed": "The exact Cisco's Karma evidence set contained 63 reviews.",
            "comparison": "Cuttlefish and Trevor Sorbie each contributed 100 analysed reviews.",
            "relevance": (
                "A consistent review programme can increase current, independent descriptions "
                "of the services and experiences the owner wants associated with the salon."
            ),
            "confidence": "High",
            "evidence_refs": ["reviews:target:set", "reviews:cuttlefish:set", "reviews:trevor:set"],
        },
    ],
    "provider_hypotheses": [
        {
            "business_name": "Cuttlefish Eco Salons - Brighton",
            "hypothesis": "Its OpenAI and Gemini visibility coincides with broad service coverage and a distinctive local proposition.",
            "evidence_refs": ["market:cuttlefish", "website:cuttlefish:pages"],
        },
        {
            "business_name": "Trevor Sorbie Brighton",
            "hypothesis": "Its OpenAI and Gemini visibility coincides with broad service coverage and a deep public content footprint.",
            "evidence_refs": ["market:trevor", "website:trevor:pages"],
        },
        {
            "business_name": "Simon Webster Hair",
            "hypothesis": "Its Gemini-only concentration is an observed provider pattern; no undocumented mechanism is inferred.",
            "evidence_refs": ["market:simon", "website:simon:pages"],
        },
    ],
    "actions": [
        {
            "action_id": "action_service_hubs",
            "title": "Build a clear page for each owner-priority service",
            "category": "Service discovery",
            "steps": (
                "Create or strengthen connected Brighton pages for highlights, hair up, wedding hair, "
                "gents' hair, balayage and colour, with consultation detail, suitability, process, maintenance and FAQs."
            ),
            "intended_improvement": "Clearer first-party evidence for each customer need measured in the benchmark.",
            "timing": "Weeks 1-5",
            "evidence_refs": ["gap:gap_service_discovery", "website:target:pages"],
        },
        {
            "action_id": "action_service_proof",
            "title": "Attach stylist expertise and real proof to each service",
            "category": "Expertise and proof",
            "steps": (
                "Connect named stylists, relevant experience, consultation approach, portfolio examples, "
                "before-and-after work and appropriate testimonials to the priority-service pages."
            ),
            "intended_improvement": "A more credible and distinctive explanation of why the salon is suitable for each service.",
            "timing": "Weeks 2-6",
            "evidence_refs": ["gap:gap_service_proof", "reviews:target:set"],
        },
        {
            "action_id": "action_entity_schema",
            "title": "Make your business details clear and consistent online",
            "category": "Entity and structured data",
            "steps": (
                "Use the same official name, address, phone number and Brighton wording everywhere you control, "
                "then add accurate behind-the-scenes business information to the website using HairSalon/LocalBusiness structured data."
            ),
            "intended_improvement": "It becomes easier for customers and digital platforms to connect the salon, its Brighton location and its services.",
            "timing": "Weeks 1-3",
            "evidence_refs": ["gap:gap_entity_schema", "website:target:audit"],
        },
        {
            "action_id": "action_review_programme",
            "title": "Develop service-specific customer corroboration",
            "category": "Reviews and customer evidence",
            "steps": (
                "Use a compliant, non-incentivised review request process and monitor how customers naturally "
                "describe colour, balayage, highlights, styling, wedding and gents' services."
            ),
            "intended_improvement": "A larger, current body of independent evidence around priority services.",
            "timing": "Weeks 1-8",
            "evidence_refs": ["gap:gap_review_scale", "reviews:target:set"],
        },
        {
            "action_id": "action_internal_links",
            "title": "Create a coherent Brighton service journey",
            "category": "Website navigation",
            "steps": (
                "Link the homepage, services, team, gallery, bridal and contact journeys using descriptive service language "
                "and clear booking or consultation next steps."
            ),
            "intended_improvement": "Better-connected evidence and easier customer journeys across the priority topics.",
            "timing": "Weeks 3-6",
            "evidence_refs": ["gap:gap_service_discovery", "gap:gap_service_proof"],
        },
    ],
    "priority_action_ids": ["action_service_hubs", "action_service_proof", "action_entity_schema"],
    "provider_observation": (
        "Cisco's Karma received no recommendation from OpenAI, Claude or Gemini. "
        "Visibility among owner-nominated competitors varied materially by provider."
    ),
    "matrix_dimensions": [
        {"label": "AI recommendation result", "evidence_refs": ["market:target", "market:cuttlefish", "market:trevor", "market:simon"], "values": {"Cisco's Karma": "0.0% | not ranked", "Cuttlefish": "10.9% | joint leader", "Trevor Sorbie": "10.9% | joint leader", "Simon Webster": "8.1%"}},
        {"label": "AI assistants recommending them", "evidence_refs": ["market:target", "market:cuttlefish", "market:trevor", "market:simon"], "values": {"Cisco's Karma": "0 / 3", "Cuttlefish": "2 / 3", "Trevor Sorbie": "2 / 3", "Simon Webster": "1 / 3"}},
        {"label": "Service questions they appeared for", "evidence_refs": ["market:target", "market:cuttlefish", "market:trevor", "market:simon"], "values": {"Cisco's Karma": "0 / 8", "Cuttlefish": "7 / 8", "Trevor Sorbie": "8 / 8", "Simon Webster": "8 / 8"}},
        {"label": "Website pages reviewed", "evidence_refs": ["website:target:audit", "website:cuttlefish:audit", "website:trevor:audit", "website:simon:audit"], "values": {"Cisco's Karma": "10 pages", "Cuttlefish": "10 pages", "Trevor Sorbie": "20 pages", "Simon Webster": "12 pages"}},
        {"label": "Clear business details for digital systems", "evidence_refs": ["website:target:audit", "website:cuttlefish:audit", "website:trevor:audit", "website:simon:audit"], "values": {"Cisco's Karma": "Local schema not detected", "Cuttlefish": "Local schema comparison", "Trevor Sorbie": "Established brand entity", "Simon Webster": "Local entity comparison"}},
        {"label": "Priority-service evidence", "evidence_refs": ["website:target:pages", "website:cuttlefish:pages", "website:trevor:pages", "website:simon:pages"], "values": {"Cisco's Karma": "Colour, balayage, bridal and gallery foundations", "Cuttlefish": "Colour, highlights, balayage and services", "Trevor Sorbie": "Deep colour, balayage and service content", "Simon Webster": "Colour, team, FAQ and service content"}},
        {"label": "Customer reviews analysed", "evidence_refs": ["reviews:target:set", "reviews:cuttlefish:set", "reviews:trevor:set", "reviews:simon:set"], "values": {"Cisco's Karma": "63", "Cuttlefish": "100", "Trevor Sorbie": "100", "Simon Webster": "Unavailable; excluded"}},
    ],
    "matrix_note": (
        "The AI evidence is from the September 2026 owner-services benchmark. Website and review evidence is reused "
        "from the original frozen audit and remains observational rather than causal."
    ),
    "roadmap": {
        "phases": [
            {"timing": "Weeks 1-2", "title": "Structure priority services", "body": "Map the six specific service journeys and their Brighton search language."},
            {"timing": "Weeks 2-6", "title": "Publish expertise and proof", "body": "Connect service detail to stylists, portfolios, FAQs and consultation routes."},
            {"timing": "Weeks 1-8", "title": "Strengthen corroboration", "body": "Align entity data and maintain a compliant review programme."},
            {"timing": "Weeks 8-12", "title": "Remeasure", "body": "Repeat the same prompts and disclose any model-version changes."},
        ],
        "options": [
            {"title": "Implement internally", "body": "Use the evidence-backed action plan with existing web and marketing partners."},
            {"title": "Supported implementation", "body": "Work collaboratively on content, technical changes and review operations."},
            {"title": "Implementation + remeasurement", "body": "Complete delivery, verification and a comparable follow-up benchmark."},
        ],
        "remeasurement_note": "Suggested follow-up: 8-12 weeks after meaningful implementation.",
    },
}

ANALYST_DECISIONS["executive_summary"]["strengths"] = ANALYST_DECISIONS["strengths"][:3]


def _adjudication(name: str, place_id: str, business_name: str) -> dict[str, str]:
    return {
        "google_place_id": place_id,
        "business_name": business_name,
        "resolution_method": "owner_services_review_verified_alias",
    }


SLOT_ADJUDICATIONS = {
    name: _adjudication(name, COHORT[0]["google_place_id"], COHORT[0]["business_name"])
    for name in (
        "Cuttlefish Eco Salon", "Cuttlefish Eco Salons", "Cuttlefish Hair",
        "Cuttlefish Eco Salon, Brighton", "Cuttlefish Hair Studio",
        "Cuttlefish Eco Hair Salon", "Cuttlefish Eco Salons Brighton",
        "Cuttlefish Hair and Beauty", "Cuttlefish Haircare",
    )
}
SLOT_ADJUDICATIONS.update({
    name: _adjudication(name, "ChIJ-fdDoguFdUgR8Gb1dgNKVEw", "Electric Hairdressing Brighton")
    for name in ("Electric Hair Brighton", "Electric Hair")
})


CONFIG: dict[str, Any] = {
    "report_format": "beta_accessible_v2",
    "run_id": RUN_ID,
    "target_google_place_id": TARGET_PLACE_ID,
    "target_business_name": "Cisco's Karma",
    "category": "Hair services",
    "location": "Brighton",
    "primary_group": "hair_services",
    "review_profile": "hair_services",
    "expected_responses": 72,
    "expected_eligible_slots": 271,
    "baseline_validation_status": "verified_zero",
    "verification_method_version": "owner_services_raw_response_reconciliation_v1",
    "target_explicit_terms": ("cisco's karma", "cisco’s karma", "ciscos karma", "cisco karma"),
    "target_indirect_terms": ("5 bartholomews", "east street arcade", "alex martinez", "adam lawton"),
    "response_verification_note": "Complete owner-services benchmark response reconciled against target identity terms.",
    "verification_statement": (
        "All 72 persisted responses completed. No explicit Cisco's Karma recommendation or credible indirect target reference was found."
    ),
    "slot_adjudications": SLOT_ADJUDICATIONS,
    "non_business_prefixes": NON_BUSINESS_PREFIXES,
    "cohort": COHORT,
    "website_audits": WEBSITE_AUDITS,
    "review_sets": REVIEW_SETS,
    "analyst_decisions": ANALYST_DECISIONS,
    "matrix_businesses": ("Cisco's Karma", "Cuttlefish", "Trevor Sorbie", "Simon Webster"),
    "matrix_business_place_ids": {"Cisco's Karma": TARGET_PLACE_ID, "Cuttlefish": COHORT[0]["google_place_id"], "Trevor Sorbie": COHORT[1]["google_place_id"], "Simon Webster": COHORT[2]["google_place_id"]},
    "market_note": (
        "Business Share of Recommendation uses 258 named-business recommendations from 72 valid responses. It is benchmark-specific, not commercial market share."
    ),
    "provider_caveat": (
        "The report describes what each assistant recommended. It does not claim to "
        "know how the platforms chose their answers."
    ),
    "cohort_note": (
        "The diagnostic cohort retains the three evidence-complete leaders from the original report. Toni & Guy, Electric and Mooch remain visible in the full owner-nominated competitor analysis and are not excluded from the measured market."
    ),
    "gap_caveat": "Observed differences are evidence-backed opportunities, not proven causes of AI recommendations.",
    "action_caveat": "The actions strengthen public evidence; no AI visibility improvement is guaranteed.",
    "methodology_validation": (
        "72/72 valid responses: 24 per AI assistant",
        "271 recommendation items reviewed: 258 named businesses and 13 non-business exclusions",
        "No target recommendation or credible indirect reference",
        "Cuttlefish and Electric aliases reconciled",
        "All owner-nominated competitors checked",
    ),
    "methodology_limitations": (
        "This is a model-memory benchmark, not a live web-search test.",
        "Results depend on the exact prompts, model identifiers and audit date.",
        "AI outputs may vary between repetitions and over time.",
        "Website and review evidence is reused from the original audit and retains its original collection dates.",
        "Website and review differences are observational, not causal.",
        "Business Share of Recommendation is not commercial market share.",
    ),
    "non_causality": "No website, identity or review difference is presented as a proven AI ranking factor or guaranteed cause of visibility.",
    "revision": {"snapshot_revision": 1, "supersedes_snapshot_id": None, "revision_reason": "Owner-priority services benchmark and review draft"},
    "evidence_registry": {
        "market:target": {"google_place_id": TARGET_PLACE_ID},
        "market:cuttlefish": {"google_place_id": COHORT[0]["google_place_id"]},
        "market:trevor": {"google_place_id": COHORT[1]["google_place_id"]},
        "market:simon": {"google_place_id": COHORT[2]["google_place_id"]},
        "website:target:audit": {"source": TARGET_WEBSITE_AUDIT_RUN_ID},
        "website:target:pages": {"source": TARGET_WEBSITE_AUDIT_RUN_ID},
        "website:cuttlefish:audit": {"source": COHORT[0]["website_audit_run_id"]},
        "website:cuttlefish:pages": {"source": COHORT[0]["website_audit_run_id"]},
        "website:trevor:audit": {"source": COHORT[1]["website_audit_run_id"]},
        "website:trevor:pages": {"source": COHORT[1]["website_audit_run_id"]},
        "website:simon:audit": {"source": COHORT[2]["website_audit_run_id"]},
        "website:simon:pages": {"source": COHORT[2]["website_audit_run_id"]},
        "reviews:target:set": {"google_place_id": TARGET_PLACE_ID},
        "reviews:cuttlefish:set": {"google_place_id": COHORT[0]["google_place_id"]},
        "reviews:trevor:set": {"google_place_id": COHORT[1]["google_place_id"]},
        "reviews:simon:set": {"google_place_id": COHORT[2]["google_place_id"]},
        "diagnostic:review_benchmark": {"source": "deterministic hair-services review profile"},
        "diagnostic:entity_matrix": {"source": DECISION_VERSION},
        **{f"gap:{item['gap_id']}": {"source": DECISION_VERSION} for item in ANALYST_DECISIONS["gaps"]},
    },
}


def assemble_ciscos_karma_owner_services_payload(*, engine: Engine | None = None) -> dict[str, Any]:
    return assemble_poc_audit_payload(CONFIG, engine=engine)
