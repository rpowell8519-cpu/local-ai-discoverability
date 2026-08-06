from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from sqlalchemy import text

from src.database import get_engine


def create_audit_run(
    *,
    audit_batch_id: str,
    google_place_id: str,
    business_name: str,
    requested_url: str | None,
) -> str:
    engine = get_engine()
    run_id = str(uuid.uuid4())

    query = text(
        """
        insert into website_audit_runs (
            id,
            audit_batch_id,
            google_place_id,
            business_name,
            requested_url,
            audit_status,
            started_at
        )
        values (
            :id,
            :audit_batch_id,
            :google_place_id,
            :business_name,
            :requested_url,
            'running',
            now()
        )
        """
    )

    with engine.begin() as connection:
        connection.execute(
            query,
            {
                "id": run_id,
                "audit_batch_id": audit_batch_id,
                "google_place_id": google_place_id,
                "business_name": business_name,
                "requested_url": requested_url,
            },
        )

    return run_id


def save_audit_page(
    *,
    audit_run_id: str,
    page: dict[str, Any],
) -> None:
    engine = get_engine()

    query = text(
        """
        insert into website_audit_pages (
            audit_run_id,
            url,
            final_url,
            http_status,
            page_title,
            meta_description,
            canonical_url,
            headings,
            schema_types,
            detected_signals,
            issues,
            internal_links_count,
            text_excerpt,
            crawled_at
        )
        values (
            :audit_run_id,
            :url,
            :final_url,
            :http_status,
            :page_title,
            :meta_description,
            :canonical_url,
            cast(:headings as jsonb),
            cast(:schema_types as jsonb),
            cast(:detected_signals as jsonb),
            cast(:issues as jsonb),
            :internal_links_count,
            :text_excerpt,
            now()
        )
        on conflict (audit_run_id, url)
        do update set
            final_url = excluded.final_url,
            http_status = excluded.http_status,
            page_title = excluded.page_title,
            meta_description = excluded.meta_description,
            canonical_url = excluded.canonical_url,
            headings = excluded.headings,
            schema_types = excluded.schema_types,
            detected_signals = excluded.detected_signals,
            issues = excluded.issues,
            internal_links_count = excluded.internal_links_count,
            text_excerpt = excluded.text_excerpt,
            crawled_at = now()
        """
    )

    payload = {
        "audit_run_id": audit_run_id,
        "url": page.get("url"),
        "final_url": page.get("final_url"),
        "http_status": page.get("http_status"),
        "page_title": page.get("page_title"),
        "meta_description": page.get(
            "meta_description"
        ),
        "canonical_url": page.get("canonical_url"),
        "headings": json.dumps(
            page.get("headings", [])
        ),
        "schema_types": json.dumps(
            page.get("schema_types", [])
        ),
        "detected_signals": json.dumps(
            page.get("detected_signals", {})
        ),
        "issues": json.dumps(
            page.get("issues", [])
        ),
        "internal_links_count": page.get(
            "internal_links_count",
            0,
        ),
        "text_excerpt": page.get("text_excerpt"),
    }

    with engine.begin() as connection:
        connection.execute(query, payload)


def finish_audit_run(
    *,
    audit_run_id: str,
    result: dict[str, Any],
) -> None:
    engine = get_engine()

    query = text(
        """
        update website_audit_runs
        set
            final_url = :final_url,
            audit_status = :audit_status,
            http_status = :http_status,
            is_https = :is_https,
            robots_status = :robots_status,
            sitemap_url = :sitemap_url,
            pages_discovered = :pages_discovered,
            pages_crawled = :pages_crawled,
            schema_types =
                cast(:schema_types as jsonb),
            has_local_business_schema =
                :has_local_business_schema,
            has_title = :has_title,
            has_meta_description =
                :has_meta_description,
            has_canonical = :has_canonical,
            has_contact_signals =
                :has_contact_signals,
            has_address_signals =
                :has_address_signals,
            has_service_pages =
                :has_service_pages,
            has_menu_page = :has_menu_page,
            has_pricing_page = :has_pricing_page,
            has_faq_content = :has_faq_content,
            has_booking_link = :has_booking_link,
            has_social_links = :has_social_links,
            social_links = cast(:social_links as jsonb),
            issues = cast(:issues as jsonb),
            website_completeness_score =
                :website_completeness_score,
            error_message = :error_message,
            completed_at = now()
        where id = :audit_run_id
        """
    )

    payload = {
        "audit_run_id": audit_run_id,
        "final_url": result.get("final_url"),
        "audit_status": result.get(
            "audit_status",
            "failed",
        ),
        "http_status": result.get("http_status"),
        "is_https": result.get("is_https"),
        "robots_status": result.get(
            "robots_status"
        ),
        "sitemap_url": result.get("sitemap_url"),
        "pages_discovered": result.get(
            "pages_discovered",
            0,
        ),
        "pages_crawled": result.get(
            "pages_crawled",
            0,
        ),
        "schema_types": json.dumps(
            result.get("schema_types", [])
        ),
        "has_local_business_schema": result.get(
            "has_local_business_schema",
            False,
        ),
        "has_title": result.get(
            "has_title",
            False,
        ),
        "has_meta_description": result.get(
            "has_meta_description",
            False,
        ),
        "has_canonical": result.get(
            "has_canonical",
            False,
        ),
        "has_contact_signals": result.get(
            "has_contact_signals",
            False,
        ),
        "has_address_signals": result.get(
            "has_address_signals",
            False,
        ),
        "has_service_pages": result.get(
            "has_service_pages",
            False,
        ),
        "has_menu_page": result.get(
            "has_menu_page",
            False,
        ),
        "has_pricing_page": result.get(
            "has_pricing_page",
            False,
        ),
        "has_faq_content": result.get(
            "has_faq_content",
            False,
        ),
        "has_booking_link": result.get(
            "has_booking_link",
            False,
        ),
        "has_social_links": result.get(
            "has_social_links",
            False,
        ),
        "social_links": json.dumps(
            result.get("social_links", [])
        ),
        "issues": json.dumps(
            result.get("issues", [])
        ),
        "website_completeness_score": (
            result.get(
                "website_completeness_score"
            )
        ),
        "error_message": result.get(
            "error_message"
        ),
    }

    with engine.begin() as connection:
        connection.execute(query, payload)


def get_latest_audits(
    google_place_ids: list[str],
) -> pd.DataFrame:
    if not google_place_ids:
        return pd.DataFrame()

    engine = get_engine()

    query = text(
        """
        select distinct on (google_place_id)
            id,
            audit_batch_id,
            google_place_id,
            business_name,
            requested_url,
            final_url,
            audit_status,
            http_status,
            is_https,
            robots_status,
            sitemap_url,
            pages_discovered,
            pages_crawled,
            schema_types,
            has_local_business_schema,
            has_title,
            has_meta_description,
            has_canonical,
            has_contact_signals,
            has_address_signals,
            has_service_pages,
            has_menu_page,
            has_pricing_page,
            has_faq_content,
            has_booking_link,
            has_social_links,
            social_links,
            issues,
            website_completeness_score,
            error_message,
            started_at,
            completed_at
        from website_audit_runs
        where google_place_id = any(:google_place_ids)
        order by
            google_place_id,
            completed_at desc nulls last,
            started_at desc
        """
    )

    with engine.connect() as connection:
        rows = connection.execute(
            query,
            {
                "google_place_ids":
                    google_place_ids,
            },
        ).mappings().all()

    return pd.DataFrame(rows)


def get_latest_audit(
    google_place_id: str,
) -> dict[str, Any]:
    frame = get_latest_audits(
        [google_place_id]
    )

    if frame.empty:
        return {}

    return frame.iloc[0].to_dict()


def get_audit_pages(
    audit_run_id: str,
) -> pd.DataFrame:
    engine = get_engine()

    query = text(
        """
        select
            url,
            final_url,
            http_status,
            page_title,
            meta_description,
            canonical_url,
            headings,
            schema_types,
            detected_signals,
            issues,
            internal_links_count,
            text_excerpt,
            crawled_at
        from website_audit_pages
        where audit_run_id = :audit_run_id
        order by crawled_at
        """
    )

    with engine.connect() as connection:
        rows = connection.execute(
            query,
            {
                "audit_run_id": audit_run_id,
            },
        ).mappings().all()

    return pd.DataFrame(rows)
