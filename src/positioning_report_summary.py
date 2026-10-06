"""Compact, excerpt-free projection of already-reviewed positioning evidence for a report.

Read-only: this never writes an evidence decision or makes a new judgment. Every candidate it
returns reflects decisions a human operator already made in Evidence Review / Positioning. A
reviewer must still explicitly choose which candidates reach a client report (see step 5 of
app/pages/10_AI_Report_Generator.py) - this module only prepares that candidate list and keeps raw
excerpt text out of it. Returns [] for the overwhelming majority of businesses today, since most
have no archived capture or no reviewed decisions yet; existing reports are unaffected until an
operator has actually reviewed evidence for that specific business.
"""
from __future__ import annotations

from typing import Any, Mapping

from src.ai_visibility_repository import get_run_queries
from src.evidence_foundations_repository import load_confirmed_question_map
from src.intervention_repository import intervention_storage_ready, list_interventions
from src.positioning_repository import load_owner_brief
from src.positioning_triangulation import triangulate
from src.public_evidence_archive_repository import list_captures, list_decisions, load_capture

# A suggestion with no reviewed evidence behind it (NEEDS_REVIEW with nothing recorded) is
# operator triage noise, not something to show a client. A linked intervention is reportable
# regardless of its triangulation label - rob may want to disclose "we recorded and are tracking
# this action" even while evidence is still thin.
_REPORTABLE_SUGGESTIONS = {"STRATEGIC_CORE", "HIDDEN_STRENGTH", "CUSTOMER_STRENGTH", "UNPROVEN_AMBITION", "CONFLICTED_EVIDENCE"}


def build_positioning_candidates(
    place_id: str, *, benchmark_run: Mapping[str, Any] | None = None, engine=None,
) -> list[dict[str, Any]]:
    """Reviewed positioning rows and recorded interventions, ready for reviewer inclusion.

    `benchmark_run` should be the report's own attached benchmark, not an arbitrary one, so a
    report's "tested intent" claim stays consistent with the AI-visibility numbers in that same
    report. Pass None when no benchmark is attached yet; tested intent is then unknown for every
    row rather than silently using an unrelated run.

    Returns [] whenever there is no archived capture, or every row is both unsupported by
    reviewed evidence and has no recorded intervention linked to it - the common case today,
    since reviewed decisions are rare. A recorded intervention makes its proposition reportable
    even with zero reviewed decisions: that is a deliberate choice, not an oversight.
    """

    place_id = str(place_id)
    captures = list_captures(place_id, engine=engine)
    if not captures:
        return []
    capture = load_capture(str(captures[0]["id"]), engine=engine)
    decisions = list_decisions(str(capture["id"]), engine=engine)
    brief = load_owner_brief(place_id, engine=engine)
    run_id = str(benchmark_run["id"]) if benchmark_run else None
    questions = get_run_queries(run_id).to_dict("records") if run_id else []
    confirmed = load_confirmed_question_map(run_id, place_id, engine=engine) if run_id else {}
    view = triangulate(capture, decisions, owner_brief=brief, run=benchmark_run,
                       questions=questions, confirmed_question_map=confirmed)
    interventions = list_interventions(place_id, engine=engine) if intervention_storage_ready(engine=engine) else []
    linked_by_proposition: dict[str, list[dict[str, Any]]] = {}
    for action in interventions:
        linked_by_proposition.setdefault(str(action["proposition_key"]), []).append(action["record"])

    candidates = []
    for row in view["rows"]:
        linked = linked_by_proposition.get(row["proposition_key"], [])
        if row["suggestion"] not in _REPORTABLE_SUGGESTIONS and not linked:
            continue
        candidates.append({
            "proposition_key": row["proposition_key"],
            "proposition": row["proposition"],
            "suggestion": row["suggestion"],
            "reason": row["reason"],
            "owner_intended": row["owner_intended"],
            "tested": row["tested"],
            "customer_support_records": row["customer_support_records"],
            "customer_source_classes": row["customer_source_classes"],
            "interventions": [
                {
                    "hypothesis": str(action["hypothesis"]),
                    "status": str(action["status"]),
                    "planned_date": action.get("planned_date"),
                    "implemented_date": action.get("implemented_date"),
                }
                for action in linked
            ],
            "capture_id": str(capture["id"]),
            "capture_archived_at": str(capture["archived_at"]),
        })
    return candidates
