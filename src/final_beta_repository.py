"""Gather what the Final Beta report needs beyond the reviewed summary. Reads only; nothing is written."""
from __future__ import annotations

from typing import Any, Callable, Mapping

import requests
from sqlalchemy import text

from src.ai_visibility_repository import core_run_filter, get_run_results
from src.database import get_engine
from src.final_beta_report import COMMON_THEMES, build_final_beta_report, domain_of
from src.review_profiles import get_review_profile
from src.website_audit import safe_get


def page_fetcher(timeout_seconds: int = 8, max_bytes: int = 1_500_000) -> Callable[[str], str]:
    """Read one public page, with the same address and redirect checks the website scan uses."""
    def fetch(url: str) -> str:
        response = safe_get(requests.Session(), url, timeout_seconds=timeout_seconds, max_bytes=max_bytes)
        if response.status_code != 200:
            raise ValueError(f"HTTP {response.status_code}")
        return response.content.decode(response.encoding or "utf-8", "ignore")

    return fetch


def load_business_domains(*, engine=None) -> dict[str, str]:
    """Website address to business name, for addresses that belong to exactly one business."""
    with (engine or get_engine()).connect() as connection:
        rows = connection.execute(text("""
            select distinct on (bf.google_place_id) bf.business_name,
                   coalesce(nullif(rol.raw_data->>'website', ''), nullif(rol.raw_data->>'site', '')) as website
            from public.business_features bf
            join public.raw_outscraper_locations rol on rol.google_place_id = bf.google_place_id
            where bf.business_name is not null
            order by bf.google_place_id, rol.created_at desc
        """)).all()
    owners: dict[str, set[str]] = {}
    for name, website in rows:
        host = domain_of(website)
        if host:
            owners.setdefault(host, set()).add(str(name))
    return {host: next(iter(names)) for host, names in owners.items() if len(names) == 1}


def load_previous_run(place_id: str, run_id: str, question_texts: list[str], *, engine=None) -> tuple[list[dict[str, Any]], Any]:
    """The most recent earlier completed benchmark for this business that asked any of the same questions."""
    with (engine or get_engine()).connect() as connection:
        current = connection.execute(text("select started_at from public.ai_visibility_runs where id = cast(:id as uuid)"), {"id": run_id}).scalar()
        if current is None:
            return [], None
        earlier = connection.execute(text(f"""
            select ai_visibility_runs.id, ai_visibility_runs.started_at from public.ai_visibility_runs
            where target_google_place_id = :place and status = 'completed' and started_at < :current
              and exists (select 1 from public.ai_visibility_queries q where q.run_id = ai_visibility_runs.id and q.prompt_text = any(:texts))
              {core_run_filter(connection)}
            order by started_at desc limit 1
        """), {"place": place_id, "current": current, "texts": question_texts}).first()
        if not earlier:
            return [], None
        rows = connection.execute(text("""
            select q.prompt_text, r.raw_response, r.status, r.response_complete
            from public.ai_visibility_results r join public.ai_visibility_queries q on q.id = r.query_id
            where r.run_id = :run and q.prompt_text = any(:texts)
        """), {"run": earlier[0], "texts": question_texts}).mappings().all()
    return [dict(row) for row in rows], earlier[1]


def assemble_final_beta(summary: Mapping[str, Any], payload: Mapping[str, Any], audit_revision: Mapping[str, Any],
                        business: Mapping[str, Any], *, fetch: Callable[[str], str] | None = None, engine=None) -> dict[str, Any]:
    decisions = dict(audit_revision.get("reviewer_decisions") or {})
    run_id = str(audit_revision["benchmark_run_id"])
    place_id = str(audit_revision["target_google_place_id"])
    group = str(business.get("primary_group") or "generic")
    results = get_run_results(run_id).to_dict("records")
    question_texts = [" ".join(str(q["text"]).split()) for q in summary["questions"]]
    previous_rows, previous_date = load_previous_run(place_id, run_id, [str(q["text"]) for q in summary["questions"]] + question_texts, engine=engine)
    wording = dict(decisions.get("type_wording") or {})
    themes = [(label, list(terms)) for label, terms in COMMON_THEMES]
    seen = {label.casefold() for label, _ in themes}
    for theme in [*(wording.get("review_themes") or []), *get_review_profile(group)["themes"][6:]]:
        # The reviewer-approved themes for this type of business, then any written for its group.
        if str(theme["label"]).casefold() not in seen and str(theme.get("category") or "") != "Problems":
            seen.add(str(theme["label"]).casefold())
            themes.append((str(theme["label"]), list(theme.get("terms") or [])))
    records = next((list(s.get("records") or []) for s in payload["review_evidence"]["review_sets"]
                    if str(s.get("google_place_id")) == place_id), [])
    return build_final_beta_report(
        summary, responses=list(payload["baseline_validation"]["responses"]), results=results,
        confirmed_names=list(decisions.get("confirmed_target_names") or []),
        owner_priorities=list(dict(audit_revision.get("owner_context") or {}).get("priority_services") or []),
        own_domains=[business.get("source_website_url"), audit_revision.get("manual_website_url")],
        business_domains=load_business_domains(engine=engine), previous_rows=previous_rows, previous_date=previous_date,
        review_records=records, review_themes=themes, google_total=business.get("google_reviews"),
        google_rating=business.get("google_rating"), quote_ids=[str(i) for i in decisions.get("review_quote_ids") or []],
        approved_actions=[a for a in decisions.get("approved_recommendations") or [] if str(a.get("kind") or "action") == "action"],
        # Collection notes ("no review text was collected") are for the operator, not the client.
        approved_findings=[a for a in decisions.get("approved_recommendations") or [] if str(a.get("kind")) == "finding"
                           and not str(a.get("signal") or "").startswith("collection:")],
        fetch=fetch,
    )
