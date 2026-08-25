from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from hmac import compare_digest
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from src.database import get_engine
from src.poc_audit_payload import (
    SCHEMA_VERSION,
    canonical_json_bytes,
    payload_sha256,
    sha256_bytes,
    validate_poc_audit_payload,
)


class SnapshotPersistenceError(ValueError):
    """Raised before or during an immutable snapshot insertion."""


class SnapshotConflictError(SnapshotPersistenceError):
    """Raised when another snapshot makes the revision stale."""


@dataclass(frozen=True)
class SnapshotMetadata:
    ai_run_id: str
    snapshot_revision: int
    supersedes_snapshot_id: str | None
    revision_reason: str
    target_google_place_id: str
    target_business_name: str
    audit_date: date
    frozen_by: str
    pdf_filename: str
    snapshot_id: str | None = None


_INSERT = text(
    """
    insert into poc_audit_snapshots (
        id,
        schema_version,
        ai_run_id,
        snapshot_revision,
        supersedes_snapshot_id,
        revision_reason,
        target_google_place_id,
        target_business_name,
        audit_date,
        report_payload,
        report_payload_sha256,
        pdf_bytes,
        pdf_sha256,
        pdf_filename,
        pdf_mime_type,
        frozen_by
    )
    values (
        :id,
        :schema_version,
        :ai_run_id,
        :snapshot_revision,
        :supersedes_snapshot_id,
        :revision_reason,
        :target_google_place_id,
        :target_business_name,
        :audit_date,
        cast(:report_payload as jsonb),
        :report_payload_sha256,
        :pdf_bytes,
        :pdf_sha256,
        :pdf_filename,
        'application/pdf',
        :frozen_by
    )
    returning
        id,
        schema_version,
        ai_run_id,
        snapshot_revision,
        supersedes_snapshot_id,
        revision_reason,
        target_google_place_id,
        target_business_name,
        audit_date,
        report_payload_sha256,
        pdf_sha256,
        pdf_filename,
        pdf_mime_type,
        frozen_by,
        frozen_at
    """
)

_LATEST_FOR_UPDATE = text(
    """
    select id, snapshot_revision
    from poc_audit_snapshots
    where ai_run_id = :ai_run_id
    order by snapshot_revision desc
    limit 1
    for update
    """
)

_GET = text(
    """
    select *
    from poc_audit_snapshots
    where id = :snapshot_id
    """
)

_LIST = text(
    """
    select
        id,
        schema_version,
        ai_run_id,
        snapshot_revision,
        supersedes_snapshot_id,
        revision_reason,
        target_google_place_id,
        target_business_name,
        audit_date,
        report_payload_sha256,
        pdf_sha256,
        pdf_filename,
        pdf_mime_type,
        frozen_by,
        frozen_at
    from poc_audit_snapshots
    where (
        cast(:ai_run_id as uuid) is null
        or ai_run_id = cast(:ai_run_id as uuid)
    )
    and (
        :target_google_place_id is null
        or target_google_place_id = :target_google_place_id
    )
    order by frozen_at desc, snapshot_revision desc
    """
)


def _clean_uuid(value: str | None, field: str) -> str | None:
    if value is None:
        return None
    try:
        return str(uuid.UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise SnapshotPersistenceError(
            f"{field} must be a valid UUID"
        ) from exc


def _validate_pdf(pdf_bytes: bytes) -> bytes:
    if not isinstance(pdf_bytes, bytes):
        raise SnapshotPersistenceError("PDF input must be bytes")
    if not pdf_bytes.startswith(b"%PDF-"):
        raise SnapshotPersistenceError("PDF input has no PDF header")
    if not pdf_bytes.rstrip().endswith(b"%%EOF"):
        raise SnapshotPersistenceError("PDF input has no PDF EOF marker")
    return pdf_bytes


def _payload_metadata(payload: Mapping[str, Any]) -> dict[str, Any]:
    audit = payload.get("audit", {})
    revision = payload.get("revision", {})
    try:
        audit_date = date.fromisoformat(str(audit.get("audit_date")))
    except (TypeError, ValueError) as exc:
        raise SnapshotPersistenceError(
            "payload audit.audit_date must be an ISO date"
        ) from exc

    return {
        "ai_run_id": str(audit.get("baseline_run_id") or ""),
        "snapshot_revision": revision.get("snapshot_revision"),
        "supersedes_snapshot_id": (
            revision.get("supersedes_snapshot_id") or None
        ),
        "revision_reason": str(
            revision.get("revision_reason") or ""
        ),
        "target_google_place_id": str(
            audit.get("target_google_place_id") or ""
        ),
        "target_business_name": str(
            audit.get("target_business_name") or ""
        ),
        "audit_date": audit_date,
    }


def _validate_metadata_agreement(
    payload: Mapping[str, Any],
    metadata: SnapshotMetadata,
) -> dict[str, Any]:
    validate_poc_audit_payload(payload)
    payload_values = _payload_metadata(payload)
    supplied_values = {
        key: getattr(metadata, key)
        for key in payload_values
    }

    if payload_values != supplied_values:
        mismatches = [
            key
            for key in payload_values
            if payload_values[key] != supplied_values[key]
        ]
        raise SnapshotPersistenceError(
            "Snapshot metadata does not agree with payload: "
            + ", ".join(mismatches)
        )

    if not metadata.revision_reason.strip():
        raise SnapshotPersistenceError("revision_reason is required")
    if not metadata.frozen_by.strip():
        raise SnapshotPersistenceError("frozen_by is required")
    if not metadata.pdf_filename.strip():
        raise SnapshotPersistenceError("pdf_filename is required")

    ai_run_id = _clean_uuid(metadata.ai_run_id, "ai_run_id")
    supersedes = _clean_uuid(
        metadata.supersedes_snapshot_id,
        "supersedes_snapshot_id",
    )
    snapshot_id = _clean_uuid(metadata.snapshot_id, "snapshot_id")

    return {
        "ai_run_id": ai_run_id,
        "supersedes_snapshot_id": supersedes,
        "snapshot_id": snapshot_id or str(uuid.uuid4()),
    }


def _validate_lineage(
    *,
    latest: Mapping[str, Any] | None,
    metadata: SnapshotMetadata,
) -> None:
    if latest is None:
        if metadata.snapshot_revision != 1:
            raise SnapshotPersistenceError(
                "The first snapshot for an AI run must be revision 1"
            )
        if metadata.supersedes_snapshot_id is not None:
            raise SnapshotPersistenceError(
                "Revision 1 cannot supersede another snapshot"
            )
        return

    latest_revision = int(latest["snapshot_revision"])
    expected_revision = latest_revision + 1
    latest_id = str(latest["id"])

    if metadata.snapshot_revision != expected_revision:
        raise SnapshotConflictError(
            f"Revision {metadata.snapshot_revision} is stale or skipped; "
            f"the required revision is {expected_revision}"
        )
    if str(metadata.supersedes_snapshot_id or "") != latest_id:
        raise SnapshotConflictError(
            "supersedes_snapshot_id must identify the latest snapshot"
        )


def create_snapshot(
    *,
    payload: Mapping[str, Any],
    expected_payload_sha256: str,
    pdf_bytes: bytes,
    metadata: SnapshotMetadata,
    engine: Engine | None = None,
) -> dict[str, Any]:
    """Atomically persist one validated payload and its final PDF."""

    identifiers = _validate_metadata_agreement(payload, metadata)
    pdf = _validate_pdf(pdf_bytes)
    canonical_payload = canonical_json_bytes(payload)
    canonical_payload_hash = payload_sha256(payload)
    if not compare_digest(
        canonical_payload_hash,
        str(expected_payload_sha256).lower(),
    ):
        raise SnapshotPersistenceError(
            "Canonical payload SHA-256 does not match the approved hash"
        )
    pdf_hash = sha256_bytes(pdf)
    database = engine or get_engine()

    parameters = {
        "id": identifiers["snapshot_id"],
        "schema_version": SCHEMA_VERSION,
        "ai_run_id": identifiers["ai_run_id"],
        "snapshot_revision": metadata.snapshot_revision,
        "supersedes_snapshot_id": identifiers[
            "supersedes_snapshot_id"
        ],
        "revision_reason": metadata.revision_reason,
        "target_google_place_id": metadata.target_google_place_id,
        "target_business_name": metadata.target_business_name,
        "audit_date": metadata.audit_date,
        "report_payload": canonical_payload.decode("utf-8"),
        "report_payload_sha256": canonical_payload_hash,
        "pdf_bytes": pdf,
        "pdf_sha256": pdf_hash,
        "pdf_filename": metadata.pdf_filename,
        "frozen_by": metadata.frozen_by,
    }

    try:
        with database.begin() as connection:
            # Serialize revision allocation for this run, including the
            # first insertion where no row exists to lock yet.
            connection.execute(
                text(
                    "select pg_advisory_xact_lock("
                    "hashtextextended(:ai_run_id, 0))"
                ),
                {"ai_run_id": identifiers["ai_run_id"]},
            )
            latest = connection.execute(
                _LATEST_FOR_UPDATE,
                {"ai_run_id": identifiers["ai_run_id"]},
            ).mappings().first()
            _validate_lineage(latest=latest, metadata=metadata)
            inserted = connection.execute(
                _INSERT,
                parameters,
            ).mappings().one()
    except IntegrityError as exc:
        raise SnapshotConflictError(
            "Snapshot insertion conflicted with database integrity "
            "constraints; no snapshot was written"
        ) from exc

    return dict(inserted)


def get_snapshot(
    snapshot_id: str,
    *,
    engine: Engine | None = None,
) -> dict[str, Any] | None:
    database = engine or get_engine()
    clean_id = _clean_uuid(snapshot_id, "snapshot_id")
    with database.connect() as connection:
        row = connection.execute(
            _GET,
            {"snapshot_id": clean_id},
        ).mappings().first()
    return dict(row) if row is not None else None


def list_snapshots(
    *,
    ai_run_id: str | None = None,
    target_google_place_id: str | None = None,
    engine: Engine | None = None,
) -> list[dict[str, Any]]:
    database = engine or get_engine()
    clean_run_id = _clean_uuid(ai_run_id, "ai_run_id")
    with database.connect() as connection:
        rows = connection.execute(
            _LIST,
            {
                "ai_run_id": clean_run_id,
                "target_google_place_id": target_google_place_id,
            },
        ).mappings().all()
    return [dict(row) for row in rows]
