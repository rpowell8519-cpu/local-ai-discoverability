"""Inspectable positioning suggestions from preserved evidence and confirmed question links."""
from __future__ import annotations

from dataclasses import asdict, dataclass

from src.proposition_catalog import build_tested_intent_links, resolve_labels
from src.public_evidence_archive import AFFIRMATIVE, summarize_reviewed_evidence, verify_capture
from src.report_priorities import NOT_LINKED

VERSION = "positioning-triangulation-v1"


@dataclass(frozen=True)
class TriangulationRules:
    # Counts refer to distinct saved source records, not independent people or demand.
    min_customer_records: int = 2
    min_customer_source_classes: int = 1

    def __post_init__(self):
        for value in asdict(self).values():
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError("Support thresholds must be positive integers")


def triangulate(capture, decisions, *, owner_brief=None, run=None, questions=(),
                confirmed_question_map=None, rules=None):
    payload = verify_capture(capture)
    pid = str(capture["google_place_id"])
    rules = rules or TriangulationRules()
    for record in (owner_brief, run):
        if record and str(record.get("target_google_place_id")) != pid:
            raise ValueError("Owner brief or run belongs to another business")
    catalogue, aliases = payload["catalogue"], payload["aliases"]
    priorities = (owner_brief or {}).get("owner_context", {}).get("priority_services") or []
    intended = resolve_labels(priorities, catalogue, aliases)
    intent = build_tested_intent_links(run, questions, confirmed_question_map or {}, catalogue, aliases) if run else None
    links = intent["tested_questions"] if intent else []
    mapping_complete = bool(links) and all(
        q["mapping_basis"] == "reviewer_confirmed" and
        (q["resolution"] == "resolved" or q["raw_label"] == NOT_LINKED) for q in links)
    summaries = {s["proposition_key"]: s for s in summarize_reviewed_evidence(capture, decisions)}
    latest = {}
    for d in decisions:
        if d["evidence_id"] not in latest or d["revision"] > latest[d["evidence_id"]]["revision"]:
            latest[d["evidence_id"]] = d
    rows = []
    for prop in catalogue:
        key = prop["proposition_key"]
        summary = summaries.get(key, {})
        observations = [o for o in payload["matrix"]["observations"] if o["kind"] == "proposition_candidate" and o["field"] == key]
        customers = [o for o in observations if o["evidence_id"] in latest and
                     latest[o["evidence_id"]]["origin"] == "customer_report" and
                     latest[o["evidence_id"]]["decision"] in AFFIRMATIVE]
        records = {(o["source_class"], o["source_record_id"]) for o in customers}
        classes = {o["source_class"] for o in customers}
        owner_intended = True if any(r["proposition_key"] == key for r in intended) else None
        mapped = [q["question_order"] for q in links if q["proposition_key"] == key]
        tested = True if mapped else (False if mapping_complete else None)
        strong = len(records) >= rules.min_customer_records and len(classes) >= rules.min_customer_source_classes
        customer_candidates = [o for o in observations if o["source_class"].endswith("_reviews")]
        customer_definitive = [o for o in observations if o["evidence_id"] in latest and
                              latest[o["evidence_id"]]["origin"] == "customer_report" and
                              latest[o["evidence_id"]]["identity_confirmed"] and
                              latest[o["evidence_id"]]["decision"] != "UNCERTAIN"]
        # NO_SUPPORT describes only these reviewed excerpts; no matcher hit never proves absence.
        reviewed_no_support = bool(customer_candidates) and all(
            o in customer_definitive and latest[o["evidence_id"]]["decision"] == "NO_SUPPORT"
            for o in customer_candidates)
        if summary.get("reviewed_contradiction_count", 0):
            suggestion, reason = "CONFLICTED_EVIDENCE", "Reviewed contradiction requires investigation before positioning changes."
        elif strong and owner_intended and tested is True:
            suggestion, reason = "STRATEGIC_CORE", "Recorded owner priority, reviewed customer support above the thresholds, and confirmed tested questions."
        elif strong and owner_intended and tested is False:
            suggestion, reason = "HIDDEN_STRENGTH", "Supported owner priority has no question in this completely mapped panel; visibility outside it is unknown."
        elif strong:
            suggestion, reason = "CUSTOMER_STRENGTH", "Reviewed customer support meets the thresholds; owner intent and test coverage remain separate."
        elif owner_intended and reviewed_no_support:
            suggestion, reason = "UNPROVEN_AMBITION", "No support in the reviewed matching customer excerpts; this does not prove absence from all reviews."
        else:
            suggestion, reason = "NEEDS_REVIEW", "Available evidence or owner/test mapping is insufficient for a positioning suggestion."
        rows.append({"proposition_key": key, "proposition": prop["label"],
                     "owner_intended": owner_intended, "tested": tested, "question_orders": mapped,
                     "customer_support_records": len(records) if customer_definitive else None,
                     "customer_source_classes": len(classes) if customer_definitive else None,
                     "customer_support_evidence_ids": [o["evidence_id"] for o in customers],
                     "suggestion": suggestion, "reason": reason,
                     "evidence_review": summary,
                     "decision_ids": [str(latest[o["evidence_id"]]["id"]) for o in observations if o["evidence_id"] in latest and latest[o["evidence_id"]].get("id")],
                     "source_dates": [{k: o.get(k) for k in ("evidence_id", "source_class", "captured_at", "source_published_at")} for o in observations]})
    return {"version": VERSION, "google_place_id": pid, "capture_id": str(capture["id"]),
            "capture_sha256": capture["payload_sha256"], "rules": asdict(rules),
            "owner_revision_id": str(owner_brief["id"]) if owner_brief else None,
            "owner_priorities": intended, "known_for": (owner_brief or {}).get("known_for"),
            "tested_intent": intent, "question_mapping_complete": mapping_complete, "rows": rows,
            "limitations": ["Suggestions concern saved evidence, not AI ranking factors or causal effects.",
                            "Unlisted owner priorities remain unknown; free-text known-for wording is not auto-mapped.",
                            "Support counts distinct saved source records, not independent customers or a representative sample.",
                            "Run context is not proof of a tested question; tested intent is not search demand.",
                            "No market opportunity is inferred without separate market evidence."]}
