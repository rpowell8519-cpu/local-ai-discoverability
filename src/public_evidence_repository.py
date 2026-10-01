"""Project existing source records into an evidence matrix; every query is read-only."""
from __future__ import annotations

import pandas as pd
from sqlalchemy import text

from src.database import get_engine
from src.public_evidence_matrix import build_evidence_matrix


def load_public_evidence_bundle(business, *, engine=None):
    pid = str(business["google_place_id"])
    with (engine or get_engine()).connect() as connection:
        # One stable read-only view of the source records. No collectors or model calls.
        connection.execute(text("set transaction isolation level repeatable read, read only"))
        parameters = {"pid": pid}
        listing = connection.execute(text("""
            select id, google_place_id, created_at, raw_data from public.raw_outscraper_locations
            where google_place_id=:pid order by created_at desc, id desc limit 1
        """), parameters).mappings().first()
        audit = connection.execute(text("""
            select *
            from public.website_audit_runs where google_place_id=:pid
            order by started_at desc, id desc limit 1
        """), parameters).mappings().first()
        pages = []
        if audit:
            pages = connection.execute(text("""
                select *
                from public.website_audit_pages where audit_run_id=:audit_id
                order by crawled_at, id
            """), {"audit_id": audit["id"]}).mappings().all()
        reviews = connection.execute(text("""
            select *
            from public.business_reviews where google_place_id=:pid
            order by imported_at desc, id desc
        """), parameters).mappings().all()
        links = connection.execute(text("""
            select * from public.business_platform_links
            where google_place_id=:pid
        """), parameters).mappings().all()
        revision = connection.execute(text("""
            select id,revision,created_at,reviewer_decisions from public.report_audit_revisions
            where target_google_place_id=:pid order by revision desc, id desc limit 1
        """), parameters).mappings().first()
    checks = ((revision or {}).get("reviewer_decisions") or {}).get("review_platform_checks") or {}
    return {"business": dict(business), "listing": dict(listing) if listing else None,
            "audit": dict(audit) if audit else None, "pages": [dict(p) for p in pages],
            "reviews": [dict(r) for r in reviews], "platform_links": [dict(l) for l in links],
            "checks": {pid: checks[pid]} if pid in checks else {},
            "review_check_revision": {k: revision[k] for k in ("id", "revision", "created_at")} if revision else None}


def matrix_from_bundle(bundle, catalogue, aliases):
    return build_evidence_matrix(**{k: bundle[k] for k in ("business", "listing", "audit", "pages", "checks")},
        reviews=pd.DataFrame(bundle["reviews"]), platform_links=pd.DataFrame(bundle["platform_links"]),
        catalogue=catalogue, aliases=aliases)


def load_public_evidence_matrix(business, catalogue, aliases, *, engine=None):
    return matrix_from_bundle(load_public_evidence_bundle(business, engine=engine), catalogue, aliases)
