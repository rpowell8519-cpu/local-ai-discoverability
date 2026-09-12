from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


WORKFLOW_SCHEMA_VERSION = "report_audit_workflow_v1"


class AuditStage(StrEnum):
    NEEDS_OWNER_BRIEF = "needs_owner_brief"
    NEEDS_BENCHMARK = "needs_benchmark"
    NEEDS_REVIEW = "needs_review"
    READY_TO_GENERATE = "ready_to_generate"
    GENERATED = "generated"


class EvidenceState(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    NOT_CHECKED = "not_checked"


@dataclass(frozen=True)
class AuditWorkflowInput:
    """The durable facts needed to decide what one report needs next."""

    target_google_place_id: str
    owner_brief_complete: bool
    benchmark_run_id: str | None = None
    benchmark_complete: bool = False
    website_evidence: EvidenceState = EvidenceState.NOT_CHECKED
    review_evidence: EvidenceState = EvidenceState.NOT_CHECKED
    reviewer_decisions_complete: bool = False
    generated_output_id: str | None = None


def derive_audit_stage(state: AuditWorkflowInput) -> AuditStage:
    """Derive one unambiguous stage; optional evidence never blocks a report."""

    if not str(state.target_google_place_id or "").strip():
        raise ValueError("A canonical Google Place ID is required")
    if state.benchmark_complete and not state.benchmark_run_id:
        raise ValueError("A completed benchmark must have a run ID")
    if state.reviewer_decisions_complete and not state.benchmark_complete:
        raise ValueError("Reviewer decisions require a completed benchmark")
    if state.generated_output_id and not state.reviewer_decisions_complete:
        raise ValueError("A generated output requires completed reviewer decisions")

    if state.generated_output_id:
        return AuditStage.GENERATED
    if not state.owner_brief_complete:
        return AuditStage.NEEDS_OWNER_BRIEF
    if not state.benchmark_complete:
        return AuditStage.NEEDS_BENCHMARK
    if not state.reviewer_decisions_complete:
        return AuditStage.NEEDS_REVIEW
    return AuditStage.READY_TO_GENERATE


def workflow_summary(state: AuditWorkflowInput) -> dict[str, Any]:
    """Return UI-ready wording for the current stage and evidence limitations."""

    stage = derive_audit_stage(state)
    next_steps = {
        AuditStage.NEEDS_OWNER_BRIEF: (
            "Complete the owner priorities",
            "Tell us what the business should be known for and add realistic customer questions.",
        ),
        AuditStage.NEEDS_BENCHMARK: (
            "Review and run AI Visibility",
            "Check the owner questions before starting the paid AI Visibility test across the selected platforms.",
        ),
        AuditStage.NEEDS_REVIEW: (
            "Prepare the report",
            "AI Visibility is complete. A reviewer now checks identities, confirms the automatically selected comparison set and records evidence limitations.",
        ),
        AuditStage.READY_TO_GENERATE: (
            "Generate the report",
            "The reviewed report inputs are complete and ready for the PDF.",
        ),
        AuditStage.GENERATED: (
            "Review or download the output",
            "A report output has been generated from this version of the reviewed evidence.",
        ),
    }
    unavailable = [
        label
        for label, evidence_state in (
            ("website evidence", state.website_evidence),
            ("customer reviews", state.review_evidence),
        )
        if evidence_state == EvidenceState.UNAVAILABLE
    ]
    not_checked = [
        label
        for label, evidence_state in (
            ("website evidence", state.website_evidence),
            ("customer reviews", state.review_evidence),
        )
        if evidence_state == EvidenceState.NOT_CHECKED
    ]
    title, body = next_steps[stage]
    return {
        "schema_version": WORKFLOW_SCHEMA_VERSION,
        "stage": stage.value,
        "title": title,
        "body": body,
        "can_generate": stage in {AuditStage.READY_TO_GENERATE, AuditStage.GENERATED},
        "unavailable_evidence": unavailable,
        "unchecked_evidence": not_checked,
    }
