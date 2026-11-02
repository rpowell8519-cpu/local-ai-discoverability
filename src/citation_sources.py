"""Which websites the AI tools cite, and what kind of website each one is.

The unit is the answer: a website counts once per answer that cites it, however many links to it the
answer holds (Google's tool often returns several links to one site). Answers saved before citations
were recorded, or collected without search, are left out rather than counted as citing nothing.

A website's kind comes from, in order: the tested business's own site; the reviewed list in
citation_source_types.csv and public-body address endings; a business in our directory, or a business
the same test recommended by name; otherwise "Not yet classified". Nothing defaults to "business".
"""
from __future__ import annotations

import csv
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.parse import urlparse, urlsplit

import pandas as pd

from src.ai_recommendation_intelligence import extract_numbered_recommendations
from src.taxonomy import GROUP_LABELS

REDIRECT_HOST = "vertexaisearch.cloud.google.com"
# Link titles Google's tool sometimes gives instead of a website: they name no particular site.
UNNAMED_HOSTS = frozenset({"uk.com", "co.uk", "org.uk"})
# Hosts that many businesses share; a citation of one says nothing about a particular business.
SHARED_HOSTS = ("facebook.com", "instagram.com", "linktr.ee", "google.com", "sites.google.com", "wixsite.com",
                "squarespace.com", "wordpress.com", "business.site", "x.com", "twitter.com", "youtube.com",
                "tiktok.com", "linkedin.com", "yell.com", "tripadvisor.co.uk", "tripadvisor.com", "booking.com")
PUBLIC_ENDINGS = (".gov.uk", ".nhs.uk", ".ac.uk", ".police.uk", ".sch.uk")

CLIENT_SITE = "The tested business's own site"
BUSINESS_SITE = "Another business's website"
PUBLIC_BODY = "Public body or institution"
UNCLASSIFIED = "Not yet classified"
THIRD_PARTY_TYPES = ("Directory or comparison site", "Booking platform or marketplace", "Review site",
                     "Local guide or media", PUBLIC_BODY, "Trade or professional body",
                     "Charity or community group", "Social or forum")
SOURCE_TYPES = (*THIRD_PARTY_TYPES, BUSINESS_SITE, CLIENT_SITE, UNCLASSIFIED)
TEST_KINDS = {"core": "Client tests", "focused": "Focused monitoring", "free_check": "Website free checks"}
UNKNOWN_TYPE = "Business type not known"
CATALOG_PATH = Path(__file__).with_name("citation_source_types.csv")


def domain_of(url: Any) -> str:
    host = urlparse(str(url or "") if "//" in str(url or "") else "//" + str(url or "")).netloc.lower()
    return re.sub(r"^www\.", "", host.split(":")[0])


def squash(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def _is_redirect(url: str) -> bool:
    return domain_of(url) == REDIRECT_HOST


def cited_host(cite: Mapping[str, Any]) -> str | None:
    """The website one citation points to, or None when it names no particular site.

    Google's tool gives a redirect link and the website only as the link title; where the redirect was
    followed when it was saved, ``resolved_url`` holds the real page.
    """
    url = str(cite.get("resolved_url") or cite.get("url") or "")
    host = domain_of(url)
    if not host or host == REDIRECT_HOST or "vertexaisearch" in host:
        host = domain_of(" ".join(str(cite.get("title") or "").split()))
    if "." not in host or host in UNNAMED_HOSTS:
        return None
    return host


def cited_page(cite: Mapping[str, Any]) -> str:
    """The cited page's address, without tracking tags; empty when only a redirect link was saved."""
    url = str(cite.get("resolved_url") or cite.get("url") or "")
    if not url or _is_redirect(url):
        return ""
    return url.split("?utm_source")[0].split("#")[0]


def site_owner(host: str, business_domains: Mapping[str, str], recommended_names: Iterable[str]) -> str | None:
    """The business a website belongs to: from the directory, or a business the answers recommended by name.

    "lunahutsauna.co.uk" is Luna Hut Sauna's own site even when that business is not in the directory;
    treating it as an independent source would suggest the client should be listed on a rival's website.
    """
    if any(host == shared or host.endswith("." + shared) for shared in SHARED_HOSTS):
        return None
    if host in business_domains:
        return business_domains[host]
    core = squash(host.split(".")[0])
    if len(core) < 6:
        return None
    for name in recommended_names:
        squashed = squash(re.sub(r"\(.*?\)", "", str(name)))
        if len(squashed) >= 6 and (squashed in core or core in squashed):
            return str(name)
    return None


def load_source_types(path: Path | str = CATALOG_PATH) -> dict[str, str]:
    """The reviewed list of third-party websites by kind. Lines starting with # are notes."""
    catalog: dict[str, str] = {}
    with open(path, encoding="utf-8", newline="") as handle:
        rows = csv.reader(line for line in handle if line.strip() and not line.lstrip().startswith("#"))
        header = next(rows, None)
        if header != ["domain", "source_type"]:
            raise ValueError(f"{path}: expected a domain,source_type header")
        for row in rows:
            domain, kind = domain_of(row[0].strip()), row[1].strip()
            if kind not in THIRD_PARTY_TYPES:
                raise ValueError(f"{path}: unknown source type {kind!r} for {domain}")
            catalog[domain] = kind
    return catalog


def listed_type(host: str, catalog: Mapping[str, str]) -> str | None:
    """A third-party website's kind from the reviewed list (a domain covers its subdomains)."""
    parts = host.split(".")
    for start in range(len(parts) - 1):
        kind = catalog.get(".".join(parts[start:]))
        if kind:
            return kind
    if host.endswith(PUBLIC_ENDINGS) or host in {"gov.uk", "nhs.uk"}:
        return PUBLIC_BODY
    return None


def classify(host: str, *, own_hosts: Iterable[str], catalog: Mapping[str, str],
             business_domains: Mapping[str, str], recommended_names: Iterable[str]) -> tuple[str, str | None]:
    """(kind of website, the business it belongs to if any)."""
    if any(host == own or host.endswith("." + own) for own in own_hosts if own):
        return CLIENT_SITE, None
    kind = listed_type(host, catalog)
    if kind:
        return kind, None
    owner = site_owner(host, business_domains, recommended_names)
    if owner:
        return BUSINESS_SITE, owner
    return UNCLASSIFIED, None


def resolve_redirects(citations: list[dict[str, Any]], fetch_location: Callable[[str], str | None],
                      *, max_links: int = 30) -> int:
    """Add ``resolved_url`` to Google redirect citations, in place. Returns how many were resolved.

    Google's redirect links stop working after a few weeks, so they are followed when saved. Only
    Google's own redirect address is requested, and only its Location header is read.
    """
    todo = [cite for cite in citations[:max_links] if isinstance(cite, dict) and not cite.get("resolved_url")
            and urlsplit(str(cite.get("url") or "")).scheme == "https" and _is_redirect(str(cite.get("url") or ""))]
    if not todo:
        return 0

    def resolve(cite: dict[str, Any]) -> bool:
        try:
            location = str(fetch_location(str(cite["url"])) or "")
        except Exception:
            return False
        parts = urlsplit(location)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password \
                or _is_redirect(location):
            return False
        cite["resolved_url"] = location[:2000]
        return True

    with ThreadPoolExecutor(max_workers=min(8, len(todo))) as pool:
        return sum(pool.map(resolve, todo))


def redirect_location(url: str, *, timeout_seconds: float = 5) -> str | None:
    """Where one Google redirect link points, without following it."""
    import requests

    if urlsplit(url).scheme != "https" or not _is_redirect(url):
        return None
    response = requests.get(url, allow_redirects=False, timeout=timeout_seconds)
    return response.headers.get("location") if 300 <= response.status_code < 400 else None


def area_of(location: Any) -> str:
    """One label per tested area: "Brighton, Hove", "Brighton & Hove" and "Hove" are all Brighton & Hove."""
    words = set(re.findall(r"[a-z]+", str(location or "").casefold())) - {"and", "the", "uk"}
    if words and words <= {"brighton", "hove"}:
        return "Brighton & Hove"
    return " ".join(str(location or "").split()) or "Area not recorded"


def business_type_label(key: Any) -> str:
    return GROUP_LABELS.get(str(key or ""), UNKNOWN_TYPE)


def recommended_in(raw_response: Any) -> list[str]:
    names = (" ".join(re.sub(r"\*+", "", str(item.get("raw_business_name") or "")).split())
             for item in extract_numbered_recommendations(str(raw_response or "")))
    return list(dict.fromkeys(name for name in names if name))


def build_records(rows: Sequence[Mapping[str, Any]], *, business_domains: Mapping[str, str],
                  catalog: Mapping[str, str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(answers, citations) from saved results. One answer row per completed answer whose citations were
    recorded; one citation row per website per answer.

    Each row needs: result_id, run_id, answered_at, provider, question, status, raw_response,
    report_metadata, place_id, business, business_type, location, panel_kind and own_websites.
    """
    names_by_run: dict[Any, set[str]] = defaultdict(set)
    for row in rows:
        names_by_run[row["run_id"]].update(recommended_in(row.get("raw_response")))
    answers, citations = [], []
    for row in rows:
        meta = row.get("report_metadata") or {}
        if str(row.get("status") or "") != "completed" or meta.get("citation_status") != "measured":
            continue
        own_hosts = {domain_of(site) for site in row.get("own_websites") or [] if domain_of(site)}
        base = {
            "answer_id": str(row["result_id"]), "run_id": str(row["run_id"]),
            "answered_on": pd.Timestamp(row["answered_at"]).date(),
            "test_kind": TEST_KINDS.get(str(row.get("panel_kind") or "core"), str(row.get("panel_kind"))),
            "place_id": str(row.get("place_id") or ""), "business": str(row.get("business") or ""),
            "business_type": business_type_label(row.get("business_type")), "area": area_of(row.get("location")),
            "ai_tool": str(row.get("provider") or ""), "question": " ".join(str(row.get("question") or "").split()),
        }
        pages: dict[str, str] = {}
        unnamed = 0
        for cite in meta.get("citations") or []:
            host = cited_host(cite)
            if host is None:
                unnamed += 1
                continue
            page = cited_page(cite)
            if host not in pages or (page and not pages[host]):
                pages[host] = page
        answers.append({**base, "websites_cited": len(pages), "unnamed_links": unnamed})
        for host, page in pages.items():
            kind, owner = classify(host, own_hosts=own_hosts, catalog=catalog, business_domains=business_domains,
                                   recommended_names=names_by_run[row["run_id"]])
            citations.append({**base, "website": host, "page": page, "source_type": kind, "belongs_to": owner})
    answer_columns = ["answer_id", "run_id", "answered_on", "test_kind", "place_id", "business", "business_type",
                      "area", "ai_tool", "question", "websites_cited", "unnamed_links"]
    citation_columns = [*answer_columns[:10], "website", "page", "source_type", "belongs_to"]
    return pd.DataFrame(answers, columns=answer_columns), pd.DataFrame(citations, columns=citation_columns)


def sample(answers: pd.DataFrame) -> dict[str, Any]:
    """What a selection rests on, so a figure is never read without its base."""
    cited = answers[answers["websites_cited"] > 0]
    return {
        "businesses": cited["place_id"].nunique(), "business_names": sorted(cited["business"].unique()),
        "tests": cited["run_id"].nunique(), "questions": cited["question"].nunique(),
        "answers": len(answers), "answers_with_citations": len(cited),
        "first": cited["answered_on"].min() if len(cited) else None,
        "last": cited["answered_on"].max() if len(cited) else None,
    }


def rank_websites(answers: pd.DataFrame, citations: pd.DataFrame) -> pd.DataFrame:
    """Every cited website in the selection, most cited first.

    "Share of answers" divides by answers that cited any website. "Share, each business equal" averages
    each tested business's own share, so a business we tested five times weighs no more than one tested once.
    """
    columns = ["website", "source_type", "belongs_to", "answers", "share_of_answers", "share_each_business_equal",
               "businesses", "questions", "ai_tools", "first_seen", "last_seen", "example_page"]
    cited = answers[answers["websites_cited"] > 0]
    if cited.empty or citations.empty:
        return pd.DataFrame(columns=columns)
    per_business = cited.groupby("place_id")["answer_id"].nunique()
    grouped = citations.groupby("website")
    table = pd.DataFrame({
        "source_type": grouped["source_type"].agg(lambda s: s.mode().iat[0]),
        "belongs_to": grouped["belongs_to"].agg(lambda s: next((v for v in s if v), "")),
        "answers": grouped["answer_id"].nunique(),
        "businesses": grouped["place_id"].nunique(),
        "questions": grouped["question"].nunique(),
        "ai_tools": grouped["ai_tool"].agg(lambda s: ", ".join(sorted(set(s)))),
        "first_seen": grouped["answered_on"].min(),
        "last_seen": grouped["answered_on"].max(),
        "example_page": grouped["page"].agg(lambda s: next((v for v in s if v), "")),
    })
    table["share_of_answers"] = table["answers"] / len(cited)
    by_business = citations.groupby(["website", "place_id"])["answer_id"].nunique().unstack(fill_value=0)
    table["share_each_business_equal"] = (by_business / per_business.reindex(by_business.columns)).sum(axis=1) / len(per_business)
    return table.reset_index().sort_values(["answers", "businesses", "website"], ascending=[False, False, True])[columns]


def type_mix(answers: pd.DataFrame, citations: pd.DataFrame) -> pd.DataFrame:
    """For each kind of website: answers citing at least one, and websites of that kind."""
    cited = answers[answers["websites_cited"] > 0]
    rows = []
    for kind in SOURCE_TYPES:
        of_kind = citations[citations["source_type"] == kind]
        if of_kind.empty:
            continue
        hits = of_kind["answer_id"].nunique()
        rows.append({"source_type": kind, "answers": hits, "share_of_answers": hits / len(cited) if len(cited) else 0,
                     "websites": of_kind["website"].nunique()})
    return pd.DataFrame(rows, columns=["source_type", "answers", "share_of_answers", "websites"])


def over_time(answers: pd.DataFrame, citations: pd.DataFrame, website: str) -> pd.DataFrame:
    """For one website: each test of each business, with the share of its cited answers citing the site."""
    cited = answers[answers["websites_cited"] > 0]
    base = cited.groupby(["business", "run_id"]).agg(tested_on=("answered_on", "min"),
                                                     answers_with_citations=("answer_id", "nunique"))
    hits = citations[citations["website"] == website].groupby(["business", "run_id"])["answer_id"].nunique()
    base["answers_citing"] = hits.reindex(base.index, fill_value=0)
    base["share"] = base["answers_citing"] / base["answers_with_citations"]
    return base.reset_index().sort_values(["business", "tested_on"])[
        ["business", "tested_on", "answers_with_citations", "answers_citing", "share"]]
