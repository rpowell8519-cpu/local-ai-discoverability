from __future__ import annotations

from typing import Any

from sqlalchemy.engine import Engine

from src.poc_audit_assembler import assemble_poc_audit_payload


RUN_ID = "3c5a98b6-41f1-4cec-b7fe-4e788a4ab8f1"
TARGET_PLACE_ID = "ChIJOc835RGFdUgRWxPGO6RNcoc"
REVIEW_BATCH_ID = "9ff41bf1-6b4e-4196-8ffc-2dbb7bf3e440"
DECISION_VERSION = "wild_flor_stage2b_stage3_production_v1"

COHORT = (
    {
        "google_place_id": "ChIJSXUfIRW_dUgRJink33zEGqQ",
        "business_name": "etch. by Steven Edwards",
        "website_audit_run_id": "9b8a3961-16cf-449f-a575-0e47286e1002",
        "selection_reason": (
            "The market leader matched Wild Flor's 22 Gemini recommendations, "
            "but also appeared strongly in Claude and across every tested question."
        ),
    },
    {
        "google_place_id": "ChIJzcIkXEqFdUgR9oQq6cQ6hLU",
        "business_name": "The Ginger Pig - Restaurant & Rooms",
        "website_audit_run_id": "6aca146a-298f-468f-ab4c-b8e94ce62793",
        "selection_reason": (
            "Claude's most frequently recommended resolved business provides a "
            "useful comparison for broad discovery, groups and private occasions."
        ),
    },
    {
        "google_place_id": "ChIJs_74NUaFdUgRaX7YN2sS1mg",
        "business_name": "FOURTH AND CHURCH",
        "website_audit_run_id": "a82cc72c-4a08-4b08-b020-d42c01035847",
        "selection_reason": (
            "Its strong OpenAI concentration and explicit wine-led independent "
            "positioning make it a relevant comparison to Wild Flor's strengths."
        ),
    },
)

WEBSITE_AUDITS = (
    {
        "google_place_id": TARGET_PLACE_ID,
        "business_name": "Wild Flor",
        "website_audit_run_id": "9b99ab9a-0a97-4c0e-b57b-9385a26894d8",
    },
    *COHORT,
)

REVIEW_SETS = tuple(
    {
        "google_place_id": item[0],
        "business_name": item[1],
        "record_count": 100,
        "import_batch_id": REVIEW_BATCH_ID,
    }
    for item in (
        (TARGET_PLACE_ID, "Wild Flor"),
        (COHORT[0]["google_place_id"], COHORT[0]["business_name"]),
        (COHORT[1]["google_place_id"], COHORT[1]["business_name"]),
        (COHORT[2]["google_place_id"], COHORT[2]["business_name"]),
    )
)


ANALYST_DECISIONS: dict[str, Any] = {
    "version": DECISION_VERSION,
    "status": "operator_approved",
    "provenance": (
        "Wild Flor Stage 2B canonical market and approved diagnostic cohort, "
        "followed by deterministic analysis of the four completed website "
        "audits and exact 100-review sets collected for Stage 3."
    ),
    "executive_summary": {
        "headline": (
            "Wild Flor ranks fourth in the measured market and appeared across "
            "all eight customer questions."
        ),
        "summary": (
            "Visibility is uneven: Wild Flor was one of Gemini's most frequently "
            "recommended restaurants and appeared regularly in OpenAI, but was "
            "absent from every valid Claude response."
        ),
        "strengths": [],
        "action_statement": (
            "Preserve the strong wine, atmosphere and independent positioning, "
            "while making group dining, expertise and customer evidence easier "
            "to understand across public sources."
        ),
        "non_causality": (
            "The actions strengthen public evidence; they do not guarantee a "
            "change in any AI assistant's recommendations."
        ),
    },
    "strengths": [
        {
            "strength_id": "strength_visibility",
            "title": "Strong recommendation visibility already exists",
            "body": (
                "Wild Flor ranked fourth of 63 measured businesses, appeared in "
                "36 valid responses and was represented across all eight questions."
            ),
            "evidence_refs": ["market:target"],
        },
        {
            "strength_id": "strength_wine_position",
            "title": "A clear wine-led independent proposition",
            "body": (
                "The site includes dedicated wine, menu and about pages, while the "
                "wine-list question produced Wild Flor's strongest result."
            ),
            "evidence_refs": ["website:target:pages", "market:target"],
        },
        {
            "strength_id": "strength_entity_site",
            "title": "Clear owned-site foundations",
            "body": (
                "The 10-page audit found LocalBusiness data, address and contact "
                "signals, booking, social profiles, menus and private-dining content."
            ),
            "evidence_refs": ["website:target:audit", "website:target:pages"],
        },
        {
            "strength_id": "strength_customer_experience",
            "title": "Customers reinforce atmosphere and service",
            "body": (
                "Within the exact 100-review set, atmosphere appeared in 30 reviews, "
                "groups or occasions in 13, and service quality in 12."
            ),
            "evidence_refs": ["reviews:target:set", "diagnostic:review_benchmark"],
        },
    ],
    "strengths_note": (
        "The opportunity is to extend and reinforce an already credible public "
        "position, not to replace Wild Flor's proposition."
    ),
    "gaps": [
        {
            "gap_id": "gap_claude_visibility",
            "title": "Broaden visibility beyond two AI assistants",
            "observed": (
                "Wild Flor received 22 Gemini and 14 OpenAI recommendations, but "
                "none in the 23 valid Claude responses."
            ),
            "comparison": (
                "etch. received 15 Claude recommendations and The Ginger Pig 20, "
                "while both also appeared in OpenAI and Gemini."
            ),
            "relevance": (
                "The result shows that Wild Flor's current public footprint is not "
                "associated consistently across all assistants in this benchmark."
            ),
            "confidence": "High",
            "evidence_refs": ["market:target", "market:etch", "market:ginger_pig"],
        },
        {
            "gap_id": "gap_group_private",
            "title": "Make group and private-dining options easier to understand",
            "observed": (
                "Wild Flor has dedicated private-dining and Christmas pages, but "
                "appeared in only 3 of 9 group responses and 3 of 9 private-dining responses."
            ),
            "comparison": (
                "etch. and The Ginger Pig expose broader event, private-dining, "
                "booking and supporting information across their audited pages."
            ),
            "relevance": (
                "Clear practical detail can help customers and digital systems "
                "associate the restaurant with specific group and event needs."
            ),
            "confidence": "Moderate",
            "evidence_refs": ["website:target:pages", "website:etch:pages", "website:ginger_pig:pages", "market:target"],
        },
        {
            "gap_id": "gap_expertise_depth",
            "title": "Tell the people and expertise story more fully",
            "observed": (
                "Wild Flor has a useful About page, but the audit did not find a "
                "dedicated team page or FAQ content."
            ),
            "comparison": (
                "etch. provides named chef credentials, a team page and detailed "
                "FAQ content; FOURTH AND CHURCH combines story, wine and event depth."
            ),
            "relevance": (
                "More explicit information about the people, cooking and wine "
                "expertise would strengthen the public evidence behind the proposition."
            ),
            "confidence": "High",
            "evidence_refs": ["website:target:audit", "website:etch:pages", "website:fourth:pages"],
        },
        {
            "gap_id": "gap_review_profile",
            "title": "Build a more active customer-evidence programme",
            "observed": (
                "The analysed Wild Flor reviews are strongly positive, but only 3 "
                "of the exact 100 records contained an owner response."
            ),
            "comparison": (
                "The Ginger Pig had 28 owner responses and FOURTH AND CHURCH 86 in "
                "their exact 100-review sets."
            ),
            "relevance": (
                "A consistent review and response process can keep customer evidence "
                "current and make valued experiences easier to corroborate publicly."
            ),
            "confidence": "High",
            "evidence_refs": ["reviews:target:set", "reviews:ginger_pig:set", "reviews:fourth:set", "diagnostic:review_benchmark"],
        },
    ],
    "provider_hypotheses": [
        {
            "business_name": "Wild Flor",
            "hypothesis": (
                "Its strong Gemini and OpenAI visibility coincides with clear local "
                "identity, dedicated wine and private-dining pages, and positive "
                "customer evidence around atmosphere and occasions."
            ),
            "evidence_refs": ["market:target", "website:target:audit", "reviews:target:set"],
        },
        {
            "business_name": "etch. by Steven Edwards",
            "hypothesis": (
                "Its all-provider visibility coincides with a named chef identity, "
                "team, FAQ, menu and event content plus strong customer evidence."
            ),
            "evidence_refs": ["market:etch", "website:etch:pages", "reviews:etch:set"],
        },
        {
            "business_name": "The Ginger Pig - Restaurant & Rooms",
            "hypothesis": (
                "Its Claude prominence coincides with a broad restaurant, rooms, "
                "events and private-dining footprint and extensive customer evidence."
            ),
            "evidence_refs": ["market:ginger_pig", "website:ginger_pig:pages", "reviews:ginger_pig:set"],
        },
        {
            "business_name": "FOURTH AND CHURCH",
            "hypothesis": (
                "Its OpenAI concentration coincides with explicit wine, events, "
                "story and private-dining content. No provider mechanism is inferred."
            ),
            "evidence_refs": ["market:fourth", "website:fourth:pages", "reviews:fourth:set"],
        },
    ],
    "actions": [
        {
            "action_id": "action_private_dining",
            "title": "Turn private dining into a complete decision page",
            "category": "Groups and occasions",
            "steps": (
                "Expand the existing page with capacities, room formats, sample menus, "
                "occasion examples, pricing guidance, FAQs, enquiry steps and links "
                "from the homepage, menu and contact journey."
            ),
            "intended_improvement": (
                "Clearer public information for customers evaluating group meals, "
                "celebrations and private dining."
            ),
            "timing": "Weeks 1-3",
            "evidence_refs": ["gap:gap_group_private", "website:target:pages"],
        },
        {
            "action_id": "action_expertise_story",
            "title": "Make the people, cooking and wine expertise more explicit",
            "category": "Expertise and proposition",
            "steps": (
                "Develop the About content into a stronger people-and-expertise story, "
                "covering key individuals, approach to cooking, wine knowledge, sourcing "
                "and the relationship between the menu and cellar."
            ),
            "intended_improvement": (
                "A richer and more distinctive explanation of why Wild Flor is a "
                "credible independent restaurant and wine destination."
            ),
            "timing": "Weeks 1-4",
            "evidence_refs": ["gap:gap_expertise_depth", "website:target:pages"],
        },
        {
            "action_id": "action_review_programme",
            "title": "Create a consistent review and owner-response routine",
            "category": "Customer evidence",
            "steps": (
                "Use a compliant, non-incentivised request process after genuine visits, "
                "respond consistently, and monitor how customers describe wine, atmosphere, "
                "service, groups and special occasions."
            ),
            "intended_improvement": (
                "A more current and actively maintained body of independent customer "
                "evidence around the experiences Wild Flor wants to be known for."
            ),
            "timing": "Weeks 1-8",
            "evidence_refs": ["gap:gap_review_profile", "reviews:target:set"],
        },
        {
            "action_id": "action_discovery_summary",
            "title": "Strengthen the core restaurant-discovery summary",
            "category": "General discovery",
            "steps": (
                "Align homepage, About, titles and descriptions around a concise account "
                "of what Wild Flor is, where it is, who it is for, and its food, wine, "
                "atmosphere and occasion strengths."
            ),
            "intended_improvement": (
                "More consistent public context for general restaurant discovery without "
                "diluting the existing independent identity."
            ),
            "timing": "Weeks 2-4",
            "evidence_refs": ["gap:gap_claude_visibility", "website:target:audit"],
        },
        {
            "action_id": "action_faq_links",
            "title": "Add practical FAQs and strengthen internal links",
            "category": "Website usability",
            "steps": (
                "Answer common questions about dietary needs, access, booking, private "
                "dining, groups, occasions and wine, then link those answers to the most "
                "relevant menu, wine, booking and private-dining pages."
            ),
            "intended_improvement": (
                "A clearer route through the site for customers and better-connected "
                "evidence across priority topics."
            ),
            "timing": "Weeks 3-5",
            "evidence_refs": ["gap:gap_group_private", "gap:gap_expertise_depth"],
        },
    ],
    "priority_action_ids": [
        "action_private_dining",
        "action_expertise_story",
        "action_review_programme",
    ],
    "provider_observation": (
        "Wild Flor's 22 Gemini, 14 OpenAI and 0 Claude recommendations show a "
        "materially uneven provider pattern despite strong overall visibility."
    ),
    "matrix_dimensions": [
        {"label": "AI recommendation result", "evidence_refs": ["market:target", "market:etch", "market:ginger_pig", "market:fourth"], "values": {"Wild Flor": "10.20% | #4", "etch.": "13.60% | #1", "Ginger Pig": "11.90% | #2", "Fourth & Church": "6.23% | #5"}},
        {"label": "AI assistants recommending them", "evidence_refs": ["market:target", "market:etch", "market:ginger_pig", "market:fourth"], "values": {"Wild Flor": "2 / 3", "etch.": "3 / 3", "Ginger Pig": "3 / 3", "Fourth & Church": "2 / 3"}},
        {"label": "Customer questions they appeared for", "evidence_refs": ["market:target", "market:etch", "market:ginger_pig", "market:fourth"], "values": {"Wild Flor": "8 / 8", "etch.": "8 / 8", "Ginger Pig": "8 / 8", "Fourth & Church": "8 / 8"}},
        {"label": "Website pages reviewed", "evidence_refs": ["website:target:audit", "website:etch:audit", "website:ginger_pig:audit", "website:fourth:audit"], "values": {"Wild Flor": "10 pages", "etch.": "10 pages", "Ginger Pig": "10 pages", "Fourth & Church": "13 pages"}},
        {"label": "Clear business details for digital systems", "evidence_refs": ["website:target:audit", "website:etch:audit", "website:ginger_pig:audit", "website:fourth:audit"], "values": {"Wild Flor": "LocalBusiness detected", "etch.": "LocalBusiness detected", "Ginger Pig": "Organisation; no local schema detected", "Fourth & Church": "LocalBusiness detected"}},
        {"label": "Proposition and expertise information", "evidence_refs": ["website:target:pages", "website:etch:pages", "website:ginger_pig:pages", "website:fourth:pages"], "values": {"Wild Flor": "Wine, menu, about, private dining", "etch.": "Chef, team, FAQ, menus, events", "Ginger Pig": "Restaurant, rooms, events, private dining", "Fourth & Church": "Wine, story, events, private dining"}},
        {"label": "Customer reviews analysed", "evidence_refs": ["reviews:target:set", "reviews:etch:set", "reviews:ginger_pig:set", "reviews:fourth:set"], "values": {"Wild Flor": "100 | 4.65 sample rating", "etch.": "100 | 4.88 sample rating", "Ginger Pig": "100 | 4.60 sample rating", "Fourth & Church": "100 | 4.91 sample rating"}},
    ],
    "matrix_note": (
        "All four businesses supplied complete website and review evidence. The "
        "differences are observational and are not presented as ranking causes."
    ),
    "roadmap": {
        "phases": [
            {"timing": "Weeks 1-2", "title": "Clarify the offer", "body": "Strengthen group, private-dining and core discovery information."},
            {"timing": "Weeks 2-4", "title": "People and expertise", "body": "Expand the story behind the cooking, cellar and independent proposition."},
            {"timing": "Weeks 1-8", "title": "Customer evidence", "body": "Run a consistent review-request and owner-response process."},
            {"timing": "Weeks 8-12", "title": "Remeasure", "body": "Repeat the same prompt and provider methodology and disclose model changes."},
        ],
        "options": [
            {"title": "Implement internally", "body": "Use the evidence-backed action plan with your existing web and marketing partners."},
            {"title": "Supported implementation", "body": "Work collaboratively on content, technical changes and review operations."},
            {"title": "Implementation + remeasurement", "body": "Complete delivery, verification and the comparable follow-up audit."},
        ],
        "remeasurement_note": "Suggested follow-up: 8-12 weeks after meaningful implementation.",
    },
}

ANALYST_DECISIONS["executive_summary"]["strengths"] = [
    {
        "title": "Strong visibility",
        "body": "Wild Flor ranked #4 and appeared across all eight questions.",
        "evidence_refs": ["market:target"],
    },
    {
        "title": "Clear proposition",
        "body": "Dedicated wine, menu and private-dining pages support the offer.",
        "evidence_refs": ["website:target:pages"],
    },
    {
        "title": "Useful site foundations",
        "body": "LocalBusiness data, booking and contact information are present.",
        "evidence_refs": ["website:target:audit"],
    },
]


SLOT_ADJUDICATIONS = {
    "Etch": {"google_place_id": COHORT[0]["google_place_id"], "business_name": COHORT[0]["business_name"], "resolution_method": "approved_stage2b_verified_alias"},
    "etch": {"google_place_id": COHORT[0]["google_place_id"], "business_name": COHORT[0]["business_name"], "resolution_method": "approved_stage2b_verified_alias"},
    "Six": {"google_place_id": "ChIJCxCgwGqFdUgRV3BUpfNX0Kg", "business_name": "Six - Brighton & Hove", "resolution_method": "approved_stage2b_verified_short_name"},
    "Rockwater": {"google_place_id": "ChIJ8YUkI66bdUgR-Lo9DWrLrfI", "business_name": "Rockwater Hove", "resolution_method": "approved_stage2b_verified_short_name"},
    "Nostos": {"google_place_id": "ChIJbyBcHLuFdUgRg5hzD3g__QE", "business_name": "Nostos Hove", "resolution_method": "approved_stage2b_verified_short_name"},
    "Farm": {"google_place_id": None, "business_name": "Farm", "resolution_method": "approved_stage2b_unresolved"},
    "Farm Fest": {"google_place_id": None, "business_name": "Farm Fest", "resolution_method": "approved_stage2b_unresolved"},
    "Farm Fowl": {"google_place_id": None, "business_name": "Farm Fowl", "resolution_method": "approved_stage2b_unresolved"},
    "Bill's": {"google_place_id": None, "business_name": "Bill's Hove (unresolved)", "resolution_method": "approved_stage2b_unresolved_alias_group"},
    "Bill's Hove": {"google_place_id": None, "business_name": "Bill's Hove (unresolved)", "resolution_method": "approved_stage2b_unresolved_alias_group"},
    "Bill's Restaurant, Hove": {"google_place_id": None, "business_name": "Bill's Hove (unresolved)", "resolution_method": "approved_stage2b_unresolved_alias_group"},
    "Bill’s Hove": {"google_place_id": None, "business_name": "Bill's Hove (unresolved)", "resolution_method": "approved_stage2b_unresolved_alias_group"},
    "Etch. sister eateries aside, The Salt Room’s Hove counterpart “64 Degrees”": {"google_place_id": None, "business_name": "Ivy Café Hove (unresolved)", "resolution_method": "approved_stage2b_parser_reconciled_unresolved"},
}


CONFIG: dict[str, Any] = {
    "run_id": RUN_ID,
    "target_google_place_id": TARGET_PLACE_ID,
    "target_business_name": "Wild Flor",
    "category": "Restaurants",
    "location": "Hove",
    "primary_group": "restaurants",
    "review_profile": "restaurants",
    "expected_responses": 72,
    "expected_eligible_slots": 353,
    "baseline_validation_status": "verified_71_of_72",
    "verification_method_version": "independent_raw_response_reconciliation_v1",
    "target_explicit_terms": ("wild flor",),
    "target_indirect_terms": ("42 church road", "42 church rd", "wildflor.com"),
    "response_verification_note": (
        "Raw response inspected. The incomplete Claude wine-list response is "
        "preserved but excluded from all recommendation metrics."
    ),
    "verification_statement": (
        "All 72 persisted outcomes were inspected. The single truncated Claude "
        "wine-list response was excluded; all 36 Wild Flor recommendations in the "
        "71 valid responses reconcile exactly to the parsed evidence."
    ),
    "slot_adjudications": SLOT_ADJUDICATIONS,
    "non_business_prefixes": (),
    "cohort": COHORT,
    "website_audits": WEBSITE_AUDITS,
    "review_sets": REVIEW_SETS,
    "analyst_decisions": ANALYST_DECISIONS,
    "matrix_businesses": ("Wild Flor", "etch.", "Ginger Pig", "Fourth & Church"),
    "matrix_business_place_ids": {"Wild Flor": TARGET_PLACE_ID, "etch.": COHORT[0]["google_place_id"], "Ginger Pig": COHORT[1]["google_place_id"], "Fourth & Church": COHORT[2]["google_place_id"]},
    "market_note": (
        "Business Share of Recommendation uses the 353 named-business recommendations "
        "from 71 valid responses. It is benchmark-specific, not commercial market share."
    ),
    "provider_caveat": (
        "These are measured provider patterns. The audit does not claim knowledge "
        "of undocumented provider ranking or retrieval systems."
    ),
    "cohort_note": (
        "The three businesses are an operator-approved comparison set. They do not "
        "replace or curate the complete measured recommendation market."
    ),
    "gap_caveat": (
        "Observed differences are evidence-backed opportunities, not proven causes "
        "of AI recommendations."
    ),
    "action_caveat": (
        "The intended outcomes concern clearer business, content and customer evidence. "
        "No AI visibility improvement is guaranteed."
    ),
    "methodology_validation": (
        "71/72 valid: OpenAI 24, Gemini 24, Claude 23",
        "Truncated Claude wine response preserved and excluded",
        "353 named-business recommendations reconciled",
        "36 Wild Flor recommendations; no indirect or parser misses",
        "Every question represented by at least two providers",
    ),
    "methodology_limitations": (
        "This is a model-memory benchmark, not a live web-search test.",
        "Results depend on the exact prompts, model identifiers and audit date.",
        "One Claude response was repeatedly truncated and excluded from metrics.",
        "AI outputs may vary between repetitions and over time.",
        "Website and review differences are observational, not causal.",
        "The comparison cohort is an analyst-selected subset of the full market.",
        "Business Share of Recommendation is not commercial market share.",
    ),
    "non_causality": (
        "No website, identity or review difference is presented as a proven AI "
        "ranking factor or guaranteed cause of visibility."
    ),
    "evidence_registry": {
        "market:target": {"google_place_id": TARGET_PLACE_ID},
        "market:etch": {"google_place_id": COHORT[0]["google_place_id"]},
        "market:ginger_pig": {"google_place_id": COHORT[1]["google_place_id"]},
        "market:fourth": {"google_place_id": COHORT[2]["google_place_id"]},
        "website:target:audit": {"source": WEBSITE_AUDITS[0]["website_audit_run_id"]},
        "website:target:pages": {"source": WEBSITE_AUDITS[0]["website_audit_run_id"]},
        "website:etch:audit": {"source": COHORT[0]["website_audit_run_id"]},
        "website:etch:pages": {"source": COHORT[0]["website_audit_run_id"]},
        "website:ginger_pig:audit": {"source": COHORT[1]["website_audit_run_id"]},
        "website:ginger_pig:pages": {"source": COHORT[1]["website_audit_run_id"]},
        "website:fourth:audit": {"source": COHORT[2]["website_audit_run_id"]},
        "website:fourth:pages": {"source": COHORT[2]["website_audit_run_id"]},
        "reviews:target:set": {"google_place_id": TARGET_PLACE_ID},
        "reviews:etch:set": {"google_place_id": COHORT[0]["google_place_id"]},
        "reviews:ginger_pig:set": {"google_place_id": COHORT[1]["google_place_id"]},
        "reviews:fourth:set": {"google_place_id": COHORT[2]["google_place_id"]},
        "diagnostic:review_benchmark": {"source": "deterministic restaurant review profile"},
        **{f"gap:{item['gap_id']}": {"source": item["evidence_refs"]} for item in ANALYST_DECISIONS["gaps"]},
    },
}


def assemble_wild_flor_payload(*, engine: Engine | None = None) -> dict[str, Any]:
    return assemble_poc_audit_payload(CONFIG, engine=engine)
