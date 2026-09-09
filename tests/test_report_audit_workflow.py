import pytest

from src.report_audit_workflow import (
    AuditStage,
    AuditWorkflowInput,
    EvidenceState,
    derive_audit_stage,
    workflow_summary,
)


def state(**overrides):
    values = {
        "target_google_place_id": "place-123",
        "owner_brief_complete": False,
    }
    values.update(overrides)
    return AuditWorkflowInput(**values)


@pytest.mark.parametrize(
    ("workflow", "expected"),
    [
        (state(), AuditStage.NEEDS_OWNER_BRIEF),
        (state(owner_brief_complete=True), AuditStage.NEEDS_BENCHMARK),
        (
            state(owner_brief_complete=True, benchmark_complete=True, benchmark_run_id="run-1"),
            AuditStage.NEEDS_REVIEW,
        ),
        (
            state(
                owner_brief_complete=True,
                benchmark_complete=True,
                benchmark_run_id="run-1",
                reviewer_decisions_complete=True,
            ),
            AuditStage.READY_TO_GENERATE,
        ),
        (
            state(
                owner_brief_complete=True,
                benchmark_complete=True,
                benchmark_run_id="run-1",
                reviewer_decisions_complete=True,
                generated_output_id="output-1",
            ),
            AuditStage.GENERATED,
        ),
    ],
)
def test_stage_is_derived_from_required_work(workflow, expected):
    assert derive_audit_stage(workflow) == expected


def test_missing_optional_evidence_does_not_block_generation():
    workflow = state(
        owner_brief_complete=True,
        benchmark_complete=True,
        benchmark_run_id="run-1",
        reviewer_decisions_complete=True,
        website_evidence=EvidenceState.UNAVAILABLE,
        review_evidence=EvidenceState.UNAVAILABLE,
    )

    summary = workflow_summary(workflow)

    assert summary["can_generate"] is True
    assert summary["unavailable_evidence"] == ["website evidence", "customer reviews"]


def test_unchecked_evidence_is_distinct_from_unavailable_evidence():
    summary = workflow_summary(state())

    assert summary["unchecked_evidence"] == ["website evidence", "customer reviews"]
    assert summary["unavailable_evidence"] == []


@pytest.mark.parametrize(
    "workflow",
    [
        state(target_google_place_id=""),
        state(benchmark_complete=True),
        state(reviewer_decisions_complete=True),
        state(generated_output_id="output-1"),
    ],
)
def test_inconsistent_workflow_state_is_rejected(workflow):
    with pytest.raises(ValueError):
        derive_audit_stage(workflow)
