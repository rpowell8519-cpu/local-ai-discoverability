"""Checks of a client's own website that can support a specific finding.

Each check returns an observation with its source and date, so an action built on it can
say exactly what was seen and where. A check that cannot be completed returns nothing: an
unavailable result is never reported as a gap.
"""
from __future__ import annotations

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
    }
