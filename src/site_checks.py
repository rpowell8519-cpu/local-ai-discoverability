"""Checks of a client's own website that can support a specific finding.

Each check returns an observation with its source and date, so an action built on it can
say exactly what was seen and where. A check that cannot be completed returns nothing: an
unavailable result is never reported as a gap.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

from src.website_audit import normalise_url, safe_get

# The search crawlers that decide whether an assistant can read and cite a site.
# Training crawlers (GPTBot, ClaudeBot, Google-Extended) are a separate business choice
# and are deliberately not checked here.
AI_SEARCH_CRAWLERS: tuple[tuple[str, str], ...] = (
    ("OAI-SearchBot", "ChatGPT search"),
    ("Claude-SearchBot", "Claude search"),
    ("PerplexityBot", "Perplexity"),
    ("Googlebot", "Google Search"),
    ("Bingbot", "Bing and Copilot"),
)
_UNVERIFIABLE_STATUSES = frozenset({401, 403, 429})
_OBSERVATION_LIMIT, _SOURCE_LIMIT = 220, 200


@dataclass(frozen=True)
class CrawlerAccess:
    status: str  # "blocked", "open" or "unknown"
    blocked: tuple[tuple[str, str], ...]
    robots_url: str
    checked_on: str
    robots_found: bool


def robots_location(website_url: str) -> tuple[str, str]:
    """Return (robots.txt URL, home page URL) for a website address."""

    parsed = urlparse(normalise_url(website_url))
    base = f"{parsed.scheme}://{parsed.netloc}"
    return base + "/robots.txt", base + "/"


def fetch_robots(website_url: str, *, timeout_seconds: int = 10) -> tuple[int | None, str | None]:
    """Fetch robots.txt through the audit's public-address-only fetcher."""

    robots_url, _ = robots_location(website_url)
    try:
        response = safe_get(
            requests.Session(), robots_url, timeout_seconds=timeout_seconds, max_bytes=500_000
        )
    except Exception:
        return None, None
    return response.status_code, response.text if response.status_code == 200 else None


def evaluate_robots(
    *, website_url: str, status: int | None, text: str | None, checked_on: str
) -> CrawlerAccess:
    robots_url, home_url = robots_location(website_url)

    def result(state: str, blocked=(), found=False) -> CrawlerAccess:
        return CrawlerAccess(state, tuple(blocked), robots_url, checked_on, found)

    if status is None or status >= 500 or status in _UNVERIFIABLE_STATUSES:
        return result("unknown")  # could not be read; never treated as a gap
    if status != 200:
        # No robots.txt (404, 410 and other client errors): nothing tells crawlers to stay away.
        # Anything else, such as a redirect that never resolved, cannot be relied on.
        return result("open") if 400 <= status < 500 else result("unknown")
    parser = RobotFileParser()
    parser.parse(str(text or "").splitlines())
    blocked = [(agent, label) for agent, label in AI_SEARCH_CRAWLERS if not parser.can_fetch(agent, home_url)]
    return result("blocked" if blocked else "open", blocked, found=True)


def check_ai_crawler_access(
    website_url: str,
    *,
    today: date | None = None,
    fetcher: Callable[[str], tuple[int | None, str | None]] = fetch_robots,
) -> CrawlerAccess | None:
    if not str(website_url or "").strip():
        return None
    status, text = fetcher(website_url)
    return evaluate_robots(
        website_url=website_url, status=status, text=text,
        checked_on=(today or date.today()).isoformat(),
    )


def _long_date(iso: str) -> str:
    parsed = date.fromisoformat(iso)
    return f"{parsed.day} {parsed:%B %Y}"


def crawler_finding(access: CrawlerAccess | None, finding_id: str = "E1") -> dict[str, Any] | None:
    """An observation with its source, or None when the check could not be completed."""

    if access is None or access.status == "unknown":
        return None
    source = f"{access.robots_url}, read on {_long_date(access.checked_on)}"[:_SOURCE_LIMIT]
    if access.status == "blocked":
        names = ", ".join(f"{agent} ({label})" for agent, label in access.blocked)
        observation = f"robots.txt asks these AI search crawlers not to visit the site: {names}."
        gap = True
    else:
        gap = False
        observation = (
            "robots.txt does not block the main AI search crawlers "
            "(" + ", ".join(label for _, label in AI_SEARCH_CRAWLERS) + ")."
            if access.robots_found else
            "No robots.txt file was found, so nothing tells AI search crawlers to stay away."
        )
    return {
        "id": finding_id,
        "kind": "crawler_access",
        "gap": gap,
        "observation": observation[:_OBSERVATION_LIMIT],
        "source": source,
        "blocked_labels": [label for _, label in access.blocked],
        "url": access.robots_url,
        "checked_on": access.checked_on,
    }


# --------------------------------------------------------------------------- contact details
# Compares the Google listing's phone number and postcode with the pages already saved by the
# website audit. It reads saved evidence only, so it makes no network request. A page's saved
# text is capped, so a page that reached the cap cannot show that something is absent.
SAVED_TEXT_CAP = 8000  # website_audit stores text_content[:8000] per page
_PHONE = re.compile(r"(?<![\d.])(?:\+44|0044|\(?0)[\d\s().\-]{8,16}\d(?!\d)")
_POSTCODE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?)\s*(\d[A-Z]{2})\b", re.IGNORECASE)


def normalise_uk_phone(value: str) -> str | None:
    """National form (01273123456) of a UK number, or None if it is not one."""

    digits_source = re.sub(r"\(0\)", "", str(value or ""))
    digits = re.sub(r"\D", "", digits_source)
    if digits.startswith("0044"):
        digits = "0" + digits[4:]
    elif digits.startswith("44") and str(value).strip().startswith("+"):
        digits = "0" + digits[2:]
    return digits if digits.startswith("0") and len(digits) in (10, 11) else None


def normalise_postcode(value: str) -> str | None:
    match = _POSTCODE.search(str(value or ""))
    return (match.group(1) + match.group(2)).upper() if match else None


def _readable_phone(national: str) -> str:
    if len(national) != 11:
        return national
    if national.startswith("02"):
        return f"{national[:3]} {national[3:7]} {national[7:]}"
    return f"{national[:5]} {national[5:]}"


def scan_contact_details(text: str) -> tuple[dict[str, str], dict[str, str]]:
    """Phone numbers and postcodes in the text: normalised form -> exactly as written."""

    phones: dict[str, str] = {}
    for match in _PHONE.finditer(text or ""):
        written = re.split(r"[.,;]\s", match.group(0))[0].strip()
        number = normalise_uk_phone(written)
        if number:
            phones.setdefault(number, written)
    postcodes: dict[str, str] = {}
    for match in _POSTCODE.finditer(text or ""):
        code = normalise_postcode(match.group(0))
        if code:
            postcodes.setdefault(code, match.group(0).strip())
    return phones, postcodes


def extract_contact_details(text: str) -> tuple[set[str], set[str]]:
    phones, postcodes = scan_contact_details(text)
    return set(phones), set(postcodes)


@dataclass(frozen=True)
class ContactCheck:
    discrepancies: tuple[str, ...]   # human-readable, one per field that disagrees
    mismatched: tuple[str, ...]      # which fields: "phone number", "postcode"
    matches: tuple[str, ...]         # fields confirmed on the site
    pages_read: tuple[str, ...]      # URLs of the pages the conclusion rests on
    checked_on: str
    page_evidence: tuple[dict[str, str], ...] = ()  # page id, url and the exact text quoted
    listing_phone: str = ""
    listing_postcode: str = ""


def check_contact_details(
    *,
    listing_phone: str | None,
    listing_postcode: str | None,
    pages: list[dict[str, Any]],
    checked_on: str,
) -> ContactCheck | None:
    """Compare the listing's phone and postcode with the saved page text; None if nothing can be said."""

    listing_number = normalise_uk_phone(listing_phone or "")
    listing_pc = normalise_postcode(listing_postcode or "")
    if not pages or not (listing_number or listing_pc):
        return None
    where_phone: dict[str, dict[str, str]] = {}      # number -> first page showing it
    where_pc: dict[str, dict[str, str]] = {}
    complete_phone: dict[str, dict[str, str]] = {}   # the same, from pages saved in full
    complete_pc: dict[str, dict[str, str]] = {}
    complete_urls: list[str] = []
    for page in pages:
        text = str(page.get("text_excerpt") or "")
        phones, postcodes = scan_contact_details(text)
        base = {"page_id": str(page.get("id") or ""), "url": str(page.get("url") or "")}
        for number, written in phones.items():
            where_phone.setdefault(number, {**base, "excerpt": written})
        for code, written in postcodes.items():
            where_pc.setdefault(code, {**base, "excerpt": written})
        if len(text) < SAVED_TEXT_CAP - 100:  # the whole page was saved
            complete_urls.append(base["url"])
            for number, written in phones.items():
                complete_phone.setdefault(number, {**base, "excerpt": written})
            for code, written in postcodes.items():
                complete_pc.setdefault(code, {**base, "excerpt": written})

    discrepancies, mismatched, matches, used, quoted = [], [], [], [], []
    if listing_number:
        if listing_number in where_phone:
            matches.append("phone number")
            quoted.append(where_phone[listing_number])
        elif complete_phone:
            others = sorted(complete_phone)[:2]
            discrepancies.append(
                f"the Google listing gives {_readable_phone(listing_number)}; the pages read show "
                + " and ".join(_readable_phone(n) for n in others) + " but not that number"
            )
            mismatched.append("phone number")
            used += [complete_phone[n]["url"] for n in others]
            quoted += [complete_phone[n] for n in others]
    if listing_pc:
        if listing_pc in where_pc:
            matches.append("postcode")
            quoted.append(where_pc[listing_pc])
        elif complete_pc:
            other = sorted(complete_pc)[0]
            discrepancies.append(
                f"the Google listing has postcode {listing_pc[:-3]} {listing_pc[-3:]}; the pages read show "
                f"{other[:-3]} {other[-3:]} but not that postcode"
            )
            mismatched.append("postcode")
            used.append(complete_pc[other]["url"])
            quoted.append(complete_pc[other])
    if not discrepancies and not matches:
        return None
    pages_read = tuple(dict.fromkeys(url for url in (used or complete_urls) if url))[:3]
    return ContactCheck(
        tuple(discrepancies), tuple(mismatched), tuple(matches), pages_read, checked_on,
        tuple(quoted), str(listing_phone or "").strip(), str(listing_postcode or "").strip(),
    )


def contact_finding(check: ContactCheck | None, finding_id: str = "E2") -> dict[str, Any] | None:
    if check is None:
        return None
    sources = ", ".join(check.pages_read) or "saved website pages"
    source = f"{sources}, saved {_long_date(check.checked_on)}"[:_SOURCE_LIMIT]
    if check.discrepancies:
        lead = "The website and the Google listing disagree: "
        observation = lead + "; ".join(check.discrepancies) + "."
        if len(observation) > _OBSERVATION_LIMIT:  # keep whole sentences rather than cutting one off
            observation = lead + check.discrepancies[0] + ". Another detail also differs."
        gap = True
    else:
        observation = "The website shows the same " + " and ".join(check.matches) + " as the Google listing."
        gap = False
    return {
        "id": finding_id, "kind": "contact_details", "gap": gap,
        "observation": observation[:_OBSERVATION_LIMIT], "source": source,
        "fields": list(check.mismatched),
        "matches": list(check.matches),
        "page_sources": [dict(item) for item in check.page_evidence if item.get("page_id")],
        "listing": {"phone": check.listing_phone, "postcode": check.listing_postcode},
        "checked_on": check.checked_on,
    }
