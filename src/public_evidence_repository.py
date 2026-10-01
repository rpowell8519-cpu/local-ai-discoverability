"""Project existing source records into an evidence matrix; every query is read-only."""
from __future__ import annotations

import pandas as pd
from sqlalchemy import text

from src.database import get_engine
from src.public_evidence_matrix import build_evidence_matrix


def load_public_evidence_matrix(business, catalogue, aliases, *, engine=None):
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
            select id, requested_url, audit_status, started_at, completed_at
            from public.website_audit_runs where google_place_id=:pid
            order by started_at desc, id desc limit 1
        """), parameters).mappings().first()
        pages = []
        if audit:
            pages = connection.execute(text("""
                select id, url, final_url, http_status, text_excerpt, crawled_at
                from public.website_audit_pages where audit_run_id=:audit_id
                order by crawled_at, id
            """), {"audit_id": audit["id"]}).mappings().all()
        reviews = connection.execute(text("""
            select id, google_place_id, review_id, review_text, review_link, source,
                   review_datetime_utc, imported_at
            from public.business_reviews where google_place_id=:pid
            order by imported_at desc, id desc
        """), parameters).mappings().all()
        links = connection.execute(text("""
            select google_place_id, platform, external_url from public.business_platform_links
            where google_place_id=:pid
        """), parameters).mappings().all()
        revision = connection.execute(text("""
            select reviewer_decisions from public.report_audit_revisions
            where target_google_place_id=:pid order by revision desc, id desc limit 1
        """), parameters).mappings().first()
    checks = ((revision or {}).get("reviewer_decisions") or {}).get("review_platform_checks") or {}
    return build_evidence_matrix(business=business, listing=dict(listing) if listing else None,
        audit=dict(audit) if audit else None, pages=[dict(p) for p in pages], reviews=pd.DataFrame(reviews),
        platform_links=pd.DataFrame(links), checks=checks, catalogue=catalogue, aliases=aliases)
