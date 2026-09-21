"""Strengths, gaps and actions for the full report, built from the same findings as the summary.

The full report (RP) needs every claim to cite a saved source and every action to carry a need,
an observation, a deliverable, responsibilities, an effort statement, dependencies and a
completion check. For a business with no hand-written content this module supplies them from
what was actually measured and observed:

* a verified finding (see src/site_checks.py) becomes a gap and an action, citing its source;
* the weakest topics become one honest "investigate" action, never a claimed defect, because a
  low appearance count alone does not show that a page is missing something;
* strengths are stated only when the data shows them.

Nothing here is written by a model, and nothing invents an effort estimate: effort is reported as
not yet estimated until someone has looked at the work.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from src.site_checks import check_contact_details, contact_finding

_STRONG_RATE = 0.5
_NEEDS_A_QUESTION_LABEL = "Question "  # unconfirmed priority mapping rows are named "Question N ..."
_NOT_ESTIMATED = "Not yet estimated. "


def target_pages(payload: Mapping[str, Any], target_id: str) -> tuple[list[dict[str, Any]], str]:
    """The saved website pages for the target and the date they were saved."""

    for audit in payload.get("website_evidence", {}).get("audits", []):
        if str(audit.get("google_place_id")) == target_id:
            checked_on = str(audit.get("completed_at") or audit.get("started_at") or payload["audit"]["audit_date"])[:10]
            return list(audit.get("pages") or []), checked_on
    return [], str(payload["audit"]["audit_date"])


def collect_findings(
    payload: Mapping[str, Any],
    owner_config: Mapping[str, Any],
    target_id: str,
    extra: Iterable[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    """Site findings already gathered plus the contact-details check, gaps first, at most three."""

    listing = dict(owner_config.get("listing_contact") or {})
    pages, checked_on = target_pages(payload, target_id)
    contact = contact_finding(
        check_contact_details(
            listing_phone=listing.get("phone"),
            listing_postcode=listing.get("postal_code") or listing.get("address"),
            pages=pages,
            checked_on=checked_on,
        )
    )
    by_kind: dict[Any, dict[str, Any]] = {}
    for finding in [*(owner_config.get("site_findings") or []), *extra]:
        by_kind.setdefault(finding.get("kind"), dict(finding))
    combined = list(by_kind.values()) + ([contact] if contact else [])
    return sorted(combined, key=lambda f: not f.get("gap"))[:3]


def _rate(service: Mapping[str, Any]) -> float:
    return service["appearances"] / service["answers"] if service["answers"] else 0.0


def _q_refs(services: Iterable[Mapping[str, Any]]) -> list[str]:
    return sorted({f"Q{int(order)}" for service in services for order in service["questions"]})


def _named(names: list[str]) -> str:
    return ", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else "".join(names)


def _source_records(
    findings: list[dict[str, Any]], target_id: str, taken: set[str]
) -> list[dict[str, Any]]:
    """Source entries for every finding; each finding gets the refs that cite it.

    References already used by the report (a hand-written W1, say) are never reused.
    """

    counters = {"S": 0, "L": 0, "W": 0}

    def ref(prefix: str) -> str:
        while True:
            counters[prefix] += 1
            key = f"{prefix}{counters[prefix]}"
            if key not in taken:
                taken.add(key)
                return key

    sources = []
    for finding in findings:
        refs = []
        if finding["kind"] == "crawler_access":
            key = ref("S")
            sources.append({
                "ref": key, "kind": "site_check", "title": "robots.txt read for the AI crawler check",
                "url": finding.get("url"), "date": finding.get("checked_on"),
                "record_id": finding.get("url") or "robots.txt", "observation": finding["observation"],
            })
            refs.append(key)
        elif finding["kind"] == "contact_details":
            listing = finding.get("listing") or {}
            details = "; ".join(
                text for text in (
                    f"Phone: {listing['phone']}" if listing.get("phone") else "",
                    f"Postcode: {listing['postcode']}" if listing.get("postcode") else "",
                ) if text
            )
            key = ref("L")
            sources.append({
                "ref": key, "kind": "listing", "title": "Google listing (saved business record)",
                "record_id": target_id, "observation": details or "Contact details from the saved listing",
            })
            refs.append(key)
            for page in finding.get("page_sources") or []:
                page_key = ref("W")
                sources.append({
                    "ref": page_key, "kind": "website", "record_id": page["page_id"],
                    "title": "Saved website page used for the contact check", "excerpt": page["excerpt"],
                })
                refs.append(page_key)
        finding["refs"] = refs
    return sources


def _verified_action(finding: Mapping[str, Any], number: int) -> dict[str, Any]:
    if finding["kind"] == "crawler_access":
        blocked = _named(list(finding.get("blocked_labels") or ["AI search tools"]))
        return {
            "title": f"{number}. Let AI search tools visit the website",
            "need": "Customers who ask an AI assistant for a recommendation can only be pointed to pages that assistant is allowed to read.",
            "observation": finding["observation"] + " This is what robots.txt says; firewall or hosting rules are not visible to this check.",
            "deliverable": f"A robots.txt that no longer blocks {blocked}, and confirmation that hosting and security settings allow these crawlers.",
            "supplier": "Website provider: access to robots.txt and the hosting or security settings. Owner: approval to allow AI search crawlers.",
            "implementer": "Website provider.",
            "effort": _NOT_ESTIMATED + "The provider should quote after seeing the current robots.txt and hosting settings.",
            "dependencies": "Access to the website's robots.txt and hosting or security settings; the owner's decision on which crawlers to allow.",
            "check": "Reading robots.txt again shows none of the listed crawlers blocked, and the provider confirms hosting and security settings allow them.",
            "refs": list(finding["refs"]),
        }
    fields = " and ".join(finding.get("fields") or ["contact details"])
    return {
        "title": f"{number}. Make the contact details match everywhere",
        "need": "Customers, and the systems that read business information, need one consistent phone number and address.",
        "observation": finding["observation"] + " Only the saved pages were read; text inside images or scripts is not visible to this check.",
        "deliverable": "A decision on the correct details, then updates so the website, Google Business Profile and main directory listings all match.",
        "supplier": "Business owner: decide which details are correct.",
        "implementer": "Website provider, and whoever manages the Google Business Profile.",
        "effort": _NOT_ESTIMATED + "It depends on how many listings carry the wrong details.",
        "dependencies": "The owner confirms the correct details; access to the website and the Google Business Profile.",
        "check": f"The same {fields} appears on the website and on the Google listing when both are read again.",
        "refs": list(finding["refs"]),
    }


def _investigation_action(
    weakest: list[Mapping[str, Any]], untested: list[str], number: int, target_name: str
) -> dict[str, Any]:
    names = [s["name"] for s in weakest]
    measured = ", ".join(f"{s['appearances']} of {s['answers']} answers for {s['name']}" for s in weakest)
    deliverable = (
        "A page-by-page check of the website and main profiles for these topics, recorded with exact sources, "
        "before any change is commissioned."
    )
    if untested:
        deliverable += f" Also agree a question for {_named(untested)}, which had none."
    return {
        "title": f"{number}. Investigate the topics where the business appeared least",
        "need": f"Customers asking about {_named(names)} need to find accurate information about {target_name}.",
        "observation": (
            f"{target_name} appeared in {measured}. The saved answers measure visibility only; on their own they do "
            "not show that a page or profile is missing information."
        ),
        "deliverable": deliverable,
        "supplier": "Business owner: confirm which of these topics matter commercially and supply accurate details.",
        "implementer": "Audit reviewer, with the website manager.",
        "effort": _NOT_ESTIMATED + "It depends on how many pages and profiles cover these topics.",
        "dependencies": "The owner confirms the priorities; current page addresses and profile access are available.",
        "check": "Every proposed change has an exact source, an agreed customer need and an acceptance check.",
        "refs": [*_q_refs(weakest), "TEST"],
    }


def derive_owner_content(
    *,
    config: dict[str, Any],
    payload: Mapping[str, Any],
    questions: list[Mapping[str, Any]],
    services: list[Mapping[str, Any]],
    target_id: str,
    target_name: str,
) -> None:
    """Add sources, strengths, gaps and actions to a report config that asked for them."""

    findings = collect_findings(payload, config, target_id)
    sources = _source_records(findings, target_id, {str(item.get("ref")) for item in config.get("sources", [])})
    tested = [s for s in services if s["answers"]]
    strengths: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []

    visible = sorted(
        (s for s in tested if s["appearances"] and _rate(s) >= _STRONG_RATE and not str(s["name"]).startswith(_NEEDS_A_QUESTION_LABEL)),
        key=lambda s: (-_rate(s), s["name"]),
    )[:2]
    if visible:
        parts = [f"{s['appearances']} of {s['answers']} answers for {s['name']}" for s in visible]
        strengths.append({
            "title": "Visible in the AI answers for " + _named([s["name"] for s in visible]),
            "body": "In this test the business appeared in " + " and in ".join(parts)
                    + ". This is a foundation to build on; the test does not show why it appeared.",
            "refs": _q_refs(visible),
        })
    for finding in findings:
        if finding["gap"]:
            continue
        strengths.append({
            "title": "AI search crawlers are not blocked by robots.txt" if finding["kind"] == "crawler_access"
                     else "The website and Google listing agree on contact details",
            "body": finding["observation"],
            "refs": list(finding["refs"]),
        })
    for finding in findings:
        if not finding["gap"]:
            continue
        if finding["kind"] == "crawler_access":
            gaps.append({
                "title": "robots.txt blocks AI search crawlers",
                "body": finding["observation"] + " Assistants that follow robots.txt may not be able to read or cite the site. "
                        "Firewall or hosting rules are not visible to this check.",
                "refs": list(finding["refs"]),
            })
        else:
            gaps.append({
                "title": "The website and Google listing give different contact details",
                "body": finding["observation"] + " Only the saved pages were read, and text inside images or scripts is not visible to this check.",
                "refs": list(finding["refs"]),
            })
    cohort = list(payload.get("diagnostic", {}).get("cohort") or [])
    audited = {str(a.get("google_place_id")) for a in payload.get("website_evidence", {}).get("audits", [])}
    missing = [str(m.get("business_name")) for m in cohort if str(m.get("google_place_id")) not in audited]
    if missing:
        gaps.append({
            "title": "Comparison businesses have no saved website evidence",
            "body": f"No saved website pages exist for {_named(missing)}, so their service pages could not be compared with "
                    f"{target_name}'s. This is a research gap, not a finding about those businesses.",
            "refs": ["INVENTORY"],
        })

    actions = [_verified_action(f, number) for number, f in enumerate((f for f in findings if f["gap"]), 1)]
    weakest = sorted(tested, key=lambda s: (_rate(s), s["name"]))[:2]
    if weakest and _rate(weakest[0]) < 1.0:
        untested = [s["name"] for s in services if s.get("status") == "Not tested"]
        actions.append(_investigation_action(weakest, untested, len(actions) + 1, target_name))

    config["sources"] = [*config.get("sources", []), *sources]
    if strengths:
        config["strengths"] = [*config.get("strengths", []), *strengths]
    if gaps:
        config["gaps"] = [*config.get("gaps", []), *gaps]
    if actions:
        config["actions"] = actions
