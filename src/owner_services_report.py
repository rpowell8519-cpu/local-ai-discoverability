"""Read-only owner report projection. Counts come from answers, never narrative copy.

One appearance is one resolved business in one valid completed answer's saved
recommendation list. Raw slots and raw answers remain unchanged. Unknown names
stay in the market but are not upgraded to verified entities.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from html import escape
import re
from typing import Any, Mapping

from src.owner_report_findings import derive_owner_content

FORMAT = "accessible_owner_services_v4"
VERSION = "owner_services_v4.0"


def provider_name(value: Any) -> str:
    name = str(value)
    return {"openai": "OpenAI", "anthropic": "Claude", "claude": "Claude",
            "google": "Gemini", "gemini": "Gemini"}.get(name.casefold(), name)


def business_key(slot: Mapping[str, Any]) -> str:
    return str(slot.get("google_place_id") or "unresolved:" + str(
        slot.get("business_name") or slot.get("raw_business_name") or "Unknown name"
    ).strip().casefold())


def cited_urls(text: str) -> list[str]:
    """Only URLs actually preserved in the answer; not reconstructed citations."""
    return sorted(set(url.rstrip(".,;:!]") for url in re.findall(r"https?://[^\s<>\)\"]+", text)))


def tied_rank(count: int, counts: list[int]) -> tuple[int, bool]:
    return 1 + sum(other > count for other in counts), counts.count(count) > 1


def comparison_partition(baseline: Mapping, followup: Mapping) -> dict:
    """New/edited questions never enter the unchanged-baseline series.

    Exact text is intentional. A mode/settings change requires a disclosed,
    separate series, not an apparently comparable before/after score.
    """
    def settings(report):
        return (report.get("mode"), report.get("models"), report.get("providers"),
                report.get("repetition_values"))
    old = {q["prompt"] for q in baseline["questions"]}
    comparable = settings(baseline) == settings(followup) and baseline.get("mode") not in (None, "unknown")
    return {"settings_comparable": comparable,
            "baseline_questions": [q for q in followup["questions"] if q["prompt"] in old],
            "new_questions": [q for q in followup["questions"] if q["prompt"] not in old],
            "removed_questions": [q for q in baseline["questions"] if q["prompt"] not in {x["prompt"] for x in followup["questions"]}]}


def _sources(payload, config):
    pages = {str(page["id"]): (audit, page) for audit in payload.get("website_evidence", {}).get("audits", []) for page in audit.get("pages", [])}
    reviews = {str(r["review_id"]): (group, r) for group in payload.get("review_evidence", {}).get("review_sets", []) for r in group.get("records", [])}
    sources = {}
    for item in config.get("sources", []):
        source = dict(item)
        if item["kind"] in ("site_check", "listing"):
            # Observations the audit made itself, not saved pages or reviews: shown with their own source and date.
            source.update(url=item.get("url"), date=item.get("date"), collection_id=None,
                          business=payload["audit"]["target_business_name"], text=item.get("observation", ""),
                          record_id=item.get("record_id") or item.get("url") or "")
        elif item["kind"] == "website":
            if item["record_id"] not in pages:
                raise ValueError(f"Missing website evidence for {item['ref']}")
            audit, record = pages[item["record_id"]]
            text = str(record.get("text_excerpt") or "")
            source.update(url=record.get("url"), date=record.get("crawled_at"),
                          collection_id=audit.get("id"), business=audit.get("business_name"), text=text)
        else:
            if item["record_id"] not in reviews:
                raise ValueError(f"Missing review evidence for {item['ref']}")
            group, record = reviews[item["record_id"]]
            text = str(record.get("review_text") or "")
            source.update(url=record.get("review_link"), date=record.get("review_datetime_utc"),
                          collection_id=record.get("import_batch_id"), business=group.get("business_name"),
                          imported_at=record.get("imported_at"), source=record.get("source"), text=text)
        excerpt = item.get("excerpt", "")
        if any(part not in text for part in [excerpt, *item.get("additional_excerpts", [])] if part):
            raise ValueError(f"Unverified exact excerpt: {item['ref']}")
        sources[item["ref"]] = source
    return sources


def build_owner_report(payload: Mapping[str, Any]) -> dict[str, Any]:
    config = deepcopy(payload.get("report", {}).get("owner_report", {}))
    audit = payload["audit"]
    target = str(audit["target_google_place_id"])
    responses = [dict(r) for r in payload["baseline_validation"]["responses"]]
    ids = [r["response_id"] for r in responses]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate saved response ID")
    valid = [r for r in responses if r.get("response_complete") and r.get("status") == "completed" and not r.get("error_message") and str(r.get("raw_response") or "").strip()]
    lookup = {}
    for r in valid:
        key = (str(r["query_id"]), provider_name(r["provider"]))
        if key in lookup:
            raise ValueError("Multiple completed answers for the same query/provider; resolve retries explicitly")
        lookup[key] = r
    appearances = defaultdict(set)
    businesses = {}
    eligible_slots = 0
    for slot in payload["recommendation_market"]["slot_evidence"]:
        if slot.get("slot_disposition") != "business":
            continue
        response = lookup.get((str(slot.get("query_id")), provider_name(slot.get("provider"))))
        if response is None:
            continue
        eligible_slots += 1
        key = business_key(slot)
        appearances[key].add(response["response_id"])
        businesses[key] = {"key": key, "name": str(slot.get("business_name") or slot.get("raw_business_name")),
                           "verified": bool(slot.get("google_place_id"))}
    target_ids = appearances[target]
    orders = sorted({int(q["base_prompt_order"]) for q in payload["methodology"].get("queries", [])} |
                    {int(r["base_prompt_order"]) for r in responses})
    questions = []
    for order in orders:
        rows = [r for r in responses if int(r["base_prompt_order"]) == order]
        texts = {r["prompt_text"] for r in rows} | {q["prompt_text"] for q in payload["methodology"].get("queries", []) if int(q["base_prompt_order"]) == order}
        if len(texts) != 1:
            raise ValueError(f"Q{order} has conflicting exact question texts")
        completed = [r for r in valid if int(r["base_prompt_order"]) == order]
        questions.append({"order": order, "prompt": next(iter(texts)), "answers": len(completed),
                          "appearances": sum(r["response_id"] in target_ids for r in completed),
                          "records": rows, "answer_ids": {r["response_id"] for r in completed}})
    question_map = {q["order"]: q for q in questions}
    services = []
    assigned = set()
    for item in config.get("services", []):
        mapped = item.get("questions")
        if mapped is None:
            services.append({**item, "questions": [], "status": "Coverage not mapped", "answers": 0, "appearances": None})
            continue
        orders_for_service = set(mapped)
        if not orders_for_service <= question_map.keys() or assigned & orders_for_service:
            raise ValueError("Primary service groups must partition existing questions without overlap")
        assigned |= orders_for_service
        count = sum(question_map[o]["answers"] for o in mapped)
        services.append({**item, "answers": count,
                         "appearances": sum(question_map[o]["appearances"] for o in mapped) if count else None,
                         "status": "Tested" if count else ("Not tested" if not mapped else "No complete answers")})
    for q in questions:
        if q["order"] not in assigned:
            services.append({"name": f"Question {q['order']} (priority mapping not confirmed)", "questions": [q["order"]],
                             "answers": q["answers"], "appearances": q["appearances"] if q["answers"] else None,
                             "status": "Tested" if q["answers"] else "No complete answers"})
    tested = [s for s in services if s["answers"]]
    visible = [s for s in tested if s["appearances"]]
    absent = [s for s in tested if not s["appearances"]]
    name = audit["target_business_name"]
    if not valid:
        headline = "There is not enough completed evidence to assess visibility."
    elif not target_ids:
        headline = f"{name} did not appear in recommendations for the questions tested."
    elif visible and absent:
        visible_names = ", ".join(s["name"] for s in visible)
        headline = (f"{name} appeared for {visible_names}, but was absent from recommendations for the other services tested."
                    if len(visible_names) < 95 else f"{name} appeared for some tested services, but not others.")
    elif len(target_ids) == len(valid):
        headline = f"{name} appeared in every completed answer in this test."
    else:
        headline = f"{name} appeared across all tested service groups, though not in every answer."
    market = []
    counts = [len(appearances[k]) for k in businesses]
    for key, business in businesses.items():
        count = len(appearances[key])
        rank, tied = tied_rank(count, counts)
        market.append({**business, "count": count, "rank": rank, "tied": tied})
    market.sort(key=lambda row: (-row["count"], row["name"].casefold()))
    providers = sorted({provider_name(r["provider"]) for r in responses} | {provider_name(p) for p in payload["methodology"].get("providers", [])})
    provider_counts = [{"name": p, "answers": sum(provider_name(r["provider"]) == p for r in valid),
                        "appearances": sum(provider_name(r["provider"]) == p and r["response_id"] in target_ids for r in valid)} for p in providers]
    repetitions = sorted({int(r["repetition"]) for r in responses})
    repetition_counts = sorted({len({r["repetition"] for r in responses if int(r["base_prompt_order"]) == q["order"] and provider_name(r["provider"]) == provider}) for q in questions for provider in providers})
    if config.get("auto_findings"):
        derive_owner_content(config=config, payload=payload, questions=questions, services=services,
                             target_id=target, target_name=name)
    sources = _sources(payload, config)
    allowed_refs = set(sources) | {f"Q{q['order']}" for q in questions} | {"TEST", "INVENTORY"}
    for section in ("strengths", "gaps", "actions", "comparisons"):
        for item in config.get(section, []):
            if not item.get("refs") or not set(item["refs"]) <= allowed_refs:
                raise ValueError(f"Missing/unknown evidence references for {section}: {item.get('title', '')}")
    required_action_fields = ("title", "need", "observation", "deliverable", "supplier", "implementer", "effort", "dependencies", "check", "refs")
    for action in config.get("actions", []):
        if any(not action.get(field) for field in required_action_fields):
            raise ValueError("Actions require a need, evidence, deliverable, responsibilities, estimate, dependencies and completion check")
    if not config.get("actions"):
        config["actions"] = [{"title": "Investigation: agree the priority and check the evidence", "need": "Choose work that supports the owner's most important services.",
            "observation": "The saved answers measure visibility; on their own they do not establish a specific website or profile problem.",
            "deliverable": "An owner-approved service-to-question map and a page-by-page evidence check before commissioning changes.",
            "supplier": "Business owner", "implementer": "Audit reviewer, with the website manager", "effort": "Estimate: 1–2 hours for initial review; implementation not estimated yet.",
            "dependencies": "Confirm service priorities, current page addresses and customer permissions for any proof used.",
            "check": "Every proposed change has an exact source, an agreed customer need and an acceptance check.", "refs": ["TEST", "INVENTORY"]}]
    cohort = []
    for member in payload.get("diagnostic", {}).get("cohort", []):
        pid = str(member.get("google_place_id") or "")
        if not pid or pid not in businesses:
            continue
        cohort.append({**member, "count": len(appearances[pid]),
                       "services": [{"name": s["name"], "count": len(appearances[pid] & set().union(*(question_map[o]["answer_ids"] for o in s["questions"]))), "answers": s["answers"]} for s in tested]})
    named_ids = set().union(*appearances.values()) if appearances else set()
    owners = []
    for item in payload.get("report", {}).get("owner_competitors", []):
        key = str(item.get("google_place_id") or "unresolved:" + str(item.get("business_name") or item["owner_name"]).casefold())
        owners.append({**item, "count": len(appearances[key]), "verified": bool(item.get("google_place_id"))})
    return {"name": name, "audit": dict(audit), "config": config, "headline": headline,
            "mode": payload["methodology"].get("benchmark_mode", config.get("benchmark_mode", "unknown")),
            "models": payload["methodology"].get("models", {}), "providers": providers,
            "repetition_values": repetitions, "repetition_counts": repetition_counts, "questions": questions, "services": services,
            "answers": len(valid), "appearances": len(target_ids), "excluded": len(responses) - len(valid),
            "no_named_answers": len({r["response_id"] for r in valid} - named_ids),
            "raw_entries": eligible_slots, "deduplicated_entries": sum(len(ids) for ids in appearances.values()),
            "provider_counts": provider_counts, "market": market, "sources": sources,
            "cohort": cohort, "owners": owners, "responses": responses,
            "website_audits": payload.get("website_evidence", {}).get("audits", []),
            "review_sets": payload.get("review_evidence", {}).get("review_sets", []),
            "target_answer_ids": target_ids,
            "answer_businesses": {
                response["response_id"]: sorted(key for key, ids in appearances.items() if response["response_id"] in ids)
                for response in valid
            }}


def evidence_index_html(payload: Mapping[str, Any]) -> str:
    """Companion index keeps complete saved answers inspectable without a huge PDF."""
    report = build_owner_report(payload)
    e = lambda value: escape(str(value or ""), quote=True)
    parts = ["<!doctype html><html lang='en'><meta charset='utf-8'><title>Saved report evidence</title><style>body{font:17px/1.6 system-ui;max-width:1000px;margin:40px auto;padding:20px;color:#15233b}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}a{color:#194db0}section{border-top:1px solid #aaa;margin-top:30px}small{overflow-wrap:anywhere}</style>",
             f"<h1>{e(report['name'])} — evidence index</h1>",
             "<p>SYNTHETIC DEMONSTRATION — not real client evidence.</p>" if report["config"].get("synthetic") else "",
             f"<p>Run: {e(report['audit']['baseline_run_id'])}. Test date: {e(report['audit']['audit_date'])}. Read-only copy of existing evidence; not new research.</p>",
             "<p>AI-cited URLs below are sources linked in saved answers, not sources independently verified by this audit. Citation does not establish cause or factual accuracy. Some provider citation metadata was not retained.</p>",
             "<h2>Saved answers from the original test</h2>"]
    parts.insert(-1, "<h2>Complete unfiltered recommendation market</h2><table><tr><th>Rank</th><th>Business / unresolved name</th><th>Answer appearances</th><th>Identity</th></tr>" + "".join(
        f"<tr><td>{'Joint ' if row['tied'] else ''}{row['rank']}</td><td>{e(row['name'])}</td><td>{row['count']}</td><td>{'Resolved' if row['verified'] else 'Unconfirmed'}</td></tr>" for row in report["market"]) + "</table>")
    for r in report["responses"]:
        parts.extend([f"<section id='{e(r['response_id'])}'><h3>Q{r['base_prompt_order']} · {e(provider_name(r['provider']))} · repetition {r['repetition']}</h3>",
                      f"<small>Answer {e(r['response_id'])}; query {e(r['query_id'])}; model {e(r['model'])}; saved {e(r.get('created_at'))}; status {e(r['status'])}; complete {e(r['response_complete'])}; SHA-256 {e(r.get('raw_response_sha256'))}</small>",
                      f"<p>{e(r['prompt_text'])}</p><pre>{e(r['raw_response'])}</pre>",
                      "<p>URLs preserved in this answer: " + (" · ".join(f"<a href='{e(u)}'>{e(u)}</a>" for u in cited_urls(r["raw_response"])) or "None preserved; this does not prove that no sources were used.") + "</p></section>"])
    parts.append("<h2>Independently reviewed website snapshots</h2><p>Saved excerpts may be truncated. Page records are not necessarily unique pages. Missing collected text is not proof of absent content.</p>")
    for audit in report["website_audits"]:
        parts.append(f"<h3>{e(audit['business_name'])}</h3><p>Audit {e(audit['id'])}; {len(audit.get('pages', []))} saved page records.</p>")
        for page in audit.get("pages", []):
            parts.append(f"<section id='{e(page['id'])}'><h4><a href='{e(page.get('url'))}'>{e(page.get('page_title') or page.get('url'))}</a></h4><small>Record {e(page['id'])}; collected {e(page.get('crawled_at'))}</small><pre>{e(page.get('text_excerpt'))}</pre></section>")
    checks = [(ref, s) for ref, s in report["sources"].items() if s["kind"] in ("site_check", "listing")]
    if checks:
        parts.append("<h2>Checks made by this audit</h2><p>Observations made from saved records or by reading the site's robots.txt on the date shown. They describe what was seen, not why.</p>")
        for ref, source in checks:
            link = f"<p><a href='{e(source['url'])}'>{e(source['url'])}</a></p>" if source.get("url") else ""
            parts.append(f"<section id='{ref}'><h3>{ref} · {e(source['title'])}</h3><p>{e(source['text'])}</p>{link}<small>Date: {e(str(source.get('date') or 'Not recorded')[:10])}</small></section>")
    parts.append("<h2>Selected customer-review sources</h2>")
    for ref, source in report["sources"].items():
        if source["kind"] == "review":
            parts.append(f"<section id='{ref}'><h3>{ref} · {e(source['business'])}</h3><p>{e(source['text'])}</p><small>Review {e(source['record_id'])}; date {e(source['date'])}; imported {e(source.get('imported_at'))}; source {e(source.get('source'))}; batch {e(source['collection_id'])}</small><p><a href='{e(source['url'])}'>Original review link</a></p></section>")
    parts.append("</html>")
    return "\n".join(parts)
