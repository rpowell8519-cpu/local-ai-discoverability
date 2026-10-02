"""Read saved owner positioning and exact completed reviewer provenance."""
from sqlalchemy import text

from src.database import get_engine


def load_owner_brief(place_id, *, engine=None):
    with (engine or get_engine()).connect() as connection:
        row = connection.execute(text("""
            select id,target_google_place_id,revision,known_for,owner_context,benchmark_run_id,
                   reviewer_decisions,reviewer_decisions_complete,created_at
            from public.report_audit_revisions where target_google_place_id=:pid
            order by revision desc,created_at desc,id desc limit 1
        """), {"pid": place_id}).mappings().first()
    return dict(row) if row else None


def load_approved_actions(place_id, *, engine=None):
    with (engine or get_engine()).connect() as connection:
        # Use the current revision only; an older completed review may have been withdrawn.
        row = connection.execute(text("""
            select id,reviewer_decisions,reviewer_decisions_complete
            from public.report_audit_revisions where target_google_place_id=:pid
            order by revision desc,created_at desc,id desc limit 1
        """), {"pid": place_id}).mappings().first()
    if not row or not row["reviewer_decisions_complete"]:
        return []
    return [{"revision_id": str(row["id"]), "action_id": r["id"], "action": r.get("action", "")}
            for r in (row["reviewer_decisions"] or {}).get("approved_recommendations", []) if r.get("id")]
