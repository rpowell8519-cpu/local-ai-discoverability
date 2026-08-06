from __future__ import annotations

import ipaddress
import json
import re
import socket
import time
from collections import deque
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import (
    urljoin,
    urlparse,
    urlunparse,
)
from urllib.robotparser import RobotFileParser

import requests


USER_AGENT = (
    "LocalAIVisibilityAudit/1.0 "
    "(website completeness audit)"
)

SOCIAL_HOSTS = {
    "instagram.com",
    "facebook.com",
    "www.facebook.com",
    "tiktok.com",
    "www.tiktok.com",
    "linkedin.com",
    "www.linkedin.com",
    "youtube.com",
    "www.youtube.com",
    "x.com",
    "twitter.com",
}

LOCAL_BUSINESS_SCHEMA_TYPES = {
    "LocalBusiness",
    "HairSalon",
    "BarOrPub",
    "CafeOrCoffeeShop",
    "Restaurant",
    "BeautySalon",
    "HealthAndBeautyBusiness",
    "ProfessionalService",
    "FoodEstablishment",
}

SERVICE_TERMS = {
    "service",
    "services",
    "treatment",
    "treatments",
    "hair",
    "colour",
    "color",
    "balayage",
    "menu",
    "food",
    "drink",
    "cocktail",
}

PRICING_TERMS = {
    "price",
    "prices",
    "pricing",
    "tariff",
    "cost",
}

FAQ_TERMS = {
    "faq",
    "faqs",
    "frequently asked",
    "questions",
}

BOOKING_TERMS = {
    "book",
    "booking",
    "reserve",
    "reservation",
    "appointment",
}

CONTACT_TERMS = {
    "contact",
    "telephone",
    "phone",
    "email",
    "find us",
    "visit us",
}

ADDRESS_TERMS = {
    "address",
    "street",
    "road",
    "avenue",
    "lane",
    "brighton",
    "hove",
    "postcode",
    "postal",
}


class AuditHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.meta_description: str | None = None
        self.canonical_url: str | None = None
        self.links: list[str] = []
        self.headings: list[str] = []
        self.json_ld_blocks: list[str] = []
        self.text_parts: list[str] = []

        self._in_title = False
        self._in_heading = False
        self._heading_parts: list[str] = []
        self._in_script = False
        self._script_type = ""
        self._script_parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = {
            key.lower(): value
            for key, value in attrs
        }

        if tag in {"style", "noscript"}:
            self._ignored_depth += 1

        if tag == "title":
            self._in_title = True

        if tag in {"h1", "h2", "h3"}:
            self._in_heading = True
            self._heading_parts = []

        if tag == "a":
            href = attributes.get("href")
            if href:
                self.links.append(href)

        if tag == "meta":
            name = (
                attributes.get("name")
                or attributes.get("property")
                or ""
            ).lower()

            if name == "description":
                self.meta_description = (
                    attributes.get("content")
                )

        if tag == "link":
            rel = (
                attributes.get("rel")
                or ""
            ).lower()

            if "canonical" in rel:
                self.canonical_url = (
                    attributes.get("href")
                )

        if tag == "script":
            self._in_script = True
            self._script_type = (
                attributes.get("type")
                or ""
            ).lower()
            self._script_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

        if tag in {"h1", "h2", "h3"}:
            self._in_heading = False
            heading = clean_text(
                " ".join(self._heading_parts)
            )
            if heading:
                self.headings.append(heading)
            self._heading_parts = []

        if tag == "script":
            if (
                "ld+json" in self._script_type
                and self._script_parts
            ):
                self.json_ld_blocks.append(
                    "".join(self._script_parts)
                )

            self._in_script = False
            self._script_type = ""
            self._script_parts = []

        if (
            tag in {"style", "noscript"}
            and self._ignored_depth > 0
        ):
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_script:
            self._script_parts.append(data)
            return

        if self._ignored_depth:
            return

        cleaned = clean_text(data)

        if not cleaned:
            return

        if self._in_title:
            self.title_parts.append(cleaned)

        if self._in_heading:
            self._heading_parts.append(cleaned)

        self.text_parts.append(cleaned)


def clean_text(value: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        unescape(value or ""),
    ).strip()


def normalise_url(value: str) -> str:
    value = (value or "").strip()

    if not value:
        raise ValueError("Website URL is empty.")

    if not re.match(
        r"^https?://",
        value,
        flags=re.IGNORECASE,
    ):
        value = "https://" + value

    parsed = urlparse(value)

    if parsed.scheme not in {"http", "https"}:
        raise ValueError(
            "Only HTTP and HTTPS websites are supported."
        )

    if not parsed.hostname:
        raise ValueError(
            "Website URL does not contain a valid host."
        )

    path = parsed.path or "/"

    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            "",
            parsed.query,
            "",
        )
    )


def canonicalise_for_queue(
    value: str,
) -> str:
    parsed = urlparse(value)

    path = parsed.path or "/"
    path = re.sub(r"/+", "/", path)

    if path != "/":
        path = path.rstrip("/")

    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            "",
            parsed.query,
            "",
        )
    )


def validate_public_url(value: str) -> None:
    parsed = urlparse(value)

    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Unsupported URL scheme.")

    hostname = parsed.hostname

    if not hostname:
        raise ValueError("URL has no hostname.")

    lowered = hostname.lower()

    if lowered in {
        "localhost",
        "localhost.localdomain",
    }:
        raise ValueError(
            "Local network addresses are blocked."
        )

    try:
        addresses = socket.getaddrinfo(
            hostname,
            parsed.port or (
                443
                if parsed.scheme == "https"
                else 80
            ),
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise ValueError(
            f"Hostname could not be resolved: {exc}"
        ) from exc

    for address in addresses:
        ip_text = address[4][0]
        ip = ipaddress.ip_address(ip_text)

        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise ValueError(
                "Private or reserved network "
                "addresses are blocked."
            )


def safe_get(
    session: requests.Session,
    url: str,
    *,
    timeout_seconds: int,
    max_redirects: int = 5,
) -> requests.Response:
    current_url = url

    for _ in range(max_redirects + 1):
        validate_public_url(current_url)

        response = session.get(
            current_url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": (
                    "text/html,application/xhtml+xml,"
                    "application/xml;q=0.9,*/*;q=0.8"
                ),
            },
            timeout=timeout_seconds,
            allow_redirects=False,
        )

        if response.status_code in {
            301,
            302,
            303,
            307,
            308,
        }:
            location = response.headers.get(
                "Location"
            )

            if not location:
                return response

            current_url = normalise_url(
                urljoin(current_url, location)
            )
            continue

        return response

    raise requests.TooManyRedirects(
        "Website exceeded the redirect limit."
    )


def extract_schema_types(
    blocks: list[str],
) -> set[str]:
    output: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            schema_type = value.get("@type")

            if isinstance(schema_type, str):
                output.add(schema_type)
            elif isinstance(schema_type, list):
                output.update(
                    str(item)
                    for item in schema_type
                )

            for nested in value.values():
                walk(nested)

        elif isinstance(value, list):
            for nested in value:
                walk(nested)

    for block in blocks:
        try:
            parsed = json.loads(block)
        except json.JSONDecodeError:
            continue

        walk(parsed)

    return output


def page_signal_from_url_or_text(
    url: str,
    text: str,
    terms: set[str],
) -> bool:
    combined = (
        urlparse(url).path
        + " "
        + text[:8000]
    ).lower()

    return any(term in combined for term in terms)


def analyse_html_page(
    *,
    requested_url: str,
    final_url: str,
    status_code: int,
    html: str,
) -> dict[str, Any]:
    parser = AuditHTMLParser()
    parser.feed(html)

    page_title = clean_text(
        " ".join(parser.title_parts)
    ) or None

    text_content = clean_text(
        " ".join(parser.text_parts)
    )

    schema_types = sorted(
        extract_schema_types(
            parser.json_ld_blocks
        )
    )

    parsed_final = urlparse(final_url)
    internal_links: list[str] = []
    social_links: list[str] = []
    booking_links: list[str] = []

    for href in parser.links:
        absolute = urljoin(final_url, href)
        parsed_link = urlparse(absolute)

        if parsed_link.scheme not in {
            "http",
            "https",
        }:
            continue

        host = (
            parsed_link.hostname
            or ""
        ).lower()

        if host in SOCIAL_HOSTS:
            social_links.append(
                canonicalise_for_queue(absolute)
            )

        if any(
            term in absolute.lower()
            for term in BOOKING_TERMS
        ):
            booking_links.append(
                canonicalise_for_queue(absolute)
            )

        if host == (
            parsed_final.hostname or ""
        ).lower():
            internal_links.append(
                canonicalise_for_queue(absolute)
            )

    signals = {
        "service_page": (
            page_signal_from_url_or_text(
                final_url,
                text_content,
                SERVICE_TERMS,
            )
        ),
        "menu_page": (
            "menu"
            in (
                urlparse(final_url).path
                + " "
                + text_content[:8000]
            ).lower()
        ),
        "pricing_page": (
            page_signal_from_url_or_text(
                final_url,
                text_content,
                PRICING_TERMS,
            )
        ),
        "faq_content": (
            page_signal_from_url_or_text(
                final_url,
                text_content,
                FAQ_TERMS,
            )
            or "FAQPage" in schema_types
        ),
        "booking_link": bool(booking_links),
        "contact_signals": any(
            term in text_content.lower()
            for term in CONTACT_TERMS
        ),
        "address_signals": any(
            term in text_content.lower()
            for term in ADDRESS_TERMS
        ),
        "social_links": sorted(
            set(social_links)
        ),
    }

    issues: list[str] = []

    if status_code >= 400:
        issues.append(
            f"HTTP status {status_code}"
        )

    if not page_title:
        issues.append("Missing page title")

    if not parser.meta_description:
        issues.append(
            "Missing meta description"
        )

    if not parser.canonical_url:
        issues.append(
            "Missing canonical link"
        )

    return {
        "url": requested_url,
        "final_url": final_url,
        "http_status": status_code,
        "page_title": page_title,
        "meta_description": (
            parser.meta_description
        ),
        "canonical_url": parser.canonical_url,
        "headings": parser.headings[:30],
        "schema_types": schema_types,
        "detected_signals": signals,
        "issues": issues,
        "internal_links_count": len(
            set(internal_links)
        ),
        "internal_links": sorted(
            set(internal_links)
        ),
        "text_excerpt": text_content[:3000],
    }


def robots_information(
    session: requests.Session,
    home_url: str,
    *,
    timeout_seconds: int,
) -> tuple[str, str | None, RobotFileParser]:
    parsed = urlparse(home_url)
    robots_url = urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            "/robots.txt",
            "",
            "",
            "",
        )
    )

    robot_parser = RobotFileParser()
    robot_parser.set_url(robots_url)

    try:
        response = safe_get(
            session,
            robots_url,
            timeout_seconds=timeout_seconds,
        )

        if response.status_code == 200:
            robot_parser.parse(
                response.text.splitlines()
            )

            sitemap_url = None

            for line in response.text.splitlines():
                if line.lower().startswith(
                    "sitemap:"
                ):
                    sitemap_url = line.split(
                        ":",
                        1,
                    )[1].strip()
                    break

            return (
                "found",
                sitemap_url,
                robot_parser,
            )

        robot_parser.parse([])
        return (
            f"not_found_{response.status_code}",
            None,
            robot_parser,
        )

    except Exception:
        robot_parser.parse([])
        return (
            "unavailable",
            None,
            robot_parser,
        )


def calculate_score(
    result: dict[str, Any],
) -> float:
    checks = {
        "reachable": (
            result.get("http_status") is not None
            and int(result["http_status"]) < 400
        ),
        "https": result.get("is_https") is True,
        "title": result.get("has_title") is True,
        "meta": (
            result.get(
                "has_meta_description"
            )
            is True
        ),
        "canonical": (
            result.get("has_canonical")
            is True
        ),
        "robots": (
            result.get("robots_status")
            == "found"
        ),
        "sitemap": bool(
            result.get("sitemap_url")
        ),
        "schema": bool(
            result.get("schema_types")
        ),
        "local_schema": (
            result.get(
                "has_local_business_schema"
            )
            is True
        ),
        "contact": (
            result.get(
                "has_contact_signals"
            )
            is True
        ),
        "address": (
            result.get(
                "has_address_signals"
            )
            is True
        ),
        "services": (
            result.get(
                "has_service_pages"
            )
            is True
        ),
        "pricing": (
            result.get("has_pricing_page")
            is True
        ),
        "faq": (
            result.get("has_faq_content")
            is True
        ),
        "booking": (
            result.get("has_booking_link")
            is True
        ),
        "social": (
            result.get("has_social_links")
            is True
        ),
    }

    weights = {
        "reachable": 10,
        "https": 5,
        "title": 5,
        "meta": 5,
        "canonical": 5,
        "robots": 5,
        "sitemap": 5,
        "schema": 5,
        "local_schema": 10,
        "contact": 5,
        "address": 5,
        "services": 10,
        "pricing": 5,
        "faq": 10,
        "booking": 5,
        "social": 5,
    }

    return round(
        sum(
            weights[key]
            for key, passed in checks.items()
            if passed
        ),
        2,
    )


def audit_website(
    *,
    website_url: str,
    max_pages: int = 5,
    timeout_seconds: int = 10,
    request_delay_seconds: float = 0.20,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    home_url = normalise_url(website_url)
    validate_public_url(home_url)

    session = requests.Session()

    (
        robots_status,
        sitemap_url,
        robot_parser,
    ) = robots_information(
        session,
        home_url,
        timeout_seconds=timeout_seconds,
    )

    if not robot_parser.can_fetch(
        USER_AGENT,
        home_url,
    ):
        result = {
            "final_url": home_url,
            "audit_status": "blocked",
            "http_status": None,
            "is_https": (
                urlparse(home_url).scheme
                == "https"
            ),
            "robots_status": robots_status,
            "sitemap_url": sitemap_url,
            "pages_discovered": 0,
            "pages_crawled": 0,
            "schema_types": [],
            "issues": [
                "Crawling blocked by robots.txt"
            ],
            "website_completeness_score": 0,
            "error_message": (
                "Crawling blocked by robots.txt"
            ),
        }
        return result, []

    queue: deque[str] = deque([home_url])
    queued = {canonicalise_for_queue(home_url)}
    visited: set[str] = set()
    pages: list[dict[str, Any]] = []

    root_host = (
        urlparse(home_url).hostname
        or ""
    ).lower()

    while queue and len(pages) < max_pages:
        current_url = queue.popleft()
        canonical_current = canonicalise_for_queue(
            current_url
        )

        if canonical_current in visited:
            continue

        visited.add(canonical_current)

        if not robot_parser.can_fetch(
            USER_AGENT,
            current_url,
        ):
            continue

        try:
            response = safe_get(
                session,
                current_url,
                timeout_seconds=timeout_seconds,
            )

            content_type = (
                response.headers.get(
                    "Content-Type",
                    ""
                ).lower()
            )

            if "text/html" not in content_type:
                continue

            page = analyse_html_page(
                requested_url=current_url,
                final_url=response.url,
                status_code=response.status_code,
                html=response.text,
            )

            pages.append(page)

            if len(pages) == 1:
                root_host = (
                    urlparse(
                        page.get(
                            "final_url",
                            home_url,
                        )
                    ).hostname
                    or root_host
                ).lower()

            for link in page.pop(
                "internal_links",
                [],
            ):
                parsed_link = urlparse(link)

                if (
                    parsed_link.hostname or ""
                ).lower() != root_host:
                    continue

                canonical_link = (
                    canonicalise_for_queue(link)
                )

                if (
                    canonical_link not in queued
                    and canonical_link not in visited
                ):
                    queue.append(canonical_link)
                    queued.add(canonical_link)

        except Exception as exc:
            pages.append(
                {
                    "url": current_url,
                    "final_url": current_url,
                    "http_status": None,
                    "page_title": None,
                    "meta_description": None,
                    "canonical_url": None,
                    "headings": [],
                    "schema_types": [],
                    "detected_signals": {},
                    "issues": [str(exc)],
                    "internal_links_count": 0,
                    "text_excerpt": None,
                }
            )

        if request_delay_seconds > 0:
            time.sleep(request_delay_seconds)

    successful_pages = [
        page
        for page in pages
        if (
            page.get("http_status") is not None
            and int(page["http_status"]) < 400
        )
    ]

    home_page = (
        pages[0]
        if pages
        else {}
    )

    schema_types = sorted(
        {
            schema_type
            for page in pages
            for schema_type in page.get(
                "schema_types",
                [],
            )
        }
    )

    signals = [
        page.get("detected_signals", {})
        for page in pages
    ]

    social_links = sorted(
        {
            social_url
            for signal in signals
            for social_url in signal.get(
                "social_links",
                [],
            )
        }
    )

    result = {
        "final_url": home_page.get(
            "final_url",
            home_url,
        ),
        "audit_status": (
            "completed"
            if successful_pages
            else "failed"
        ),
        "http_status": home_page.get(
            "http_status"
        ),
        "is_https": (
            urlparse(
                home_page.get(
                    "final_url",
                    home_url,
                )
            ).scheme
            == "https"
        ),
        "robots_status": robots_status,
        "sitemap_url": sitemap_url,
        "pages_discovered": len(queued),
        "pages_crawled": len(pages),
        "schema_types": schema_types,
        "has_local_business_schema": bool(
            set(schema_types)
            & LOCAL_BUSINESS_SCHEMA_TYPES
        ),
        "has_title": bool(
            home_page.get("page_title")
        ),
        "has_meta_description": bool(
            home_page.get(
                "meta_description"
            )
        ),
        "has_canonical": bool(
            home_page.get("canonical_url")
        ),
        "has_contact_signals": any(
            signal.get("contact_signals")
            for signal in signals
        ),
        "has_address_signals": any(
            signal.get("address_signals")
            for signal in signals
        ),
        "has_service_pages": any(
            signal.get("service_page")
            for signal in signals
        ),
        "has_menu_page": any(
            signal.get("menu_page")
            for signal in signals
        ),
        "has_pricing_page": any(
            signal.get("pricing_page")
            for signal in signals
        ),
        "has_faq_content": any(
            signal.get("faq_content")
            for signal in signals
        ),
        "has_booking_link": any(
            signal.get("booking_link")
            for signal in signals
        ),
        "has_social_links": bool(
            social_links
        ),
        "social_links": social_links,
        "issues": sorted(
            {
                issue
                for page in pages
                for issue in page.get(
                    "issues",
                    [],
                )
            }
        ),
        "error_message": (
            None
            if successful_pages
            else "No HTML page was successfully crawled."
        ),
    }

    result[
        "website_completeness_score"
    ] = calculate_score(result)

    return result, pages
