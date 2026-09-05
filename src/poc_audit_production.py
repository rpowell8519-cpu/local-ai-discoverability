from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from hmac import compare_digest
from typing import Any

from src.poc_audit_payload import payload_sha256, sha256_bytes, validate_poc_audit_payload
from src.poc_audit_pdf import PDF_RENDERER_VERSION, render_poc_audit_pdf


Assembler = Callable[[], dict[str, Any]]
Renderer = Callable[[Mapping[str, Any]], bytes]


@dataclass(frozen=True)
class PocAuditDefinition:
    """Approved inputs which make one audit eligible for production reporting."""

    key: str
    baseline_run_id: str
    target_google_place_id: str
    client_name: str
    pdf_filename: str
    assembler: Assembler
    approved_payload_sha256: str | None = None
    report_template: str = "legacy_poc"


@dataclass(frozen=True)
class ReviewablePocAudit:
    """Validated, in-memory report output; this object performs no persistence."""

    definition: PocAuditDefinition
    payload: dict[str, Any]
    payload_sha256: str
    pdf_bytes: bytes
    pdf_sha256: str
    renderer_version: str


def _definitions() -> tuple[PocAuditDefinition, ...]:
    # Imports stay local so generic payload/PDF tests do not require production data.
    from src.poc_audit_cisco_assembler import (
        RUN_ID as CISCO_RUN_ID,
        TARGET_PLACE_ID as CISCO_TARGET_ID,
        assemble_ciscos_karma_payload,
    )
    from src.poc_audit_cisco_owner_services import (
        RUN_ID as CISCO_OWNER_SERVICES_RUN_ID,
        TARGET_PLACE_ID as CISCO_OWNER_SERVICES_TARGET_ID,
        assemble_ciscos_karma_owner_services_payload,
    )
    from src.poc_audit_wild_flor import (
        RUN_ID as WILD_FLOR_RUN_ID,
        TARGET_PLACE_ID as WILD_FLOR_TARGET_ID,
        assemble_wild_flor_payload,
    )

    return (
        PocAuditDefinition(
            key="ciscos_karma_owner_services",
            baseline_run_id=CISCO_OWNER_SERVICES_RUN_ID,
            target_google_place_id=CISCO_OWNER_SERVICES_TARGET_ID,
            client_name="Cisco's Karma",
            pdf_filename="ciscos-karma-ai-visibility-report.pdf",
            assembler=assemble_ciscos_karma_owner_services_payload,
            report_template="accessible_owner_services_v1",
        ),
        PocAuditDefinition(
            key="ciscos_karma",
            baseline_run_id=CISCO_RUN_ID,
            target_google_place_id=CISCO_TARGET_ID,
            client_name="Cisco's Karma",
            pdf_filename="ciscos-karma-poc-audit-v1.pdf",
            assembler=assemble_ciscos_karma_payload,
            approved_payload_sha256=(
                "fac0cf2db538b18dc440ad732251352602d1da57b508a7306b22cdaaf6d92a31"
            ),
        ),
        PocAuditDefinition(
            key="wild_flor",
            baseline_run_id=WILD_FLOR_RUN_ID,
            target_google_place_id=WILD_FLOR_TARGET_ID,
            client_name="Wild Flor",
            pdf_filename="wild-flor-poc-audit-v1.pdf",
            assembler=assemble_wild_flor_payload,
            approved_payload_sha256=(
                "dc15dff60b057967bd9aea939de82c6219b3d9a29838f5feedeb82774a4c1a93"
            ),
        ),
    )


def list_poc_audit_definitions() -> tuple[PocAuditDefinition, ...]:
    return _definitions()


def list_report_generator_definitions() -> tuple[PocAuditDefinition, ...]:
    """Return businesses configured for the accessible owner-services report."""

    return tuple(
        definition
        for definition in _definitions()
        if definition.report_template == "accessible_owner_services_v1"
    )


def find_poc_audit_definition(
    *, baseline_run_id: str, target_google_place_id: str
) -> PocAuditDefinition | None:
    matches = [
        item
        for item in _definitions()
        if item.baseline_run_id == str(baseline_run_id)
        and item.target_google_place_id == str(target_google_place_id)
    ]
    if len(matches) > 1:
        raise ValueError("More than one POC audit definition matches this diagnostic context")
    return matches[0] if matches else None


def build_reviewable_poc_audit(
    definition: PocAuditDefinition,
    *,
    renderer: Renderer = render_poc_audit_pdf,
) -> ReviewablePocAudit:
    """Perform the single read-only production action from evidence to PDF.

    The audit-specific assembler is responsible for read-only evidence loading and
    explicit approved analyst decisions. This function validates identity, locks an
    approved golden hash where supplied, renders once, and returns exact in-memory
    bytes. It cannot freeze or otherwise write a snapshot.
    """

    payload = definition.assembler()
    validate_poc_audit_payload(payload)
    audit = payload["audit"]
    if str(audit["baseline_run_id"]) != definition.baseline_run_id:
        raise ValueError("Assembled payload baseline does not match the audit definition")
    if str(audit["target_google_place_id"]) != definition.target_google_place_id:
        raise ValueError("Assembled payload target does not match the audit definition")
    if str(audit["target_business_name"]) != definition.client_name:
        raise ValueError("Assembled payload client name does not match the audit definition")

    canonical_hash = payload_sha256(payload)
    if definition.approved_payload_sha256 and not compare_digest(
        canonical_hash, definition.approved_payload_sha256
    ):
        raise ValueError(
            "The reconstructed payload does not match its approved audit hash; "
            "review the evidence or analyst-decision change before reporting"
        )

    pdf_bytes = renderer(payload)
    if not isinstance(pdf_bytes, bytes) or not pdf_bytes.startswith(b"%PDF-"):
        raise ValueError("The report renderer did not return a valid PDF")
    return ReviewablePocAudit(
        definition=definition,
        payload=payload,
        payload_sha256=canonical_hash,
        pdf_bytes=pdf_bytes,
        pdf_sha256=sha256_bytes(pdf_bytes),
        renderer_version=PDF_RENDERER_VERSION,
    )
