"""Explicit archive/review writes; no write is triggered by a read or paid collector."""
from __future__ import annotations

from sqlalchemy import text

from src.database import get_engine
from src.public_evidence_archive import build_capture, canonical_json, collection_attempt, validate_decision, verify_capture

ARCHIVE_TABLES = ("public_evidence_captures", "public_evidence_observations", "public_evidence_decisions", "public_evidence_collection_attempts")


def archive_status(*, engine=None):
    with (engine or get_engine()).connect() as connection:
        rows = connection.execute(text("""
            select name,to_regclass('public.' || name) is not null as available
            from unnest(cast(:names as text[])) name
        """), {"names": list(ARCHIVE_TABLES)}).mappings().all()
    return {r["name"]: bool(r["available"]) for r in rows}


def _require_ready(engine):
    status = archive_status(engine=engine)
    if not all(status.get(t) for t in ARCHIVE_TABLES):
        raise ValueError("The separately approved evidence-archive migration must be applied first")


def save_capture(bundle, catalogue, aliases, *, archived_by, engine=None):
    if not str(archived_by or "").strip():
        raise ValueError("An archiving operator is required")
    capture = build_capture(bundle, catalogue, aliases)
    engine = engine or get_engine()
    _require_ready(engine)
    with engine.begin() as connection:
        row = connection.execute(text("""
            insert into public.public_evidence_captures
                (google_place_id,capture_version,payload,canonical_payload,payload_sha256,archived_by)
            values (:google_place_id,:capture_version,cast(cast(:body as text) as jsonb),cast(:body as text),:payload_sha256,:archived_by)
            on conflict (google_place_id,payload_sha256) do nothing returning id
        """), {**{k: capture[k] for k in ("google_place_id", "capture_version", "payload_sha256")},
                "body": canonical_json(capture["payload"]), "archived_by": archived_by.strip()}).mappings().first()
        if not row:
            return str(connection.execute(text("""
                select id from public.public_evidence_captures
                where google_place_id=:pid and payload_sha256=:checksum
            """), {"pid": capture["google_place_id"], "checksum": capture["payload_sha256"]}).scalar_one())
        for observation in capture["payload"]["matrix"]["observations"]:
            connection.execute(text("""
                insert into public.public_evidence_observations(capture_id,evidence_id,observation)
                values (:capture_id,:evidence_id,cast(:body as jsonb))
            """), {"capture_id": str(row["id"]), "evidence_id": observation["evidence_id"], "body": canonical_json(observation)})
        return str(row["id"])


def list_captures(place_id, *, engine=None):
    engine = engine or get_engine()
    status = archive_status(engine=engine)
    if not all(status.get(t) for t in ARCHIVE_TABLES):
        return []
    with engine.connect() as connection:
        rows = connection.execute(text("""
            select id,google_place_id,archived_at,archived_by,payload_sha256 from public.public_evidence_captures
            where google_place_id=:pid order by archived_at desc,id desc
        """), {"pid": place_id}).mappings().all()
    return [dict(r) for r in rows]


def load_capture(capture_id, *, engine=None):
    with (engine or get_engine()).connect() as connection:
        row = connection.execute(text("select * from public.public_evidence_captures where id=:id"), {"id": capture_id}).mappings().first()
    if not row:
        raise ValueError("No saved evidence capture exists")
    result = dict(row)
    verify_capture(result)
    return result


def list_decisions(capture_id, *, engine=None):
    with (engine or get_engine()).connect() as connection:
        rows = connection.execute(text("""
            select * from public.public_evidence_decisions where capture_id=:id order by revision,id
        """), {"id": capture_id}).mappings().all()
    return [dict(r) for r in rows]


def save_decision(capture_id, *, evidence_id, decision, origin, reviewer, note, identity_confirmed, engine=None):
    engine = engine or get_engine()
    _require_ready(engine)
    capture = load_capture(capture_id, engine=engine)
    record = validate_decision(capture, evidence_id=evidence_id, decision=decision, origin=origin,
                               reviewer=reviewer, note=note, identity_confirmed=identity_confirmed)
    with engine.begin() as connection:
        connection.execute(text("select pg_advisory_xact_lock(hashtextextended(:scope,0))"), {"scope": str(capture_id) + ":" + evidence_id})
        revision = connection.execute(text("""
            select coalesce(max(revision),0)+1 from public.public_evidence_decisions
            where capture_id=:capture_id and evidence_id=:evidence_id
        """), {"capture_id": str(capture_id), "evidence_id": evidence_id}).scalar_one()
        return str(connection.execute(text("""
            insert into public.public_evidence_decisions
                (capture_id,evidence_id,revision,decision,origin,reviewer,note,identity_confirmed)
            values (:capture_id,:evidence_id,:revision,:decision,:origin,:reviewer,:note,:identity_confirmed)
            returning id
        """), {**record, "capture_id": str(capture_id), "revision": revision}).scalar_one())


def save_collection_attempt(*, engine=None, **values):
    record = collection_attempt(**values)
    engine = engine or get_engine()
    _require_ready(engine)
    with engine.begin() as connection:
        return str(connection.execute(text("""
            insert into public.public_evidence_collection_attempts
                (google_place_id,source_class,source_url,status,observed_at,sample_size,scope,note,adapter_version,capture_id)
            values (:google_place_id,:source_class,:source_url,:status,:observed_at,:sample_size,:scope,:note,:adapter_version,:capture_id)
            returning id
        """), record).scalar_one())


def list_collection_attempts(place_id, *, engine=None):
    with (engine or get_engine()).connect() as connection:
        rows = connection.execute(text("""
            select * from public.public_evidence_collection_attempts where google_place_id=:pid
            order by observed_at desc,id desc
        """), {"pid": place_id}).mappings().all()
    return [dict(r) for r in rows]
