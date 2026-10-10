"""Suggestions drawn from the cited sources and from review volume and themes, for a reviewer to approve.

The website and review-text comparison says nothing for a business the AI tools never name, which is
when an owner most needs a place to start. These candidates use evidence the report already holds:
which websites the answers cited, whether the business is on the independent pages cited, how many
reviews it has beside the most visible businesses, and what those businesses' customers praise.

Each candidate states what was observed and where. None claims a cause, and a page that could not be
read produces no candidate: absence is only reported for a page that was read.
"""
from __future__ import annotations

import re
from datetime import date
from statistics import median
from typing import Any, Iterable, Mapping, Sequence

MAX_LISTING_CANDIDATES = 4
MIN_LISTING_ANSWERS = 3
MIN_BUSINESSES_LISTED = 2
MIN_LEADERS_FOR_VOLUME = 3
MAX_THEMES = 5
_OWNER = "Business owner"
_NO_CAUSE = "This shows where the AI tools looked; it does not show why a business was chosen."


def _candidate(**values: Any) -> dict[str, Any]:
    base = {"observation": "", "why": "", "action": "", "done_when": "", "owner": "", "confidence": "Low", "score": 0.0,
            "prevalence": "", "evidence": [], "hygiene": False, "basis": ""}
    return {**base, **values}


def listing_candidates(sources: Mapping[str, Any], *, target_name: str, read_on: date) -> list[dict[str, Any]]:
    """Independent sources the answers cited where the business was not on the pages read."""
    if not sources.get("available"):
        return []
    total = int(sources["answers"])
    # Only pages that name several recommended businesses: a directory or guide, not one rival's own website.
    missing = [s for s in sources["independent"] if s.get("status") == "Not found" and int(s["answers"]) >= MIN_LISTING_ANSWERS
               and int(s.get("businesses_listed") or 0) >= MIN_BUSINESSES_LISTED]
    out = []
    for source in missing[:MAX_LISTING_CANDIDATES]:
        domain, answers = source["domain"], int(source["answers"])
        why = (f"The AI tools cited {domain} in {answers} of {total} answers. The pages cited name {int(source['businesses_listed'])} of the "
               f"businesses they recommended, and {target_name} was not among them.")
        out.append(_candidate(
            id=f"sources:listing:{domain}", kind="action", layer="sources", signal=f"listing:{domain}",
            title=f"Check whether you can be listed on {domain}",
            observation=f"{why} {_NO_CAUSE}", why=why,
            action=f"Look at how businesses appear on {domain}. If {target_name} can be listed, add or complete the listing with accurate details.",
            done_when=f"{target_name} appears on {domain} with correct details, or you have confirmed it cannot be listed there.",
            owner=_OWNER, confidence="Medium", score=round(100 * answers / total, 1) if total else 0.0,
            prevalence=f"{answers} of {total} answers",
            evidence=[{"business": domain, "url": url, "read_on": read_on.isoformat(), "note": f"{target_name} not found on this page"}
                      for url in source.get("urls") or []],
            basis=f"Websites cited in the saved AI answers, and the cited pages read on {read_on.isoformat()}",
            implementer="Business owner, or whoever manages your listings",
            effort="Not yet estimated. It depends on whether the site accepts listings and what it asks for.",
            dependencies="Accurate business details; any fee or criteria the site sets.",
        ))
    return out


def own_site_candidate(sources: Mapping[str, Any], *, target_name: str) -> list[dict[str, Any]]:
    """The business's own website was never cited although other businesses' websites were."""
    if not sources.get("available") or int(sources.get("own_answers") or 0) > 0:
        return []
    others = [(name, int(count)) for name, count in sources.get("business_sites") or [] if int(count) >= MIN_LISTING_ANSWERS]
    if not others:
        return []
    total = int(sources["answers"])
    named = ", ".join(f"{name} ({count})" for name, count in others[:3])
    why = (f"{target_name}'s own website was cited in 0 of {total} answers, while other businesses' websites were cited: {named}.")
    return [_candidate(
        id="sources:own-site", kind="action", layer="sources", signal="own-site-not-cited",
        title="Check that AI search tools can find and read your website",
        observation=f"{why} We have not established why. A new website, a site search tools cannot read, or pages that do not "
                    "describe each service in plain words are all possible reasons.",
        why=why,
        action="Ask your website provider to confirm the site is indexed by search engines and not blocking AI search crawlers, "
               "and check each priority service has its own page describing it in the words customers use.",
        done_when="Your provider has confirmed search engines and AI search crawlers can read the site, and each priority service has a page.",
        owner="Business owner, with the website provider", confidence="Low", score=60.0, prevalence=f"0 of {total} answers",
        basis="Websites cited in the saved AI answers",
        implementer="Website provider", effort="Not yet estimated. A check is quick; new pages depend on how many are needed.",
        dependencies="Access to the website and its search settings.",
    )]


def _published(value: Any) -> int | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number == number and number >= 0 else None


def review_volume_candidate(*, target_name: str, target_reviews: Any, leaders: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Far fewer published Google reviews than the most visible businesses."""
    mine = _published(target_reviews)
    theirs = [(str(item["business_name"]), _published(item.get("google_reviews"))) for item in leaders]
    theirs = [(name, count) for name, count in theirs if count is not None]
    if mine is None or len(theirs) < MIN_LEADERS_FOR_VOLUME:
        return []
    middle = median(count for _, count in theirs)
    if middle < 10 or mine * 2 > middle:
        return []
    listed = ", ".join(f"{name} {count}" for name, count in sorted(theirs, key=lambda item: -item[1]))
    why = (f"Google shows {mine} review{'s' if mine != 1 else ''} for {target_name}. The {len(theirs)} most visible businesses have a "
           f"median of {middle:g} ({listed}).")
    return [_candidate(
        id="reviews:volume", kind="action", layer="reviews", signal="review-volume",
        title="Build up your Google reviews",
        observation=f"{why} Review counts are as shown on each Google listing when it was saved. More reviews have not been shown to "
                    "cause more AI recommendations; they give customers and AI tools more to go on.",
        why=why,
        action="Ask recent customers for a Google review as a routine, a few each week, with a direct link to your review page.",
        done_when="Asking for a review is part of your routine and your review count is noted at the next check.",
        owner=_OWNER, confidence="Low", score=50.0, prevalence=f"{mine} against a median of {middle:g}",
        basis="Published Google review totals on the saved listings",
        implementer="Business owner and team", effort="A few minutes a week once a link and a short message are set up.",
        dependencies="A direct link to your Google review page.",
    )]


def leader_theme_finding(*, target_id: str, target_name: str, leader_ids: Sequence[str], reviews: Iterable[Mapping[str, Any]],
                         themes: Sequence[tuple[str, Sequence[str]]]) -> list[dict[str, Any]]:
    """What customers of the most visible businesses mention most, beside the client's own reviews."""
    leader_set = {str(i) for i in leader_ids}
    mine, theirs = [], []
    for row in reviews:
        text = str(row.get("review_text") or "").casefold()
        if not text.strip():
            continue
        place = str(row.get("google_place_id"))
        (mine if place == str(target_id) else theirs if place in leader_set else []).append(text)
    if len(theirs) < 20:
        return []
    rows = []
    for label, terms in themes:
        patterns = [re.compile(r"(?<![a-z0-9])" + re.escape(str(t).casefold())) for t in terms if str(t).strip()]
        if not patterns:
            continue
        share = lambda texts: round(100 * sum(any(p.search(t) for p in patterns) for t in texts) / len(texts)) if texts else None
        rows.append((label, share(theirs), share(mine)))
    rows = sorted((r for r in rows if r[1]), key=lambda r: (-r[1], r[0].casefold()))[:MAX_THEMES]
    if not rows:
        return []
    leaders_text = "; ".join(f"{label.lower()} ({theirs_pct}%)" for label, theirs_pct, _ in rows)
    observation = f"Across {len(theirs)} Google reviews of the {len(leader_set)} most visible businesses, customers most often mention: {leaders_text}."
    if mine:
        observation += (f" In {target_name}'s {len(mine)} reviews: "
                        + "; ".join(f"{label.lower()} ({mine_pct}%)" for label, _, mine_pct in rows) + ".")
    observation += " Themes are counted from keywords, so read this as what customers talk about, not as a cause."
    return [_candidate(
        id="reviews:leader-themes", kind="finding", layer="reviews", signal="leader-themes",
        title="What customers of the most visible businesses talk about", observation=observation,
        why=f"Customers of the most visible businesses most often mention {rows[0][0].lower()}.",
        basis=f"Google review text: {len(mine)} of the client's reviews and {len(theirs)} reviews of the most visible businesses",
    )]


def build_visibility_candidates(*, sources: Mapping[str, Any], target_id: str, target_name: str, target_reviews: Any,
                                leaders: Sequence[Mapping[str, Any]], reviews: Iterable[Mapping[str, Any]],
                                themes: Sequence[tuple[str, Sequence[str]]], read_on: date) -> list[dict[str, Any]]:
    return [
        *own_site_candidate(sources, target_name=target_name),
        *listing_candidates(sources, target_name=target_name, read_on=read_on),
        *review_volume_candidate(target_name=target_name, target_reviews=target_reviews, leaders=leaders),
        *leader_theme_finding(target_id=target_id, target_name=target_name, leader_ids=[str(i["google_place_id"]) for i in leaders],
                              reviews=reviews, themes=themes),
    ]
