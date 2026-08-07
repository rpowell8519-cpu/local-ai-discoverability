from __future__ import annotations

import gzip
import heapq
import ipaddress
import json
import re
import socket
import time
import xml.etree.ElementTree as ET
from html import unescape
from html.parser import HTMLParser
from itertools import count
from typing import Any
from urllib.parse import (
    parse_qsl,
    urlencode,
    urljoin,
    urlparse,
    urlunparse,
)
from urllib.robotparser import RobotFileParser

import requests


USER_AGENT = (
    "LocalAIVisibilityAudit/1.1 "
    "(adaptive website completeness audit)"
)

MAX_HTML_BYTES = 3_000_000
MAX_SITEMAP_BYTES = 5_000_000
MAX_SITEMAP_URLS = 500
MAX_SITEMAP_FILES = 12

SOCIAL_HOSTS = {
    "instagram.com",
    "www.instagram.com",
    "facebook.com",
    "www.facebook.com",
    "tiktok.com",
    "www.tiktok.com",
    "linkedin.com",
    "www.linkedin.com",
    "youtube.com",
    "www.youtube.com",
    "x.com",
    "www.x.com",
    "twitter.com",
    "www.twitter.com",
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

NON_HTML_EXTENSIONS = {
    ".7z",
    ".avi",
    ".css",
    ".csv",
    ".doc",
    ".docx",
    ".eot",
    ".gif",
    ".gz",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".json",
    ".m4a",
    ".mov",
    ".mp3",
    ".mp4",
    ".mpeg",
    ".ogg",
    ".otf",
    ".pdf",
    ".png",
    ".ppt",
    ".pptx",
    ".rar",
    ".rss",
    ".svg",
    ".tar",
    ".tif",
    ".tiff",
    ".ttf",
    ".txt",
    ".wav",
    ".webm",
    ".webp",
    ".woff",
    ".woff2",
    ".xls",
    ".xlsx",
    ".xml",
    ".zip",
}

EXCLUDED_PATH_TERMS = {
    "/account",
    "/admin",
    "/author/",
    "/basket",
    "/cart",
    "/checkout",
    "/cookie",
    "/feed",
    "/login",
    "/logout",
    "/my-account",
    "/privacy",
    "/search",
    "/tag/",
    "/terms",
    "/wp-admin",
    "/wp-json",
}

TRACKING_QUERY_PREFIXES = {
    "fbclid",
    "gclid",
    "mc_",
    "utm_",
}

UNIVERSAL_PRIORITY_TERMS = {
    "services": 110,
    "service": 105,
    "treatments": 105,
    "treatment": 100,
    "menu": 108,
    "food": 92,
    "drinks": 100,
    "drink": 90,
    "prices": 108,
    "pricing": 108,
    "price-list": 108,
    "faq": 105,
    "faqs": 105,
    "frequently-asked": 105,
    "booking": 100,
    "book": 92,
    "reservations": 100,
    "reserve": 92,
    "appointments": 100,
    "contact": 96,
    "find-us": 94,
    "visit-us": 92,
    "location": 88,
    "about": 80,
    "team": 88,
    "our-team": 90,
    "gallery": 84,
    "portfolio": 84,
    "events": 92,
    "whats-on": 94,
    "what-s-on": 94,
    "private-hire": 96,
    "venue-hire": 94,
    "accessibility": 82,
    "opening-hours": 88,
    "opening-times": 88,
}

GROUP_PRIORITY_TERMS = {
    "hair_services": {
        "balayage": 120,
        "colour": 112,
        "color": 112,
        "extensions": 112,
        "curly": 106,
        "blonde": 104,
        "blonding": 108,
        "consultation": 112,
        "stylists": 108,
        "hairdressers": 104,
        "before-after": 106,
        "our-work": 100,
        "bridal": 98,
    },
    "bars_pubs": {
        "food-menu": 120,
        "drinks-menu": 120,
        "cocktails": 110,
        "wine": 102,
        "beer": 102,
        "sunday-roast": 108,
        "live-music": 112,
        "events": 110,
        "whats-on": 112,
        "private-hire": 115,
        "functions": 104,
        "parties": 100,
        "garden": 96,
        "terrace": 96,
        "rooftop": 96,
        "sports": 90,
    },
    "coffee_cafes": {
        "coffee": 104,
        "brunch": 112,
        "breakfast": 104,
        "bakery": 102,
        "pastries": 100,
        "workspace": 94,
        "wifi": 92,
        "wi-fi": 92,
    },
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
    "common questions",
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

SIGNAL_TERMS = {
    "team_page": {
        "meet the team",
        "our team",
        "our stylists",
        "our hairdressers",
        "our colourists",
        "our colorists",
    },
    "consultation_page": {
        "consultation",
        "book a consultation",
    },
    "gallery_page": {
        "gallery",
        "before and after",
        "before & after",
        "our work",
        "portfolio",
    },
    "events_page": {
        "events",
        "what's on",
        "whats on",
        "live music",
        "live performances",
        "quiz night",
    },
    "private_hire_page": {
        "private hire",
        "venue hire",
        "function room",
        "group bookings",
    },
    "outdoor_page": {
        "beer garden",
        "outdoor seating",
        "roof terrace",
        "rooftop",
        "courtyard",
    },
    "opening_hours": {
        "opening hours",
        "opening times",
        "hours of operation",
    },
    "accessibility_page": {
        "accessibility",
        "wheelchair accessible",
        "wheelchair-accessible",
        "disabled access",
    },
    "drinks_menu": {
        "drinks menu",
        "cocktail menu",
        "wine list",
        "beer list",
        "our beers",
        "our cocktails",
    },
}

COVERAGE_TARGETS = {
    "hair_services": {
        "service",
        "pricing",
        "faq",
        "booking",
        "contact",
        "team",
        "consultation",
        "gallery",
    },
    "bars_pubs": {
        "menu",
        "drinks",
        "events",
        "private_hire",
        "booking",
        "contact",
        "opening_hours",
    },
    "coffee_cafes": {
        "menu",
        "pricing",
        "booking",
        "contact",
        "opening_hours",
    },
    "generic": {
        "service",
        "pricing",
        "faq",
        "booking",
        "contact",
    },
}


class AuditHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.meta_description: str | None = None
        self.canonical_url: str | None = None
        self.links: list[dict[str, str]] = []
        self.headings: list[str] = []
        self.json_ld_blocks: list[str] = []
        self.text_parts: list[str] = []

        self._in_title = False
        self._in_heading = False
        self._heading_parts: list[str] = []
        self._in_anchor = False
        self._anchor_href = ""
        self._anchor_parts: list[str] = []
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
            self._in_anchor = True
            self._anchor_href = (
                attributes.get("href")
                or ""
            )
            self._anchor_parts = []

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

        if tag == "a":
            if self._anchor_href:
                self.links.append(
                    {
                        "href": self._anchor_href,
                        "text": clean_text(
                            " ".join(
                                self._anchor_parts
                            )
                        ),
                    }
                )
            self._in_anchor = False
            self._anchor_href = ""
            self._anchor_parts = []

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

        if self._in_anchor:
            self._anchor_parts.append(cleaned)

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
            sanitise_query(parsed.query),
            "",
        )
    )


def sanitise_query(query: str) -> str:
    if not query:
        return ""

    retained = []

    for key, value in parse_qsl(
        query,
        keep_blank_values=False,
    ):
        lowered = key.lower()

        if any(
            lowered == prefix
            or lowered.startswith(prefix)
            for prefix in TRACKING_QUERY_PREFIXES
        ):
            continue

        if lowered in {
            "page",
            "paged",
            "p",
        }:
            retained.append(
                (key, value)
            )

    return urlencode(retained)


def canonicalise_for_queue(
    value: str,
) -> str:
    parsed = urlparse(value)

    path = re.sub(
        r"/+",
        "/",
        parsed.path or "/",
    )

    if path != "/":
        path = path.rstrip("/")

    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            "",
            sanitise_query(parsed.query),
            "",
        )
    )


def base_host(value: str) -> str:
    host = (
        urlparse(value).hostname
        or ""
    ).lower()

    return (
        host[4:]
        if host.startswith("www.")
        else host
    )


def same_site(
    first_url: str,
    second_url: str,
) -> bool:
    return bool(
        base_host(first_url)
        and base_host(first_url)
        == base_host(second_url)
    )


def validate_public_url(value: str) -> None:
    parsed = urlparse(value)

    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Unsupported URL scheme.")

    hostname = parsed.hostname

    if not hostname:
        raise ValueError("URL has no hostname.")

    if hostname.lower() in {
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
        ip = ipaddress.ip_address(
            address[4][0]
        )

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
    max_bytes: int,
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
                    "application/xml,text/xml;q=0.9,"
                    "*/*;q=0.5"
                ),
            },
            timeout=timeout_seconds,
            allow_redirects=False,
            stream=True,
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
            response.close()

            if not location:
                return response

            current_url = normalise_url(
                urljoin(current_url, location)
            )
            continue

        content = bytearray()

        for chunk in response.iter_content(
            chunk_size=65536
        ):
            if not chunk:
                continue

            content.extend(chunk)

            if len(content) > max_bytes:
                response.close()
                raise ValueError(
                    "Response exceeded the audit "
                    "download-size limit."
                )

        response._content = bytes(content)
        response._content_consumed = True
        response.close()

        return response

    raise requests.TooManyRedirects(
        "Website exceeded the redirect limit."
    )


def is_crawlable_html_url(
    value: str,
) -> bool:
    parsed = urlparse(value)
    path = parsed.path.lower()

    if any(
        path.endswith(extension)
        for extension in NON_HTML_EXTENSIONS
    ):
        return False

    if any(
        term in path
        for term in EXCLUDED_PATH_TERMS
    ):
        return False

    return True


def url_priority(
    value: str,
    *,
    business_group: str,
    anchor_text: str = "",
    source: str = "link",
) -> int:
    parsed = urlparse(value)
    path = (
        parsed.path
        .strip("/")
        .lower()
    )

    if not path:
        return 1000

    combined = (
        path.replace("_", "-")
        + " "
        + anchor_text.lower()
    )

    score = 30

    depth = len(
        [
            segment
            for segment in path.split("/")
            if segment
        ]
    )

    score -= max(
        0,
        depth - 1,
    ) * 3

    for term, term_score in (
        UNIVERSAL_PRIORITY_TERMS.items()
    ):
        if term in combined:
            score = max(
                score,
                term_score,
            )

    for term, term_score in (
        GROUP_PRIORITY_TERMS.get(
            business_group,
            {},
        ).items()
    ):
        if term in combined:
            score = max(
                score,
                term_score,
            )

    if source == "sitemap":
        score += 4

    if source == "homepage":
        score += 8

    if any(
        term in combined
        for term in {
            "blog",
            "news",
            "article",
            "press",
        }
    ):
        score -= 10

    return score


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
        + text[:12000]
    ).lower()

    return any(
        term in combined
        for term in terms
    )


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

    internal_links: list[
        dict[str, str]
    ] = []
    social_links: list[str] = []
    booking_links: list[str] = []

    linked_signal_text = []

    for link in parser.links:
        href = link.get("href", "")
        anchor_text = link.get("text", "")
        absolute = urljoin(
            final_url,
            href,
        )
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
                canonicalise_for_queue(
                    absolute
                )
            )

        combined_link = (
            absolute
            + " "
            + anchor_text
        ).lower()

        if any(
            term in combined_link
            for term in BOOKING_TERMS
        ):
            booking_links.append(
                canonicalise_for_queue(
                    absolute
                )
            )

        if same_site(
            final_url,
            absolute,
        ):
            canonical = (
                canonicalise_for_queue(
                    absolute
                )
            )

            internal_links.append(
                {
                    "url": canonical,
                    "anchor_text": (
                        anchor_text
                    ),
                }
            )
            linked_signal_text.append(
                combined_link
            )

    signal_text = (
        text_content[:12000]
        + " "
        + " ".join(
            linked_signal_text[:200]
        )
    ).lower()

    signals = {
        "service_page": (
            page_signal_from_url_or_text(
                final_url,
                signal_text,
                SERVICE_TERMS,
            )
        ),
        "menu_page": (
            "menu"
            in (
                urlparse(
                    final_url
                ).path
                + " "
                + signal_text
            ).lower()
        ),
        "pricing_page": (
            page_signal_from_url_or_text(
                final_url,
                signal_text,
                PRICING_TERMS,
            )
        ),
        "faq_content": (
            page_signal_from_url_or_text(
                final_url,
                signal_text,
                FAQ_TERMS,
            )
            or "FAQPage" in schema_types
        ),
        "booking_link": bool(
            booking_links
        ),
        "contact_signals": any(
            term in signal_text
            for term in CONTACT_TERMS
        ),
        "address_signals": any(
            term in signal_text
            for term in ADDRESS_TERMS
        ),
        "social_links": sorted(
            set(social_links)
        ),
    }

    for signal_name, terms in (
        SIGNAL_TERMS.items()
    ):
        signals[signal_name] = any(
            term in (
                urlparse(
                    final_url
                ).path
                + " "
                + signal_text
            ).lower()
            for term in terms
        )

    issues: list[str] = []

    if status_code >= 400:
        issues.append(
            f"HTTP status {status_code}"
        )

    if not page_title:
        issues.append(
            "Missing page title"
        )

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
        "canonical_url": (
            parser.canonical_url
        ),
        "headings": parser.headings[:40],
        "schema_types": schema_types,
        "detected_signals": signals,
        "issues": issues,
        "internal_links_count": len(
            {
                item["url"]
                for item in internal_links
            }
        ),
        "internal_links": (
            internal_links
        ),
        "text_excerpt": (
            text_content[:8000]
        ),
    }


def robots_information(
    session: requests.Session,
    home_url: str,
    *,
    timeout_seconds: int,
) -> tuple[
    str,
    list[str],
    RobotFileParser,
]:
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
    robot_parser.set_url(
        robots_url
    )

    try:
        response = safe_get(
            session,
            robots_url,
            timeout_seconds=(
                timeout_seconds
            ),
            max_bytes=500_000,
        )

        if response.status_code == 200:
            lines = (
                response.text.splitlines()
            )
            robot_parser.parse(lines)

            sitemap_urls = []

            for line in lines:
                if line.lower().startswith(
                    "sitemap:"
                ):
                    sitemap_urls.append(
                        line.split(
                            ":",
                            1,
                        )[1].strip()
                    )

            return (
                "found",
                sitemap_urls,
                robot_parser,
            )

        robot_parser.parse([])

        return (
            (
                "not_found_"
                + str(
                    response.status_code
                )
            ),
            [],
            robot_parser,
        )

    except Exception:
        robot_parser.parse([])

        return (
            "unavailable",
            [],
            robot_parser,
        )


def xml_local_name(
    tag: str,
) -> str:
    return tag.split(
        "}",
        1,
    )[-1].lower()


def parse_sitemap_document(
    content: bytes,
    *,
    source_url: str,
) -> tuple[
    list[str],
    list[str],
]:
    raw = content

    if (
        source_url.lower().endswith(
            ".gz"
        )
    ):
        try:
            raw = gzip.decompress(
                content
            )
        except OSError:
            raw = content

    root = ET.fromstring(raw)

    page_urls: list[str] = []
    child_sitemaps: list[str] = []

    root_name = xml_local_name(
        root.tag
    )

    for element in root.iter():
        if xml_local_name(
            element.tag
        ) != "loc":
            continue

        value = (
            element.text
            or ""
        ).strip()

        if not value:
            continue

        if root_name == "sitemapindex":
            child_sitemaps.append(
                value
            )
        else:
            page_urls.append(
                value
            )

    return (
        page_urls,
        child_sitemaps,
    )


def discover_sitemap_pages(
    session: requests.Session,
    *,
    home_url: str,
    robots_sitemaps: list[str],
    timeout_seconds: int,
) -> tuple[
    list[str],
    list[str],
]:
    parsed = urlparse(home_url)
    fallback_sitemaps = [
        urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                "/sitemap.xml",
                "",
                "",
                "",
            )
        ),
        urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                "/sitemap_index.xml",
                "",
                "",
                "",
            )
        ),
    ]

    pending = []

    for candidate in [
        *robots_sitemaps,
        *fallback_sitemaps,
    ]:
        try:
            normalised = normalise_url(
                candidate
            )
        except ValueError:
            continue

        if same_site(
            home_url,
            normalised,
        ):
            pending.append(
                normalised
            )

    pending = list(
        dict.fromkeys(pending)
    )

    successful_sitemaps: list[str] = []
    page_urls: list[str] = []
    visited_sitemaps: set[str] = set()

    while (
        pending
        and len(
            visited_sitemaps
        ) < MAX_SITEMAP_FILES
        and len(
            page_urls
        ) < MAX_SITEMAP_URLS
    ):
        sitemap_url = pending.pop(0)

        if (
            sitemap_url
            in visited_sitemaps
        ):
            continue

        visited_sitemaps.add(
            sitemap_url
        )

        try:
            response = safe_get(
                session,
                sitemap_url,
                timeout_seconds=(
                    timeout_seconds
                ),
                max_bytes=(
                    MAX_SITEMAP_BYTES
                ),
            )
        except Exception:
            continue

        if (
            response.status_code
            != 200
        ):
            continue

        content_type = (
            response.headers.get(
                "Content-Type",
                "",
            ).lower()
        )

        if not (
            "xml" in content_type
            or sitemap_url.lower().endswith(
                (
                    ".xml",
                    ".xml.gz",
                    ".gz",
                )
            )
        ):
            continue

        try:
            (
                discovered_pages,
                child_sitemaps,
            ) = parse_sitemap_document(
                response.content,
                source_url=sitemap_url,
            )
        except ET.ParseError:
            continue

        successful_sitemaps.append(
            sitemap_url
        )

        for page_url in discovered_pages:
            try:
                normalised_page = (
                    normalise_url(
                        page_url
                    )
                )
            except ValueError:
                continue

            if (
                same_site(
                    home_url,
                    normalised_page,
                )
                and is_crawlable_html_url(
                    normalised_page
                )
            ):
                page_urls.append(
                    canonicalise_for_queue(
                        normalised_page
                    )
                )

            if (
                len(page_urls)
                >= MAX_SITEMAP_URLS
            ):
                break

        for child_url in child_sitemaps:
            try:
                normalised_child = (
                    normalise_url(
                        child_url
                    )
                )
            except ValueError:
                continue

            if (
                same_site(
                    home_url,
                    normalised_child,
                )
                and normalised_child
                not in visited_sitemaps
            ):
                pending.append(
                    normalised_child
                )

    return (
        list(
            dict.fromkeys(
                page_urls
            )
        )[:MAX_SITEMAP_URLS],
        list(
            dict.fromkeys(
                successful_sitemaps
            )
        ),
    )


def coverage_from_page(
    page: dict[str, Any],
) -> set[str]:
    signals = page.get(
        "detected_signals",
        {},
    )

    mapping = {
        "service_page": "service",
        "menu_page": "menu",
        "pricing_page": "pricing",
        "faq_content": "faq",
        "booking_link": "booking",
        "contact_signals": "contact",
        "address_signals": "address",
        "team_page": "team",
        "consultation_page": (
            "consultation"
        ),
        "gallery_page": "gallery",
        "events_page": "events",
        "private_hire_page": (
            "private_hire"
        ),
        "outdoor_page": "outdoor",
        "opening_hours": (
            "opening_hours"
        ),
        "accessibility_page": (
            "accessibility"
        ),
        "drinks_menu": "drinks",
    }

    return {
        coverage_name
        for signal_name, coverage_name
        in mapping.items()
        if signals.get(
            signal_name
        )
    }


def should_stop_adaptively(
    *,
    pages_crawled: int,
    max_pages: int,
    business_group: str,
    coverage: set[str],
    next_priority: int | None,
) -> bool:
    if pages_crawled >= max_pages:
        return True

    minimum_pages = min(
        max_pages,
        max(
            6,
            round(
                max_pages * 0.50
            ),
        ),
    )

    if pages_crawled < minimum_pages:
        return False

    target_coverage = (
        COVERAGE_TARGETS.get(
            business_group,
            COVERAGE_TARGETS[
                "generic"
            ],
        )
    )

    coverage_ratio = (
        len(
            target_coverage
            & coverage
        )
        / len(
            target_coverage
        )
    )

    return (
        coverage_ratio >= 0.80
        and (
            next_priority is None
            or next_priority < 80
        )
    )


def calculate_score(
    result: dict[str, Any],
) -> float:
    checks = {
        "reachable": (
            result.get(
                "http_status"
            )
            is not None
            and int(
                result[
                    "http_status"
                ]
            )
            < 400
        ),
        "https": (
            result.get(
                "is_https"
            )
            is True
        ),
        "title": (
            result.get(
                "has_title"
            )
            is True
        ),
        "meta": (
            result.get(
                "has_meta_description"
            )
            is True
        ),
        "canonical": (
            result.get(
                "has_canonical"
            )
            is True
        ),
        "robots": (
            result.get(
                "robots_status"
            )
            == "found"
        ),
        "sitemap": bool(
            result.get(
                "sitemap_url"
            )
        ),
        "schema": bool(
            result.get(
                "schema_types"
            )
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
            result.get(
                "has_pricing_page"
            )
            is True
        ),
        "faq": (
            result.get(
                "has_faq_content"
            )
            is True
        ),
        "booking": (
            result.get(
                "has_booking_link"
            )
            is True
        ),
        "social": (
            result.get(
                "has_social_links"
            )
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
            for key, passed
            in checks.items()
            if passed
        ),
        2,
    )


def audit_website(
    *,
    website_url: str,
    business_group: str = "generic",
    max_pages: int = 20,
    timeout_seconds: int = 10,
    request_delay_seconds: float = 0.20,
    adaptive_stop: bool = True,
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
]:
    home_url = normalise_url(
        website_url
    )
    validate_public_url(home_url)

    session = requests.Session()

    (
        robots_status,
        robots_sitemaps,
        robot_parser,
    ) = robots_information(
        session,
        home_url,
        timeout_seconds=(
            timeout_seconds
        ),
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
                urlparse(
                    home_url
                ).scheme
                == "https"
            ),
            "robots_status": (
                robots_status
            ),
            "sitemap_url": (
                robots_sitemaps[0]
                if robots_sitemaps
                else None
            ),
            "pages_discovered": 0,
            "pages_crawled": 0,
            "schema_types": [],
            "issues": [
                "Crawling blocked "
                "by robots.txt"
            ],
            "website_completeness_score": 0,
            "error_message": (
                "Crawling blocked "
                "by robots.txt"
            ),
        }

        return result, []

    pages: list[
        dict[str, Any]
    ] = []
    visited: set[str] = set()
    queued: set[str] = set()
    priority_queue: list[
        tuple[int, int, str]
    ] = []
    sequence = count()
    coverage: set[str] = set()
    page_failures = 0

    def enqueue(
        url: str,
        *,
        anchor_text: str = "",
        source: str = "link",
    ) -> None:
        try:
            normalised = (
                canonicalise_for_queue(
                    normalise_url(
                        url
                    )
                )
            )
        except ValueError:
            return

        if (
            normalised in visited
            or normalised in queued
            or not same_site(
                home_url,
                normalised,
            )
            or not is_crawlable_html_url(
                normalised
            )
        ):
            return

        priority = url_priority(
            normalised,
            business_group=(
                business_group
            ),
            anchor_text=(
                anchor_text
            ),
            source=source,
        )

        heapq.heappush(
            priority_queue,
            (
                -priority,
                next(sequence),
                normalised,
            ),
        )
        queued.add(normalised)

    enqueue(
        home_url,
        source="homepage",
    )

    sitemap_pages: list[str] = []
    successful_sitemaps: list[str] = []

    while (
        priority_queue
        and len(pages) < max_pages
    ):
        (
            negative_priority,
            _,
            current_url,
        ) = heapq.heappop(
            priority_queue
        )

        queued.discard(
            current_url
        )

        if current_url in visited:
            continue

        visited.add(
            current_url
        )

        if not robot_parser.can_fetch(
            USER_AGENT,
            current_url,
        ):
            continue

        try:
            response = safe_get(
                session,
                current_url,
                timeout_seconds=(
                    timeout_seconds
                ),
                max_bytes=(
                    MAX_HTML_BYTES
                ),
            )

            content_type = (
                response.headers.get(
                    "Content-Type",
                    "",
                ).lower()
            )

            if (
                "text/html"
                not in content_type
                and "application/xhtml+xml"
                not in content_type
            ):
                continue

            page = analyse_html_page(
                requested_url=(
                    current_url
                ),
                final_url=response.url,
                status_code=(
                    response.status_code
                ),
                html=response.text,
            )

            internal_links = (
                page.pop(
                    "internal_links",
                    [],
                )
            )

            pages.append(page)
            coverage.update(
                coverage_from_page(
                    page
                )
            )

            if len(pages) == 1:
                home_url = normalise_url(
                    page.get(
                        "final_url",
                        home_url,
                    )
                )

                (
                    final_robots_status,
                    final_robots_sitemaps,
                    final_robot_parser,
                ) = robots_information(
                    session,
                    home_url,
                    timeout_seconds=(
                        timeout_seconds
                    ),
                )

                if final_robots_status == "found":
                    robots_status = (
                        final_robots_status
                    )
                    robots_sitemaps = (
                        final_robots_sitemaps
                    )
                    robot_parser = (
                        final_robot_parser
                    )

                (
                    sitemap_pages,
                    successful_sitemaps,
                ) = discover_sitemap_pages(
                    session,
                    home_url=home_url,
                    robots_sitemaps=(
                        robots_sitemaps
                    ),
                    timeout_seconds=(
                        timeout_seconds
                    ),
                )

                for sitemap_page in (
                    sitemap_pages
                ):
                    enqueue(
                        sitemap_page,
                        source="sitemap",
                    )

            for link in internal_links:
                enqueue(
                    link.get(
                        "url",
                        "",
                    ),
                    anchor_text=link.get(
                        "anchor_text",
                        "",
                    ),
                    source=(
                        "homepage"
                        if len(pages) == 1
                        else "link"
                    ),
                )

        except Exception as exc:
            page_failures += 1

            pages.append(
                {
                    "url": current_url,
                    "final_url": (
                        current_url
                    ),
                    "http_status": None,
                    "page_title": None,
                    "meta_description": (
                        None
                    ),
                    "canonical_url": None,
                    "headings": [],
                    "schema_types": [],
                    "detected_signals": {},
                    "issues": [
                        str(exc)
                    ],
                    "internal_links_count": 0,
                    "text_excerpt": None,
                }
            )

        if request_delay_seconds > 0:
            time.sleep(
                request_delay_seconds
            )

        next_priority = (
            -priority_queue[0][0]
            if priority_queue
            else None
        )

        if (
            adaptive_stop
            and should_stop_adaptively(
                pages_crawled=(
                    len(pages)
                ),
                max_pages=max_pages,
                business_group=(
                    business_group
                ),
                coverage=coverage,
                next_priority=(
                    next_priority
                ),
            )
        ):
            break

    successful_pages = [
        page
        for page in pages
        if (
            page.get(
                "http_status"
            )
            is not None
            and int(
                page[
                    "http_status"
                ]
            )
            < 400
        )
    ]

    home_page = (
        successful_pages[0]
        if successful_pages
        else (
            pages[0]
            if pages
            else {}
        )
    )

    schema_types = sorted(
        {
            schema_type
            for page in pages
            for schema_type in (
                page.get(
                    "schema_types",
                    [],
                )
            )
        }
    )

    signals = [
        page.get(
            "detected_signals",
            {},
        )
        for page in pages
    ]

    social_links = sorted(
        {
            social_url
            for signal in signals
            for social_url in (
                signal.get(
                    "social_links",
                    [],
                )
            )
        }
    )

    all_issues = sorted(
        {
            issue
            for page in pages
            for issue in (
                page.get(
                    "issues",
                    [],
                )
            )
        }
    )

    if (
        successful_pages
        and page_failures
    ):
        audit_status = "partial"
    elif successful_pages:
        audit_status = "completed"
    else:
        audit_status = "failed"

    result = {
        "final_url": (
            home_page.get(
                "final_url",
                home_url,
            )
        ),
        "audit_status": audit_status,
        "http_status": (
            home_page.get(
                "http_status"
            )
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
        "robots_status": (
            robots_status
        ),
        "sitemap_url": (
            successful_sitemaps[0]
            if successful_sitemaps
            else (
                robots_sitemaps[0]
                if robots_sitemaps
                else None
            )
        ),
        "pages_discovered": len(
            visited
            | queued
        ),
        "pages_crawled": len(
            pages
        ),
        "schema_types": (
            schema_types
        ),
        "has_local_business_schema": bool(
            set(
                schema_types
            )
            & LOCAL_BUSINESS_SCHEMA_TYPES
        ),
        "has_title": bool(
            home_page.get(
                "page_title"
            )
        ),
        "has_meta_description": bool(
            home_page.get(
                "meta_description"
            )
        ),
        "has_canonical": bool(
            home_page.get(
                "canonical_url"
            )
        ),
        "has_contact_signals": any(
            signal.get(
                "contact_signals"
            )
            for signal in signals
        ),
        "has_address_signals": any(
            signal.get(
                "address_signals"
            )
            for signal in signals
        ),
        "has_service_pages": any(
            signal.get(
                "service_page"
            )
            for signal in signals
        ),
        "has_menu_page": any(
            signal.get(
                "menu_page"
            )
            for signal in signals
        ),
        "has_pricing_page": any(
            signal.get(
                "pricing_page"
            )
            for signal in signals
        ),
        "has_faq_content": any(
            signal.get(
                "faq_content"
            )
            for signal in signals
        ),
        "has_booking_link": any(
            signal.get(
                "booking_link"
            )
            for signal in signals
        ),
        "has_social_links": bool(
            social_links
        ),
        "social_links": (
            social_links
        ),
        "issues": all_issues,
        "error_message": (
            None
            if successful_pages
            else (
                "No HTML page was "
                "successfully crawled."
            )
        ),
    }

    result[
        "website_completeness_score"
    ] = calculate_score(result)

    return result, pages
