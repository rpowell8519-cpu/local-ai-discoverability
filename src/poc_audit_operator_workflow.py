from __future__ import annotations

import re
from collections.abc import Callable, Mapping, MutableMapping
from dataclasses import dataclass
from datetime import date
from hmac import compare_digest
from typing import TYPE_CHECKING, Any

from src.poc_audit_payload import payload_sha256, sha256_bytes, validate_poc_audit_payload
from src.poc_audit_repository import SnapshotMetadata

if TYPE_CHECKING:
    from src.poc_audit_production import ReviewablePocAudit


APPROVAL_KEYS = ("identity", "evidence", "conclusions", "client_report")
FREEZE_CONFIRMATION = "FREEZE"


@dataclass(frozen=True)
class FreezeReadiness:
    enabled: bool
    reasons: tuple[str, ...]


def count_pdf_pages(pdf_bytes: bytes) -> int:
    """Count page objects in the ReportLab PDF without a runtime PDF dependency."""
    if not isinstance(pdf_bytes, bytes) or not pdf_bytes.startswith(b"%PDF-"):
        raise ValueError("PDF preview is missing or invalid")
    count = len(re.findall(rb"/Type\s*/Page\b", pdf_bytes))
    if count < 1:
        raise ValueError("PDF preview contains no pages")
    return count


def sync_payload_session(
    state: MutableMapping[str, Any],
    *,
    payload: Mapping[str, Any],
    canonical_hash: str,
    representation_version: str,
) -> bool:
    """Bind session approvals and preview bytes to one canonical payload hash."""
    previous = state.get("canonical_hash")
    changed = (
        previous is not None and not compare_digest(str(previous), canonical_hash)
    ) or (
        state.get("representation_version") is not None
        and state.get("representation_version") != representation_version
    )
    state["canonical_payload"] = payload
    state["canonical_hash"] = canonical_hash
    state["representation_version"] = representation_version
    if changed:
        for key in (
            "pdf_bytes", "pdf_sha256", "pdf_payload_hash", "pdf_page_count",
            "pdf_filename", "stored_snapshot",
        ):
            state.pop(key, None)
        state["approvals"] = {key: False for key in APPROVAL_KEYS}
        state["confirmation"] = ""
    else:
        state.setdefault("approvals", {key: False for key in APPROVAL_KEYS})
        state.setdefault("confirmation", "")
    return changed


def bind_pdf_preview(
    state: MutableMapping[str, Any],
    *,
    pdf_bytes: bytes,
    canonical_hash: str,
    filename: str,
    representation_version: str,
) -> dict[str, Any]:
    page_count = count_pdf_pages(pdf_bytes)
    pdf_hash = sha256_bytes(pdf_bytes)
    state.update({
        "pdf_bytes": pdf_bytes,
        "pdf_sha256": pdf_hash,
        "pdf_payload_hash": canonical_hash,
        "pdf_page_count": page_count,
        "pdf_filename": filename,
        "pdf_renderer_version": representation_version,
    })
    approvals = state.setdefault("approvals", {key: False for key in APPROVAL_KEYS})
    approvals["client_report"] = False
    return {"pdf_sha256": pdf_hash, "page_count": page_count, "size_bytes": len(pdf_bytes)}


def bind_reviewable_report(
    state: MutableMapping[str, Any], report: "ReviewablePocAudit"
) -> dict[str, Any]:
    """Bind one validated production result to session state without persistence."""
    sync_payload_session(
        state,
        payload=report.payload,
        canonical_hash=report.payload_sha256,
        representation_version=report.renderer_version,
    )
    details = bind_pdf_preview(
        state,
        pdf_bytes=report.pdf_bytes,
        canonical_hash=report.payload_sha256,
        filename=report.definition.pdf_filename,
        representation_version=report.renderer_version,
    )
    if not compare_digest(details["pdf_sha256"], report.pdf_sha256):
        raise ValueError("Production report PDF hash changed while binding session state")
    return details


def freeze_readiness(
    *,
    payload_valid: bool,
    canonical_hash: str | None,
    preview_bytes: bytes | None,
    preview_payload_hash: str | None,
    approvals: Mapping[str, bool],
    confirmation: str,
    frozen_by: str,
    existing_snapshot: Mapping[str, Any] | None,
) -> FreezeReadiness:
    reasons: list[str] = []
    if not payload_valid or not canonical_hash:
        reasons.append("Canonical payload validation has not passed")
    if not preview_bytes:
        reasons.append("Generate the PDF preview")
    elif not compare_digest(str(preview_payload_hash or ""), str(canonical_hash or "")):
        reasons.append("The PDF preview belongs to an older payload")
    missing = [key for key in APPROVAL_KEYS if not bool(approvals.get(key))]
    if missing:
        reasons.append("Complete all approval confirmations")
    if confirmation != FREEZE_CONFIRMATION:
        reasons.append("Enter the exact freeze confirmation")
    if not frozen_by.strip():
        reasons.append("Provide the operator identity")
    if existing_snapshot is not None:
        reasons.append("A frozen snapshot already exists for this AI run")
    return FreezeReadiness(enabled=not reasons, reasons=tuple(reasons))


def revision_one_metadata(
    payload: Mapping[str, Any], *, frozen_by: str, pdf_filename: str
) -> SnapshotMetadata:
    validate_poc_audit_payload(payload)
    audit = payload["audit"]
    revision = payload["revision"]
    if int(revision["snapshot_revision"]) != 1 or revision.get("supersedes_snapshot_id"):
        raise ValueError("The initial freeze requires revision 1 without a parent")
    return SnapshotMetadata(
        ai_run_id=str(audit["baseline_run_id"]), snapshot_revision=1,
        supersedes_snapshot_id=None, revision_reason=str(revision["revision_reason"]),
        target_google_place_id=str(audit["target_google_place_id"]),
        target_business_name=str(audit["target_business_name"]),
        audit_date=date.fromisoformat(str(audit["audit_date"])),
        frozen_by=frozen_by.strip(), pdf_filename=pdf_filename,
    )


def freeze_initial_snapshot(
    *,
    state: MutableMapping[str, Any],
    payload: Mapping[str, Any],
    canonical_hash: str,
    frozen_by: str,
    existing_snapshots: list[Mapping[str, Any]],
    create: Callable[..., Mapping[str, Any]],
    load: Callable[[str], Mapping[str, Any] | None],
) -> Mapping[str, Any]:
    readiness = freeze_readiness(
        payload_valid=True, canonical_hash=canonical_hash,
        preview_bytes=state.get("pdf_bytes"),
        preview_payload_hash=state.get("pdf_payload_hash"),
        approvals=state.get("approvals", {}), confirmation=str(state.get("confirmation", "")),
        frozen_by=frozen_by,
        existing_snapshot=(existing_snapshots[0] if existing_snapshots else None),
    )
    if not readiness.enabled:
        raise ValueError("Freeze is not ready: " + "; ".join(readiness.reasons))
    if not compare_digest(payload_sha256(payload), canonical_hash):
        raise ValueError("Canonical payload hash changed before freeze")
    pdf_bytes = state["pdf_bytes"]
    if not compare_digest(sha256_bytes(pdf_bytes), str(state.get("pdf_sha256") or "")):
        raise ValueError("Reviewed PDF bytes changed before freeze")
    metadata = revision_one_metadata(
        payload, frozen_by=frozen_by, pdf_filename=str(state["pdf_filename"])
    )
    inserted = create(
        payload=payload, expected_payload_sha256=canonical_hash,
        pdf_bytes=pdf_bytes, metadata=metadata,
    )
    stored = load(str(inserted["id"]))
    if stored is None:
        raise RuntimeError("Snapshot was inserted but could not be reloaded")
    state["stored_snapshot"] = stored
    return stored


def stored_pdf_bytes(snapshot: Mapping[str, Any]) -> bytes:
    value = snapshot.get("pdf_bytes")
    if isinstance(value, memoryview):
        value = value.tobytes()
    if not isinstance(value, bytes) or not value.startswith(b"%PDF-"):
        raise ValueError("Stored snapshot does not contain a valid PDF")
    return value
