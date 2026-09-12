from __future__ import annotations

import re
from typing import Any


BRIEFS_STATE_KEY = "accessible_ai_report_owner_briefs"
AI_VISIBILITY_HANDOFF_KEY = "ai_visibility_report_handoff_target"
AI_VISIBILITY_FORCE_PROMPTS_KEY = "ai_visibility_force_owner_prompts"
ACTIVE_REPORT_PROJECT_KEY = "active_report_project_place_id"
AI_VISIBILITY_COMPLETED_KEY = "ai_visibility_report_completed_run"


def _lines(value: str) -> list[str]:
    return [
        item.strip(" \t-•")
        for item in re.split(r"[\r\n]+", str(value or ""))
        if item.strip(" \t-•")
    ]


def normalise_owner_brief(
    *, known_for: str, desired_searches: str, owner_competitors: str = ""
) -> dict[str, Any]:
    """Normalise owner inputs without making competitors a report requirement."""

    return {
        "known_for": " ".join(str(known_for or "").split()),
        "desired_searches": _lines(desired_searches),
        "owner_competitors": _lines(owner_competitors),
    }


def owner_brief_missing_fields(brief: dict[str, Any] | None) -> list[str]:
    brief = brief or {}
    missing = []
    if len(str(brief.get("known_for") or "").strip()) < 10:
        missing.append("what the business should be known for")
    if not list(brief.get("desired_searches") or []):
        missing.append("at least one realistic customer search")
    return missing


def owner_prompt_records(brief: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Turn submitted customer questions into editable AI Visibility rows."""

    if owner_brief_missing_fields(brief):
        return []
    return [
        {
            "include": True,
            "category": "Owner priority",
            "source": "owner_brief",
            "prompt": prompt,
        }
        for prompt in list((brief or {}).get("desired_searches") or [])
    ]


def report_journey(
    *,
    owner_ready: bool,
    ai_ready: bool,
    website_ready: bool,
    reviews_ready: bool,
    configuration_ready: bool,
) -> dict[str, Any]:
    """Describe a report journey without treating optional evidence as a blocker."""

    items = [
        {
            "label": "Owner priorities",
            "importance": "Required",
            "ready": owner_ready,
            "detail": "Submitted" if owner_ready else "Two short answers needed",
        },
        {
            "label": "AI Visibility",
            "importance": "Required",
            "ready": ai_ready,
            "detail": "Completed" if ai_ready else "Needs to be run from the agreed questions",
        },
        {
            "label": "Website evidence",
            "importance": "Recommended",
            "ready": website_ready,
            "detail": "Available" if website_ready else "Add if a website exists",
        },
        {
            "label": "Customer reviews",
            "importance": "Recommended",
            "ready": reviews_ready,
            "detail": "Available" if reviews_ready else "Can be reported as unavailable",
        },
        {
            "label": "Owner competitor names",
            "importance": "Optional",
            "ready": True,
            "detail": "Not required - AI results determine the comparison set",
        },
        {
            "label": "Report review",
            "importance": "Internal",
            "ready": configuration_ready,
            "detail": "Complete" if configuration_ready else "Prepared after AI Visibility",
        },
    ]

    if configuration_ready:
        next_step = {
            "key": "generate",
            "title": "Generate the report",
            "body": "The reviewed report is ready to generate from saved evidence.",
        }
    elif not owner_ready:
        next_step = {
            "key": "owner",
            "title": "Complete the two owner-priority answers",
            "body": "These answers determine the customer questions used in AI Visibility.",
        }
    elif not ai_ready:
        next_step = {
            "key": "benchmark",
            "title": "Run AI Visibility",
            "body": "Your submitted questions will be taken to AI Visibility for review before the paid run starts.",
        }
    else:
        next_step = {
            "key": "review",
            "title": "Evidence is ready for report preparation",
            "body": (
                "The final review will select comparison businesses from the AI answers and clearly "
                "mark any unavailable website or review evidence. Owner competitor names are not required."
            ),
        }

    return {
        "items": items,
        "required_ready": owner_ready and ai_ready,
        "can_generate": configuration_ready,
        "missing_recommended": [
            label
            for label, ready in (
                ("website evidence", website_ready),
                ("customer reviews", reviews_ready),
            )
            if not ready
        ],
        "next_step": next_step,
    }
