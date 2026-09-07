from __future__ import annotations

import re
from typing import Any


BRIEFS_STATE_KEY = "accessible_ai_report_owner_briefs"
AI_VISIBILITY_HANDOFF_KEY = "ai_visibility_report_handoff_target"
AI_VISIBILITY_FORCE_PROMPTS_KEY = "ai_visibility_force_owner_prompts"


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
