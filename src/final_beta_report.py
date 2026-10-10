"""The "Final Beta" owner report: findings for discussion, built from one reviewed report.

It adds nothing a reviewer has not already decided. Recommendation counts, question labels, the
competitor lists and approved actions come from the client summary built from the reviewed
revision. This module adds four things that summary does not carry: answers that name the business
anywhere (as opposed to recommending it), the same questions in an earlier test, the sources the AI
tools cited, and a fuller reading of the business's own reviews.

Unknown stays unknown: a run saved before citations were recorded has no sources page figures, a
cited page that cannot be read is "To check", and a question never asked before has no earlier value.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.parse import urlparse

from src.ai_recommendation_intelligence import extract_numbered_recommendations

VERSION = "final-beta-v1"
MAX_BUSINESS_SITES = 6
MAX_INDEPENDENT_SOURCES = 9
MAX_THEMES = 6
MIN_READABLE_CHARS = 1500
PROVIDER_ORDER = ("OpenAI", "Claude", "Gemini")
# Hosts that many businesses share; a citation of one says nothing about a particular business.
# Themes any local business's customers write about. Each term matches the start of a word, so
# "friendl" finds "friendly" and "friendliness". A business type's own themes are added to these.
COMMON_THEMES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Friendly, helpful people", ("friendl", "welcom", "helpful", "staff", "team", "kind", "caring", "attentive")),
    ("The space and atmosphere", ("atmosphere", "vibe", "space", "decor", "design", "light", "clean", "comfortable", "cosy", "views")),
    ("Location and getting there", ("location", "station", "parking", "central", "convenient")),
    ("Quality and professionalism", ("quality", "professional", "attention to detail", "high standard", "expert", "skilled")),
    ("Food and drink", ("food", "coffee", "drinks", "menu", "lunch", "cake", "snack")),
    ("Booking and communication", ("book", "communicat", "respons", "updates", "easy to")),
    ("Value and price", ("price", "value", "afford", "reasonabl", "expensive")),
    ("Would recommend", ("recommend",)),
)
SHARED_HOSTS = ("facebook.com", "instagram.com", "linktr.ee", "google.com", "sites.google.com", "wixsite.com",
                "squarespace.com", "wordpress.com", "business.site", "x.com", "twitter.com", "youtube.com",
                "tiktok.com", "linkedin.com", "yell.com", "tripadvisor.co.uk", "tripadvisor.com", "booking.com")


def domain_of(url: Any) -> str:
    host = urlparse(str(url or "") if "//" in str(url or "") else "//" + str(url or "")).netloc.lower()
    return re.sub(r"^www\.", "", host.split(":")[0])


def name_patterns(names: Iterable[str], short_name: str = "") -> list[re.Pattern[str]]:
    """Patterns for the names a reviewer confirmed, plus the short name exactly as the business writes it.

    Confirmed names match in any letter case. The short name is matched case-sensitively, because a
    short name such as "WRAP" is also an ordinary word.
    """
    patterns = []
    for name in sorted({" ".join(str(n).split()) for n in names if str(n or "").strip()}, key=len, reverse=True):
        patterns.append(re.compile(r"(?<![A-Za-z0-9])" + re.escape(name) + r"(?![A-Za-z0-9])", re.IGNORECASE))
    short = " ".join(str(short_name or "").split())
    if len(short) >= 3:
        patterns.append(re.compile(r"(?<![A-Za-z0-9])" + re.escape(short) + r"(?![A-Za-z0-9])"))
    return patterns


def _matches(text: Any, patterns: Sequence[re.Pattern[str]]) -> bool:
    return any(p.search(str(text or "")) for p in patterns)


def count_by_question(rows: Iterable[Mapping[str, Any]], patterns: Sequence[re.Pattern[str]]) -> dict[str, dict[str, int]]:
    """For each question text: completed answers, answers naming the business, answers listing it."""
    out: dict[str, dict[str, int]] = defaultdict(lambda: {"complete": 0, "named": 0, "listed": 0})
    for row in rows:
        if str(row.get("status") or "completed") != "completed" or row.get("response_complete") is False:
            continue
        text = str(row.get("raw_response") or "")
        listed = any(_matches(item.get("raw_business_name"), patterns) for item in extract_numbered_recommendations(text))
        entry = out[" ".join(str(row.get("prompt_text") or "").split())]
        entry["complete"] += 1
        entry["listed"] += listed
        entry["named"] += listed or _matches(text, patterns)
    return dict(out)


def build_questions(summary: Mapping[str, Any], responses: Iterable[Mapping[str, Any]], patterns: Sequence[re.Pattern[str]],
                    *, previous: Mapping[str, Mapping[str, int]] | None = None,
                    owner_priorities: Iterable[str] = ()) -> list[dict[str, Any]]:
    by_text = count_by_question(responses, patterns)
    per_provider: dict[tuple[str, str], int] = Counter()
    for row in responses:
        if str(row.get("status") or "completed") == "completed" and row.get("response_complete") is not False:
            per_provider[(f"q{int(row['base_prompt_order'])}", _provider(row.get("provider")))] += 1
    rows = []
    for question in summary["questions"]:
        text = " ".join(str(question["text"]).split())
        recommended = int(question["appearances"])
        earlier = (previous or {}).get(text)
        rows.append({
            "label": question["label"], "text": question["text"], "complete": int(question["complete"]),
            "recommended": recommended,
            # A recommendation is also a mention, so the reviewed count is the floor.
            "named": max(recommended, int(by_text.get(text, {}).get("named", 0))),
            "providers": {name: {"recommended": int(question.get("provider_appearances", {}).get(name.casefold(), 0)),
                                 "complete": int(per_provider.get((question["id"], name), 0))}
                          for name in PROVIDER_ORDER if per_provider.get((question["id"], name), 0)},
            "previous": ({"recommended": int(earlier["listed"]), "complete": int(earlier["complete"])}
                         if earlier and earlier.get("complete") else None),
        })
    rows.sort(key=lambda r: (-(r["recommended"] / r["complete"] if r["complete"] else 0), r["label"].casefold()))
    tested = [str(r["label"]).casefold() for r in rows]
    # A priority counts as tested when a question carries its label, allowing for a longer or shorter wording.
    untested = [p for p in dict.fromkeys(str(p).strip() for p in owner_priorities if str(p).strip())
                if not any(p.casefold() in label or label in p.casefold() for label in tested)]
    return rows + [{"label": p, "text": None, "complete": 0, "recommended": None, "named": None, "providers": {}, "previous": None}
                   for p in untested]


def _provider(value: Any) -> str:
    text = str(value or "").strip().casefold()
    return next((name for name in PROVIDER_ORDER if name.casefold() == text), str(value or "").strip())


def build_competitors(summary: Mapping[str, Any]) -> dict[str, Any]:
    by_id = {b["id"]: b for b in summary["businesses"]}
    target = by_id[summary["target_id"]]
    total = sum(int(q["complete"]) for q in summary["questions"])
    named = [{"name": by_id[i]["name"], "recommended": int(by_id[i]["appearances"])} for i in summary["named_ids"] if i in by_id]
    ranked = sorted([by_id[i] for i in dict.fromkeys([summary["target_id"], *summary["visible_ids"], *summary["named_ids"]]) if i in by_id],
                    key=lambda b: (-int(b["appearances"]), b["id"] != summary["target_id"], str(b["name"]).casefold()))
    named_ids = set(summary["named_ids"])
    ai = [{"name": b["name"], "recommended": int(b["appearances"]), "target": b["id"] == summary["target_id"],
           "named_by_owner": b["id"] in named_ids} for b in ranked if int(b["appearances"]) > 0 or b["id"] == summary["target_id"]][:8]
    return {"total": total, "target_recommended": int(target["appearances"]), "named": named, "ai": ai,
            "unlisted": [row["name"] for row in ai if not row["target"] and not row["named_by_owner"]
                         and row["recommended"] >= int(target["appearances"])]}


def _squash(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def _site_owner(host: str, business_domains: Mapping[str, str], recommended_names: Iterable[str]) -> str | None:
    """The business a website belongs to: from the directory, or a business the answers recommended by name.

    "lunahutsauna.co.uk" is Luna Hut Sauna's own site even when that business is not in the directory;
    treating it as an independent source would suggest the client should be listed on a rival's website.
    """
    if any(host == shared or host.endswith("." + shared) for shared in SHARED_HOSTS):
        return None
    if host in business_domains:
        return business_domains[host]
    core = _squash(host.split(".")[0])
    if len(core) < 6:
        return None
    for name in recommended_names:
        squashed = _squash(re.sub(r"\(.*?\)", "", str(name)))
        if len(squashed) >= 6 and (squashed in core or core in squashed):
            return str(name)
    return None


def summarise_sources(results: Iterable[Mapping[str, Any]], *, own_domains: Iterable[str],
                      business_domains: Mapping[str, str], recommended_names: Iterable[str] = ()) -> dict[str, Any]:
    """Count, per website, the answers that cited it. Each website counts once per answer."""
    recommended_names = sorted({str(n).strip() for n in recommended_names if str(n or "").strip()}, key=len)
    own = {domain_of(d) for d in own_domains if domain_of(d)}
    answers = with_citations = citations = recorded = 0
    per_domain: Counter[str] = Counter()
    urls: dict[str, Counter[str]] = defaultdict(Counter)
    own_by_provider: Counter[str] = Counter()
    unnamed = 0
    results = list(results)
    for row in results:
        if str(row.get("status") or "completed") != "completed":
            continue
        answers += 1
        meta = row.get("report_metadata") or {}
        recorded += str(meta.get("citation_status") or "") == "measured" or bool(meta.get("citations"))
        seen: set[str] = set()
        for cite in meta.get("citations") or []:
            citations += 1
            url = str(cite.get("url") or "")
            host = domain_of(url)
            if not host or "vertexaisearch" in host:
                # Google's tool returns a redirect link and gives the website only as the title.
                host, url = domain_of(str(cite.get("title") or "").strip()), ""
            if "." not in host or host in {"uk.com", "co.uk", "org.uk"}:
                unnamed += 1
                continue
            seen.add(host)
            if url:
                urls[host][url.split("?utm_source")[0].split("#")[0]] += 1
        with_citations += bool(seen)
        for host in seen:
            per_domain[host] += 1
        if seen & own:
            own_by_provider[_provider(row.get("provider"))] += 1
    business_sites: Counter[str] = Counter()
    independent = []
    for host, count in sorted(per_domain.items(), key=lambda item: (-item[1], item[0])):
        if host in own:
            continue
        owner = _site_owner(host, business_domains, recommended_names)
        if owner:
            business_sites[owner] += count
        else:
            independent.append({"domain": host, "answers": count, "urls": [u for u, _ in urls[host].most_common(2)]})
    return {
        "available": recorded > 0, "answers": answers, "answers_with_citations": with_citations, "citations": citations,
        "websites": len(per_domain), "own_answers": _answers_citing(results, own),
        "own_by_provider": dict(own_by_provider), "business_sites": sorted(business_sites.items(), key=lambda item: (-item[1], item[0]))[:MAX_BUSINESS_SITES - 1],
        "independent": independent[:MAX_INDEPENDENT_SOURCES], "unnamed_citations": unnamed,
    }


def _answers_citing(results: Iterable[Mapping[str, Any]], own: set[str]) -> int:
    count = 0
    for row in results:
        if str(row.get("status") or "completed") != "completed":
            continue
        for cite in (row.get("report_metadata") or {}).get("citations") or []:
            host = domain_of(cite.get("url"))
            if not host or "vertexaisearch" in host:
                host = domain_of(str(cite.get("title") or "").strip())
            if host in own:
                count += 1
                break
    return count


def html_text(html: str) -> str:
    text = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", html)
    return " ".join(re.sub(r"(?s)<[^>]+>", " ", text).split())


def check_coverage(independent: list[dict[str, Any]], patterns: Sequence[re.Pattern[str]],
                   fetch: Callable[[str], str] | None, business_names: Iterable[str] = ()) -> list[dict[str, Any]]:
    """Whether the business appears on the pages the AI tools cited. Unreadable pages are "To check".

    `businesses_listed` counts the recommended businesses named on the pages read. A page naming
    several is a directory or guide; a page naming one is usually that business's own site.
    """
    others = sorted({" ".join(re.sub(r"\(.*?\)", "", str(n)).split()).casefold() for n in business_names} - {""}, key=len, reverse=True)
    others = [name for name in others if len(name) >= 5]

    def read(source: Mapping[str, Any]) -> tuple[str, int]:
        if not fetch or not source["urls"]:
            return "To check", 0
        found, readable, listed = False, False, set()
        for url in source["urls"]:
            try:
                text = html_text(fetch(url))
            except Exception:
                continue
            if len(text) < MIN_READABLE_CHARS:
                continue
            readable = True
            found = found or _matches(text, patterns)
            lowered = text.casefold()
            listed |= {name for name in others if name in lowered}
        return ("Yes" if found else "Not found" if readable else "To check"), len(listed)

    # The pages are read side by side so a slow site cannot hold up the report.
    with ThreadPoolExecutor(max_workers=6) as pool:
        outcomes = list(pool.map(read, independent))
    return [{**source, "status": status, "businesses_listed": listed} for source, (status, listed) in zip(independent, outcomes)]


def summarise_reviews(records: Iterable[Mapping[str, Any]], themes: Sequence[tuple[str, Sequence[str]]], *,
                      today: date, google_total: Any = None, google_rating: Any = None,
                      quote_ids: Iterable[str] = ()) -> dict[str, Any] | None:
    rows = {str(r.get("review_id")): r for r in records if str(r.get("review_text") or "").strip()}
    if not rows:
        return None
    reviews = list(rows.values())
    ratings = [int(round(float(r["review_rating"]))) for r in reviews if _number(r.get("review_rating")) is not None]
    dates = sorted(d for d in (_date(r.get("review_datetime_utc")) for r in reviews) if d)
    cutoff = today - timedelta(days=365)
    counted = []
    for label, terms in themes:
        patterns = [re.compile(r"(?<![a-z0-9])" + re.escape(str(t).casefold())) for t in terms if str(t).strip()]
        hits = sum(any(p.search(str(r["review_text"]).casefold()) for p in patterns) for r in reviews)
        if hits:
            counted.append((label, hits))
    counted.sort(key=lambda item: (-item[1], item[0].casefold()))
    quote = next((rows[str(i)] for i in quote_ids if str(i) in rows), None)
    if quote is None:
        # No quotation was chosen in review: use the newest five-star review of a quotable length.
        candidates = [r for r in reviews if _number(r.get("review_rating")) == 5 and 80 <= len(" ".join(str(r["review_text"]).split())) <= 320]
        quote = max(candidates, key=lambda r: _date(r.get("review_datetime_utc")) or date.min, default=None)
    return {
        "read": len(reviews), "google_total": _int(google_total), "google_rating": _number(google_rating),
        "five_star": sum(r == 5 for r in ratings), "four_star": sum(r == 4 for r in ratings),
        "three_or_below": sum(r <= 3 for r in ratings), "rated": len(ratings),
        "average": round(sum(ratings) / len(ratings), 2) if ratings else None,
        "first": dates[0] if dates else None, "last": dates[-1] if dates else None,
        "recent": sum(d >= cutoff for d in dates), "themes": counted[:MAX_THEMES], "also": counted[MAX_THEMES:MAX_THEMES + 5],
        "quote": ({"text": " ".join(str(quote["review_text"]).split()), "date": _date(quote.get("review_datetime_utc"))}
                  if quote else None),
    }


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _int(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def things_to_investigate(questions: list[dict[str, Any]], sources: Mapping[str, Any] | None) -> list[str]:
    """Plain observations worth a closer look. They restate the measurements; they are not advice."""
    asked = [q for q in questions if q["complete"]]
    out = []
    absent = [q["label"] for q in asked if q["recommended"] == 0]
    if absent:
        out.append("Not named in any answer for: " + _join(absent) + ".")
    moved = [q for q in asked if q["previous"] and q["previous"]["complete"] == q["complete"]
             and abs(q["recommended"] - q["previous"]["recommended"]) >= max(3, q["complete"] // 3)]
    for q in moved[:3]:
        out.append(f"{q['label']}: {q['previous']['recommended']} of {q['previous']['complete']} in the earlier test, "
                   f"{q['recommended']} of {q['complete']} now.")
    split = [q["label"] for q in asked if any(v["recommended"] == v["complete"] for v in q["providers"].values())
             and any(v["recommended"] == 0 for v in q["providers"].values())]
    if split:
        out.append("The AI tools disagree (one always names you, another never) for: " + _join(split[:4]) + ".")
    missing = [s["domain"] for s in (sources or {}).get("independent", []) if s.get("status") == "Not found"]
    if missing:
        out.append("Cited by the AI tools, but you were not found on the pages cited: " + _join(missing[:5]) + ".")
    return out


def _join(items: Sequence[str]) -> str:
    items = [str(i) for i in items]
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def build_final_beta_report(
    summary: Mapping[str, Any], *, responses: list[Mapping[str, Any]], results: list[Mapping[str, Any]],
    confirmed_names: Iterable[str], owner_priorities: Iterable[str] = (), own_domains: Iterable[str] = (),
    business_domains: Mapping[str, str] | None = None, previous_rows: list[Mapping[str, Any]] | None = None,
    previous_date: Any = None, review_records: Iterable[Mapping[str, Any]] = (),
    review_themes: Sequence[tuple[str, Sequence[str]]] = (), google_total: Any = None, google_rating: Any = None,
    quote_ids: Iterable[str] = (), approved_actions: Iterable[Mapping[str, Any]] = (),
    approved_findings: Iterable[Mapping[str, Any]] = (),
    fetch: Callable[[str], str] | None = None, today: date | None = None,
) -> dict[str, Any]:
    today = today or date.today()
    patterns = name_patterns([*confirmed_names, summary["business_name"]], summary.get("short_name") or "")
    previous = count_by_question(previous_rows, patterns) if previous_rows else None
    questions = build_questions(summary, responses, patterns, previous=previous, owner_priorities=owner_priorities)
    asked = [q for q in questions if q["complete"]]
    recommended_names = {str(item.get("raw_business_name") or "") for row in responses
                         for item in extract_numbered_recommendations(str(row.get("raw_response") or ""))}
    sources = summarise_sources(results, own_domains=own_domains, business_domains=business_domains or {},
                                recommended_names=recommended_names)
    if sources["available"]:
        sources["independent"] = check_coverage(sources["independent"], patterns, fetch, recommended_names)
    providers = []
    for item in summary["providers"]:
        name = _provider(item["name"])
        providers.append({"name": name, "recommended": int(item["appearances"]), "complete": int(item["complete"]),
                          "cited_own": sources["own_by_provider"].get(name, 0) if sources["available"] else None})
    providers.sort(key=lambda p: (-p["recommended"], p["name"]))
    total = sum(q["complete"] for q in asked)
    recommended = sum(q["recommended"] for q in asked)
    comparable = [q for q in asked if q["previous"] and q["previous"]["complete"] == q["complete"]]
    return {
        "version": VERSION, "business": summary["business_name"], "short_name": summary.get("short_name") or summary["business_name"],
        "location": summary.get("location"), "test_date": _date(summary.get("audit_date")), "previous_date": _date(previous_date) if comparable else None,
        "web_search": bool(summary.get("web_search_enabled")), "repetitions": summary.get("repetitions"),
        "total": total, "recommended": recommended, "named": sum(q["named"] for q in asked),
        "previous_total": ({"recommended": sum(q["previous"]["recommended"] for q in comparable), "complete": sum(q["complete"] for q in comparable),
                            "now": sum(q["recommended"] for q in comparable), "all_questions": len(comparable) == len(asked)} if comparable else None),
        "questions": questions, "providers": providers, "competitors": build_competitors(summary), "sources": sources,
        "reviews": summarise_reviews(review_records, review_themes, today=today, google_total=google_total,
                                     google_rating=google_rating, quote_ids=quote_ids),
        "actions": [{"title": str(a.get("title") or ""), "why": str(a.get("why") or ""), "action": str(a.get("action") or a.get("task") or ""),
                     "basis": str(a.get("basis") or "")} for a in approved_actions if str(a.get("title") or "").strip()],
        "observations": [{"title": str(a.get("title") or ""), "text": str(a.get("observation") or "")}
                         for a in approved_findings if str(a.get("title") or "").strip() and str(a.get("observation") or "").strip()],
        "investigate": things_to_investigate(questions, sources if sources["available"] else None),
        "models": {p["name"]: p.get("model") for p in summary["providers"]},
    }
