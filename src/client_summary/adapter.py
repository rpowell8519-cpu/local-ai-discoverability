"""Turn the platform's saved evidence into a client summary.

The full report (RP) and the client summary (LS) read the same assembled payload, so their
counts cannot disagree. This module adds no evidence. It maps the saved answers onto the
summary's record contract, chooses the comparison businesses to show, and picks three
suggested checks. The summary renderer then validates everything and refuses to produce a
report it cannot stand behind.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from src.owner_services_report import build_owner_report, provider_name
from src.report_identity import display_name
from src.owner_report_findings import collect_findings
from src.client_summary.actions import build_actions
from src.client_summary.model import from_records
from src.client_summary.pdf import render_pdf

_LABEL_LIMIT = 65
_NAME_LIMIT = 75
_MAX_COMPARISONS = 3
_GROUP_LABEL_SKIP = "Question "
_CONFIRMED_METHOD = "reviewer_confirmed_target_name"


class ClientSummaryError(ValueError):
    """The saved evidence cannot support a client summary; the message says what to fix."""


def _shorten(text: str, limit: int = _LABEL_LIMIT) -> str:
    text = " ".join(str(text).split()).rstrip("?.! ")
    text = text[:1].upper() + text[1:]
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0] or text[: limit - 1]
    return cut.rstrip(",;:- ") + "…"


def _question_labels(report: Mapping[str, Any]) -> dict[int, str]:
    """Short label per question: the owner priority it tests, else its own wording."""

    linked: dict[int, str] = {}
    for service in report["services"]:
        if str(service["name"]).startswith(_GROUP_LABEL_SKIP):
            continue
        orders = list(service.get("questions") or [])
        for order in orders:
            linked[int(order)] = (
                str(service["name"]) if len(orders) == 1 else f"{service['name']} (Q{int(order)})"
            )
    return {
        int(q["order"]): _shorten(linked.get(int(q["order"])) or q["prompt"])
        for q in report["questions"]
    }


def _provider_models(responses: Iterable[Mapping[str, Any]]) -> dict[str, str]:
    models: dict[str, set[str]] = {}
    for response in responses:
        models.setdefault(provider_name(response["provider"]), set()).add(str(response.get("model") or "unknown"))
    return {name: "; ".join(sorted(found))[:80] for name, found in models.items()}


def _confirmed_names(payload: Mapping[str, Any]) -> list[str]:
    return sorted(
        {
            str(slot.get("source_raw_business_name") or slot.get("raw_business_name"))
            for slot in payload["recommendation_market"]["slot_evidence"]
            if slot.get("resolution_method") == _CONFIRMED_METHOD
        }
    )


def _merge_findings(
    payload: Mapping[str, Any], owner_config: Mapping[str, Any], target_id: str,
    site_findings: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """The shared findings (also used by the full report), numbered E1, E2, E3."""

    findings = collect_findings(payload, owner_config, target_id, extra=site_findings)
    return [{**f, "id": f"E{number}"} for number, f in enumerate(findings, 1)]


def build_client_summary_report(
    payload: Mapping[str, Any],
    *,
    business_group: str | None = None,
    location: str | None = None,
    owner_questions: Iterable[str] = (),
    reviewer_action_titles: Iterable[str] = (),
    site_findings: Iterable[Mapping[str, Any]] = (),
    website_checked: bool = False,
    draft: bool = True,
) -> dict[str, Any]:
    """Return validated client-summary data for a saved, complete benchmark."""

    report = build_owner_report(payload)
    if report["excluded"]:
        raise ClientSummaryError(
            f"{report['excluded']} saved answer(s) are incomplete or failed. The client summary needs every "
            "planned answer, so retry the failed calls in AI Visibility first; the full report can still be produced."
        )
    if not report["answers"]:
        raise ClientSummaryError("There are no completed answers to summarise.")
    if len(report["questions"]) > 8:
        raise ClientSummaryError("The client summary shows at most eight questions.")
    owner_config = dict(payload.get("report", {}).get("owner_report") or {})
    audit = report["audit"]
    target_id = str(audit["target_google_place_id"])
    target_name = str(report["name"])
    if len(target_name) > _NAME_LIMIT:
        raise ClientSummaryError(f"The business name is longer than {_NAME_LIMIT} characters, which the summary cannot show.")

    labels = _question_labels(report)
    questions = [
        {
            "id": f"q{q['order']}",
            "label": labels[int(q["order"])],
            "text": q["prompt"],
            "complete": 0,
            "appearances": 0,
        }
        for q in report["questions"]
    ]
    measured = [
        {"id": f"q{q['order']}", "label": labels[int(q["order"])], "answers": q["answers"], "appearances": q["appearances"]}
        for q in report["questions"]
    ]
    group = business_group or owner_config.get("primary_group")
    findings = _merge_findings(payload, owner_config, target_id, site_findings)
    actions = build_actions(
        measured, business_group=group, reviewer_titles=reviewer_action_titles, findings=findings
    )

    models = _provider_models(report["responses"])
    providers = [
        {"id": name.casefold(), "name": name, "model": models.get(name, "unknown"), "complete": 0, "appearances": 0}
        for name in sorted({provider_name(r["provider"]) for r in report["responses"]})
    ]

    shown = [
        (str(item["google_place_id"]), str(item["business_name"]))
        for item in report["cohort"]
        if item.get("google_place_id") and str(item["google_place_id"]) != target_id
    ][:_MAX_COMPARISONS]
    if not shown:
        shown = [
            (row["key"], row["name"])
            for row in report["market"]
            if row["verified"] and row["key"] != target_id
        ][:_MAX_COMPARISONS]
    businesses = [{"id": target_id, "name": target_name, "appearances": 0}] + [
        {"id": place_id, "name": _shorten(name, _NAME_LIMIT), "appearances": 0} for place_id, name in shown
    ]

    records = [
        {
            "response_id": str(r["response_id"]),
            "provider_id": provider_name(r["provider"]).casefold(),
            "question_id": f"q{int(r['base_prompt_order'])}",
            "repetition": int(r["repetition"]),
            "status": "complete",
            "business_ids": list(report["answer_businesses"].get(r["response_id"], [])),
        }
        for r in report["responses"]
    ]

    owner_searches = {" ".join(str(item).split()).casefold() for item in owner_questions}
    limitations: list[str] = []
    if website_checked and not any(f.get("kind") == "crawler_access" for f in findings):
        limitations.append(
            "The website's robots.txt could not be read, so whether AI search crawlers can visit the site was not tested."
        )
    unresolved = [row for row in report["market"] if not row["verified"]]
    if unresolved:
        limitations.append(
            f"{len(unresolved)} business name(s) in the answers could not be matched to a verified business "
            "and are not shown."
        )
    confirmed = _confirmed_names(payload)
    if confirmed:
        limitations.append(
            "A reviewer confirmed that the AI answers "
            + ", ".join(f"“{name}”" for name in confirmed)
            + " refer to this business."
        )

    metadata = {
        "schema_version": 1,
        "business_name": target_name,
        "short_name": display_name(target_name)[:60],
        "draft": bool(draft),
        "location": str(location or owner_config.get("location") or "Local area"),
        "audit_date": str(audit["audit_date"]),
        "target_id": target_id,
        "repetitions": int(payload["methodology"]["repetitions"]),
        "counting_rule": "unique_business_per_response",
        "web_search_enabled": report["mode"] == "search_grounded",
        "owner_reviewed_questions": bool(owner_searches)
        and all(" ".join(q["prompt"].split()).casefold() in owner_searches for q in report["questions"]),
        "evidence_basis": "saved_response_records",
        "source_note": f"Saved AI visibility run {audit['baseline_run_id']}, tested {audit['audit_date']}. "
        "Counts are calculated from the saved answers.",
        "providers": providers,
        "questions": questions,
        "businesses": businesses,
        "evidence": [
            {"id": str(f["id"]), "observation": str(f["observation"]), "source": str(f["source"])}
            for f in findings
        ],
        "actions": actions,
        "limitations": limitations[:4],
    }
    return from_records(metadata, records)


def render_client_summary_pdf(summary: Mapping[str, Any]) -> bytes:
    return render_pdf(dict(summary))
