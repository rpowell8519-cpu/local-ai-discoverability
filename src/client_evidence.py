"""One plain-language view of a client's evidence: where they stand, what needs an operator, what
the reviewed evidence suggests and what is being done about it.

Read-only. It restates what the focused-monitoring, evidence-review and positioning layers already
hold and adds no judgment of its own: an unconfirmed name is never counted, a missing answer is
never a zero, and a positioning suggestion appears only once a person has reviewed the evidence.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

SUGGESTION_WORDING = {
    "STRATEGIC_CORE": "A stated priority that customers back up and that has been tested",
    "HIDDEN_STRENGTH": "A stated priority that customers back up, but no question has tested it yet",
    "CUSTOMER_STRENGTH": "Customers praise this, whether or not the owner named it as a priority",
    "UNPROVEN_AMBITION": "A stated priority that the reviewed customer excerpts do not yet support",
    "CONFLICTED_EVIDENCE": "The reviewed evidence disagrees; investigate before changing anything",
}


def _goals(summaries: Iterable[Mapping[str, Any]], target_id: str) -> list[dict[str, Any]]:
    """The newest usable focused result for each question family and provider."""
    newest: dict[tuple[str, str], dict[str, Any]] = {}
    for summary in sorted(summaries, key=lambda s: str(s["started_at"]), reverse=True):
        for row in summary["rows"]:
            key = (row["family"], row["provider"])
            if key in newest or str(row["google_place_id"]) != target_id:
                continue
            if not row["expected_answers"] or row["completed_answers"] != row["expected_answers"]:
                continue
            others = [other for other in summary["rows"]
                      if (other["family"], other["provider"]) == key and str(other["google_place_id"]) != target_id]
            newest[key] = {
                "goal": row["family"], "provider": row["provider"], "measured_at": summary["started_at"],
                "run_id": summary["run_id"], "recommended": row["appearances"], "answers": row["completed_answers"],
                "compared_with": sorted(({
                    "business": other["business_name"], "recommended": other["appearances"],
                    "answers": other["completed_answers"],
                    # Answers naming something that may be this business; not counted until confirmed.
                    "unconfirmed": sum(int(name["recommendations"]) for name in other["unapproved_possible_names"]),
                } for other in others), key=lambda item: (-item["recommended"] - item["unconfirmed"], item["business"])),
            }
    return sorted(newest.values(), key=lambda goal: (goal["goal"], goal["provider"]))


def _names_to_confirm(summaries: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    found: dict[tuple[str, str], dict[str, Any]] = {}
    for summary in summaries:
        for row in summary["rows"]:
            for name in row["unapproved_possible_names"]:
                item = found.setdefault((row["business_name"], name["name"]), {
                    "ai_name": name["name"], "may_be": row["business_name"], "answers": 0, "why": name["reason"]})
                item["answers"] += int(name["recommendations"])
    return sorted(found.values(), key=lambda item: (-item["answers"], item["may_be"], item["ai_name"]))


def build_client_evidence(*, business: Mapping[str, Any], brief: Mapping[str, Any] | None,
                          summaries: list[Mapping[str, Any]], incomplete_waves: int,
                          capture: Mapping[str, Any] | None, decisions: list[Mapping[str, Any]],
                          positioning: Mapping[str, Any] | None, actions: list[Mapping[str, Any]],
                          has_benchmark: bool = False) -> dict[str, Any]:
    target_id = str(business["google_place_id"])
    goals = _goals(summaries, target_id)
    context = (brief or {}).get("owner_context") or {}
    stated = [str(goal).strip() for goal in (context.get("priority_services") or []) if str(goal).strip()]
    tested = {goal["goal"] for goal in goals}

    excerpts = [o for o in ((capture or {}).get("payload") or {}).get("matrix", {}).get("observations", [])
                if o["kind"] == "proposition_candidate"]
    decided = {str(d["evidence_id"]) for d in decisions}
    undecided = [o for o in excerpts if str(o["evidence_id"]) not in decided]
    customer_undecided = sum(1 for o in undecided if o["source_class"] != "website")
    names = _names_to_confirm(summaries)

    tasks: list[dict[str, str]] = []
    if not brief or not stated:
        tasks.append({"task": "Record what the owner wants to be known for",
                      "detail": "Nothing can be compared with the owner's goals until they are saved in the report's owner brief.",
                      "page": "pages/10_AI_Report_Generator.py"})
    if capture is None:
        tasks.append({"task": "Save a copy of this business's website and review evidence",
                      "detail": "Evidence Review, then \"Archive current saved evidence\". Nothing is collected or paid for.",
                      "page": "pages/12_Evidence_Review.py"})
    elif undecided:
        tasks.append({"task": f"Review {len(undecided)} excerpt{'s' if len(undecided) != 1 else ''}"
                              f" ({customer_undecided} from customers)",
                      "detail": "Each one needs a decision on whether it supports the topic. Customer excerpts come first.",
                      "page": "pages/12_Evidence_Review.py"})
    if stated and not goals and not has_benchmark:
        tasks.append({"task": "Measure the owner's goals",
                      "detail": "Nothing has been measured yet. Start the report's benchmark, or a small focused test.",
                      "page": "pages/10_AI_Report_Generator.py"})
    elif goals and set(stated) - tested:
        missing = sorted(set(stated) - tested)
        tasks.append({"task": f"{len(missing)} owner goal{'s have' if len(missing) != 1 else ' has'} no completed test",
                      "detail": "; ".join(missing), "page": "pages/14_Focused_Monitoring.py"})
    if incomplete_waves:
        tasks.append({"task": f"{incomplete_waves} saved test{'s' if incomplete_waves != 1 else ''} did not finish",
                      "detail": "Their answers are not used above. Retry or ignore them in Focused Monitoring.",
                      "page": "pages/14_Focused_Monitoring.py"})

    rows = (positioning or {}).get("rows") or []
    suggestions = [{"topic": row["proposition"], "meaning": SUGGESTION_WORDING[row["suggestion"]],
                    "owner_priority": row["owner_intended"], "customer_records": row["customer_support_records"]}
                   for row in rows if row["suggestion"] in SUGGESTION_WORDING]

    return {
        "business": business["business_name"],
        "stated_goals": stated,
        "goals": goals,
        "total_recommended": sum(goal["recommended"] for goal in goals),
        "total_answers": sum(goal["answers"] for goal in goals),
        "tasks": tasks,
        "names_to_confirm": names,
        "excerpts": {"total": len(excerpts), "undecided": len(undecided), "has_capture": capture is not None},
        "suggestions": suggestions,
        "topics_awaiting_review": sum(1 for row in rows if row["suggestion"] not in SUGGESTION_WORDING),
        "actions": [{"finding": a["record"].get("finding"), "action": a["record"].get("hypothesis"),
                     "status": a["record"].get("status"), "planned": a["record"].get("planned_date"),
                     "done": a["record"].get("implemented_date")} for a in actions],
    }
