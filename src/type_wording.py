"""Wording for a kind of business the platform has no built-in wording for.

Reports talk about "how to book a table" or "membership and desk prices". For a type of business
nobody has written that for (a sauna, a dog groomer), the generic wording ("enquire or book",
"prices or price guidance") is honest but bland. An AI can draft the specific wording, but a client
reads the result, so a draft is never used until a reviewer has checked it and chosen to use it.

Nothing here calls a network. `draft_type_wording` takes the function that does, so tests never pay.
The checks below apply to a draft and to anything a reviewer edits: content that should not be
drafted at all (a number, price, link or claim) is refused with a plain reason; a value that is
merely too long is shortened at a word boundary, the same rule the client summary uses elsewhere,
never thrown away over a few characters.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from typing import Any

from src.client_summary.actions import BusinessProfile, profile_for

PHRASE_LIMIT = 90
DETAILS_LIMIT = 170
LABEL_LIMIT = 40
MAX_THEMES = 8
MAX_SITE_CHECKS = 8
TERMS_PER_THEME = (3, 8)
THEME_CATEGORIES = ("Service", "Experience", "Value", "Journey", "Problems")
_FORBIDDEN = re.compile(r"(https?://|www\.|@|£|\$|\d|guarantee|best in|award|#1)", re.IGNORECASE)
# A search phrase may contain a number ("10-session pass"); it must not carry a price, link or claim.
_FORBIDDEN_TERM = re.compile(r"(https?://|www\.|@|£|\$|guarantee|best in|award|#1)", re.IGNORECASE)


class InvalidWordingError(ValueError):
    """The wording is unusable, with the reason in plain words."""


def _shorten(text: str, limit: int) -> str:
    """Cut at a word boundary with an ellipsis, the same rule the client summary uses; never rejects for length alone."""

    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0].rstrip(",;:- ") + "…"


def _phrase(value: Any, name: str, limit: int) -> str:
    text = " ".join(str(value or "").split()).strip(" .;")
    if not text:
        raise InvalidWordingError(f"“{name}” is empty.")
    # Content that should not be drafted at all is a hard failure; a merely long draft is shortened, not thrown away.
    if _FORBIDDEN.search(text):
        raise InvalidWordingError(f"“{name}” contains a number, price, link or claim that should not be drafted: “{text}”.")
    return _shorten(text, limit)


def _theme(raw: Mapping[str, Any]) -> dict[str, Any]:
    label = _phrase(raw.get("label"), "theme label", LABEL_LIMIT)
    category = str(raw.get("category") or "Experience").strip().title()
    if category not in THEME_CATEGORIES:
        raise InvalidWordingError(f"Theme “{label}” has category “{category}”; use one of {', '.join(THEME_CATEGORIES)}.")
    terms = []
    for term in raw.get("terms") or []:
        clean = " ".join(str(term).casefold().split())
        if 2 <= len(clean) <= 40 and not _FORBIDDEN_TERM.search(clean) and clean not in terms:
            terms.append(clean)
    low, high = TERMS_PER_THEME
    if len(terms) < low:
        raise InvalidWordingError(f"Theme “{label}” needs at least {low} distinct search phrases.")
    key = "type_" + re.sub(r"[^a-z0-9]+", "_", label.casefold()).strip("_")
    return {"key": key, "label": label, "category": category, "terms": terms[:high]}


def _terms(values: Any, *, name: str, label: str, minimum: int, maximum: int) -> list[str]:
    terms: list[str] = []
    for term in values or []:
        clean = " ".join(str(term).casefold().split())
        if 2 <= len(clean) <= 40 and not _FORBIDDEN_TERM.search(clean) and clean not in terms:
            terms.append(clean)
    if len(terms) < minimum:
        raise InvalidWordingError(f"Website topic “{label}” needs at least {minimum} {name}.")
    return terms[:maximum]


def _site_check(raw: Mapping[str, Any]) -> dict[str, Any]:
    label = _phrase(raw.get("label"), "website topic", LABEL_LIMIT)
    return {
        "key": "type_check_" + re.sub(r"[^a-z0-9]+", "_", label.casefold()).strip("_"),
        "label": label,
        "page_terms": _terms(raw.get("page_terms"), name="phrases a page on it would contain", label=label, minimum=2, maximum=6),
        "url_terms": _terms(raw.get("url_terms"), name="URL words", label=label, minimum=0, maximum=3),
    }


def validate_wording(raw: Mapping[str, Any]) -> dict[str, Any]:
    """The wording as it will be saved and used, or InvalidWordingError."""

    themes = [_theme(item) for item in list(raw.get("review_themes") or [])[:MAX_THEMES]]
    if len({t["key"] for t in themes}) != len(themes):
        raise InvalidWordingError("Two review themes have the same name.")
    checks = [_site_check(item) for item in list(raw.get("site_checks") or [])[:MAX_SITE_CHECKS]]
    if len({c["key"] for c in checks}) != len(checks):
        raise InvalidWordingError("Two website topics have the same name.")
    return {
        "label": _phrase(raw.get("label"), "kind of business", LABEL_LIMIT),
        "booking": _phrase(raw.get("booking"), "how customers book", PHRASE_LIMIT),
        "pricing": _phrase(raw.get("pricing"), "what prices are called", PHRASE_LIMIT),
        "questions": _phrase(raw.get("questions"), "questions customers ask", PHRASE_LIMIT),
        "details": _phrase(raw.get("details"), "details a listing should show", DETAILS_LIMIT),
        "review_themes": themes,
        "site_checks": checks,
    }


SYSTEM = (
    "You write short, plain UK-English wording that a small-business report will use for one kind of local business. "
    "You do not know this business. Do not praise it or claim anything about it; do not include numbers, prices, links, "
    "awards or guarantees. Reply with one JSON object and nothing else."
)


def build_prompt(*, business_type: str, known_for: str = "", priorities: list[str] | None = None, questions: list[str] | None = None) -> str:
    priorities = [p for p in (priorities or []) if p][:8]
    questions = [q for q in (questions or []) if q][:8]
    return (
        f"Kind of business: {business_type}\n"
        f"What the owner wants to be known for: {known_for or 'not given'}\n"
        f"Owner's priority services: {'; '.join(priorities) or 'not given'}\n"
        f"Questions customers might ask an AI assistant: {'; '.join(questions) or 'not given'}\n\n"
        "Return JSON with exactly these keys:\n"
        '  "label": what to call this kind of business (2-3 words, lower case, e.g. "sauna").\n'
        f'  "booking": a phrase that completes "Make it obvious how to ..." for this kind of business, under {PHRASE_LIMIT} characters '
        '(e.g. "book a table, a group or an event").\n'
        f'  "pricing": a noun phrase for what customers look for in prices, under {PHRASE_LIMIT} characters (e.g. "menus and prices").\n'
        f'  "questions": a comma list of what customers ask before they enquire, under {PHRASE_LIMIT} characters '
        '(e.g. "access hours, guests, contracts and facilities").\n'
        f'  "details": a comma list of what a listing or website should show, under {DETAILS_LIMIT} characters.\n'
        f'  "review_themes": up to {MAX_THEMES} objects {{"label", "category", "terms"}} for what customers of this kind of business '
        f'say in reviews. category is one of {", ".join(THEME_CATEGORIES)}; terms are 3-8 lower-case phrases a review would '
        "actually contain. Include a mix of positives and problems.\n"
        f'  "site_checks": up to {MAX_SITE_CHECKS} objects {{"label", "page_terms", "url_terms"}}: things a customer of this kind of '
        "business looks for on its website that a competitor's site would plausibly cover (for example a service, a way to buy "
        'a gift, or what to know before a first visit). label is short; page_terms are 2-6 lower-case phrases a page on it would '
        'contain; url_terms are 0-3 lower-case words that would appear in its web address.\n'
    )


def parse_draft(text: str) -> dict[str, Any]:
    """The validated wording from a model's reply."""

    match = re.search(r"\{.*\}", str(text), re.DOTALL)
    if not match:
        raise InvalidWordingError("The reply did not contain wording.")
    try:
        raw = json.loads(match.group(0))
    except ValueError as exc:
        raise InvalidWordingError("The reply could not be read as wording.") from exc
    if not isinstance(raw, dict):
        raise InvalidWordingError("The reply did not contain wording.")
    return validate_wording(raw)


def draft_type_wording(
    call: Callable[[str, str], str], *, business_type: str, known_for: str = "",
    priorities: list[str] | None = None, questions: list[str] | None = None,
) -> dict[str, Any]:
    """Ask `call(system, prompt)` for wording and return it checked. The caller decides whether to use it."""

    return parse_draft(call(SYSTEM, build_prompt(business_type=business_type, known_for=known_for, priorities=priorities, questions=questions)))


def call_claude(api_key: str, model: str) -> Callable[[str, str], str]:
    """The one paid call this module makes: a single short Claude request."""

    import requests

    def call(system: str, prompt: str) -> str:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": model, "max_tokens": 1500, "system": system, "messages": [{"role": "user", "content": prompt}]},
            timeout=60,
        )
        payload = response.json()
        if not response.ok:
            raise InvalidWordingError(f"The AI service returned an error ({response.status_code}).")
        return "\n".join(str(p.get("text", "")) for p in payload.get("content", []) if p.get("type") == "text")

    return call


def to_profile(wording: Mapping[str, Any] | None, group: str | None = None) -> BusinessProfile:
    """The built-in profile for the type, with a reviewer-approved draft's wording laid over it."""

    base = profile_for(group)
    if not wording:
        return base
    return BusinessProfile(
        details=str(wording.get("details") or base.details), platforms=base.platforms,
        booking=str(wording.get("booking") or base.booking), pricing=str(wording.get("pricing") or base.pricing),
        questions=str(wording.get("questions") or base.questions),
    )


def to_audit_checks(wording: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """Website checks for the type, in the shape the website benchmark evaluates over saved pages."""

    return [
        {
            "key": check["key"], "label": check["label"], "category": "Type-specific coverage", "weight": 3,
            "page_terms": list(check["page_terms"]), "url_terms": list(check["url_terms"]),
            "recommendation": f"Cover “{check['label']}” on its own page or clear section.",
        }
        for check in (wording or {}).get("site_checks") or []
    ]


def site_checks_to_text(checks: list[Mapping[str, Any]]) -> str:
    return "\n".join(f"{c['label']} | {'; '.join(c['page_terms'])} | {'; '.join(c['url_terms'])}" for c in checks)


def site_checks_from_text(text: str) -> list[dict[str, Any]]:
    """The editor's lines, `label | phrase; phrase | urlword; urlword` (the last part may be empty)."""

    checks = []
    for line in str(text or "").splitlines():
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) != 3:
            raise InvalidWordingError(f"Website topic line “{line.strip()[:50]}” should look like: label | phrase; phrase | url word; url word")
        checks.append({"label": parts[0], "page_terms": [t for t in parts[1].split(";") if t.strip()],
                       "url_terms": [t for t in parts[2].split(";") if t.strip()]})
    return checks


def to_review_themes(wording: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    return [dict(theme) for theme in (wording or {}).get("review_themes") or []]


def themes_to_text(themes: list[Mapping[str, Any]]) -> str:
    return "\n".join(f"{t['label']} | {t['category']} | {'; '.join(t['terms'])}" for t in themes)


def themes_from_text(text: str) -> list[dict[str, Any]]:
    """The theme editor's lines, `label | category | phrase; phrase; phrase`."""

    themes = []
    for line in str(text or "").splitlines():
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) != 3:
            raise InvalidWordingError(f"Theme line “{line.strip()[:50]}” should look like: label | category | phrase; phrase; phrase")
        themes.append({"label": parts[0], "category": parts[1], "terms": [t for t in parts[2].split(";") if t.strip()]})
    return themes
