"""Map one saved AI Visibility scan into the GSO answer-level report contract."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Mapping
from urllib.parse import urlsplit

import pandas as pd

from gso_report.schema import Brand, Citation, Mention, Observation, Prompt, Report
from gso_report.metrics import kpis


_PROVIDERS = {
    "openai": "OpenAI",
    "claude": "Claude",
    "anthropic": "Claude",
    "gemini": "Gemini",
    "google": "Gemini",
}
_INTENTS = {"discovery", "comparison", "transactional", "branded"}


def _records(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, pd.DataFrame):
        return value.to_dict("records")
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, Mapping)]
    return []


def _json_value(value: Any, fallback: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return fallback
    return fallback if value is None else value


def _as_datetime(value: Any) -> datetime:
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime):
        raise ValueError("A saved answer is missing its collection timestamp")
    # PostgreSQL stores these values as timestamptz. The UTC fallback is for older
    # installations whose driver returned a naive datetime despite that contract.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _optional_int(value: Any) -> int | None:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    if str(value).strip().lower() in {"", "none", "not rated", "nan"}:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _host(url: str) -> str:
    candidate = url.strip()
    if "://" not in candidate:
        candidate = "https://" + candidate
    return (urlsplit(candidate).hostname or "").lower().removeprefix("www.")


def _domain_from_website(value: Any) -> str | None:
    if not value:
        return None
    host = _host(str(value))
    return host or None


def _provider(value: Any) -> str:
    provider = _PROVIDERS.get(str(value or "").strip().lower())
    if provider is None:
        raise ValueError(f"Unsupported provider in saved scan: {value}")
    return provider


def _run_providers(value: Any) -> list[str]:
    providers = _json_value(value, [])
    return list(dict.fromkeys(_provider(item) for item in providers))


def _intent(query: Mapping[str, Any]) -> str:
    value = str(query.get("report_intent") or "discovery").strip().lower()
    return value if value in _INTENTS else "discovery"


def _known_mentions(value: Any) -> list[dict[str, Any]]:
    raw = _json_value(value, [])
    if not isinstance(raw, list):
        return []
    result = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        place_id = str(item.get("google_place_id") or "").strip()
        name = str(item.get("business_name") or "").strip()
        if not place_id or not name or place_id in seen:
            continue
        seen.add(place_id)
        result.append(dict(item, google_place_id=place_id, business_name=name))
    return result


def _observation_mentions(result: Mapping[str, Any], target_id: str, target_name: str) -> list[Mention]:
    entries = _known_mentions(result.get("mentioned_known_businesses"))
    if not entries:
        entries = _known_mentions(result.get("mentioned_competitors"))
        if bool(result.get("target_mentioned")):
            entries.append({
                "google_place_id": target_id,
                "business_name": target_name,
                "recommended": bool(result.get("target_recommended")),
                "recommendation_position": result.get("target_position"),
            })
    # Historical scans can contain tied or repeated positions for multiple names in
    # one answer. The report schema requires ranks to be unique; keep the first
    # explicit rank and leave later tied entries unranked rather than inventing a
    # new ordering. The saved answer order and recommendation status remain intact.
    seen_ranks: set[int] = set()
    mentions: list[Mention] = []
    for entry in entries:
        rank = _optional_int(entry.get("recommendation_position"))
        if rank is not None and rank in seen_ranks:
            rank = None
        if rank is not None:
            seen_ranks.add(rank)
        mentions.append(
            Mention(
                brand_id=entry["google_place_id"],
                recommended=bool(entry.get("recommended")),
                position=rank,
                recommendation_position=rank,
                sentiment="unknown",
            )
        )
    return mentions


def _citations(metadata: Mapping[str, Any], domains: list[str]) -> list[Citation]:
    citations = _json_value(metadata.get("citations"), [])
    if not isinstance(citations, list):
        return []
    result = []
    seen: set[str] = set()
    for item in citations:
        if not isinstance(item, Mapping):
            continue
        url = str(item.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        host = _host(url)
        owned = any(host == domain or host.endswith("." + domain) for domain in domains)
        result.append(Citation(url=url, title=str(item.get("title") or ""), source_type="owned" if owned else "other"))
    return result


def build_gso_report_from_saved_run(
    run: Mapping[str, Any],
    queries: Any,
    results: Any,
    *,
    target_google_place_id: str,
    client_name: str,
    client_website_url: str | None = None,
    category: str = "Local business",
    market: str | None = None,
) -> Report:
    """Build a report without new API calls, from the run's persisted answer records."""

    if str(run.get("status") or "") != "completed":
        raise ValueError("The GSO report requires a completed AI Visibility run")
    query_rows = _records(queries)
    result_rows = _records(results)
    if not query_rows or not result_rows:
        raise ValueError("The selected scan has no saved prompts or answer records")

    providers = _run_providers(run.get("providers"))
    if not providers:
        providers = list(dict.fromkeys(_provider(row.get("provider")) for row in result_rows))
    provider_set = set(providers)

    prompts_by_order: dict[int, Prompt] = {}
    query_prompt_ids: dict[str, str] = {}
    for row in query_rows:
        query_id = str(row.get("id") or "")
        order = _optional_int(row.get("base_prompt_order"))
        text = str(row.get("prompt_text") or "").strip()
        if not query_id or order is None or not text:
            raise ValueError("A saved scan prompt is missing its ID, order or exact wording")
        prompt_id = f"q{order}"
        prompt = prompts_by_order.get(order)
        if prompt is not None and prompt.text != text:
            raise ValueError(f"Saved repetitions of Q{order} do not use the same exact wording")
        if prompt is None:
            importance = _optional_int(row.get("report_importance"))
            effort = _optional_int(row.get("report_effort"))
            prompts_by_order[order] = Prompt(
                id=prompt_id,
                text=text,
                topic=str(row.get("prompt_category") or f"Question {order}"),
                intent=_intent(row),
                location=str(run.get("location_context") or "").strip() or None,
                importance=importance,
                effort=effort,
            )
        query_prompt_ids[query_id] = prompt_id

    expected_pairs = {(str(row.get("id")), provider) for row in query_rows for provider in providers}
    actual_pairs = {(str(row.get("query_id")), _provider(row.get("provider"))) for row in result_rows}
    if actual_pairs != expected_pairs:
        missing = len(expected_pairs - actual_pairs)
        unexpected = len(actual_pairs - expected_pairs)
        raise ValueError(
            f"Saved scan records do not match its planned calls ({missing} missing, {unexpected} unexpected). "
            "Finish or repair the scan before generating this report."
        )

    client_id = str(target_google_place_id)
    domains = [_domain_from_website(client_website_url)] if _domain_from_website(client_website_url) else []
    brands_by_id: dict[str, Brand] = {client_id: Brand(id=client_id, name=client_name, domains=domains)}
    mentions_by_result: dict[str, list[Mention]] = {}
    for row in result_rows:
        result_id = str(row.get("id") or "")
        mentions = _observation_mentions(row, client_id, client_name)
        mentions_by_result[result_id] = mentions
        entries = _known_mentions(row.get("mentioned_known_businesses"))
        if not entries:
            entries = _known_mentions(row.get("mentioned_competitors"))
        if bool(row.get("target_mentioned")) and all(item["google_place_id"] != client_id for item in entries):
            entries.append({"google_place_id": client_id, "business_name": client_name})
        for entry in entries:
            place_id = entry["google_place_id"]
            if place_id not in brands_by_id:
                brands_by_id[place_id] = Brand(id=place_id, name=entry["business_name"])

    times = [_as_datetime(row.get("created_at")) for row in result_rows]
    benchmark_mode = str(run.get("benchmark_mode") or "unknown")
    location = str(run.get("location_context") or "location not recorded")
    configuration = f"benchmark_mode={benchmark_mode}; location={location}; search={benchmark_mode == 'search_grounded'}"
    observations = []
    missing_metadata = 0
    for row, collected_at in zip(result_rows, times):
        result_id = str(row.get("id") or "")
        query_id = str(row.get("query_id") or "")
        if not result_id or query_id not in query_prompt_ids:
            raise ValueError("A saved answer does not map to a saved prompt")
        metadata = _json_value(row.get("report_metadata"), {})
        if not isinstance(metadata, Mapping):
            metadata = {}
        citation_status = str(metadata.get("citation_status") or "unavailable")
        if citation_status not in {"measured", "unavailable"}:
            citation_status = "unavailable"
        if citation_status == "unavailable":
            missing_metadata += 1
        row_status = str(row.get("status") or "failed").lower()
        complete_value = row.get("response_complete")
        complete = bool(complete_value) if complete_value is not None else False
        answer = str(row.get("raw_response") or "")
        explicit_refusal = bool(metadata.get("refused")) or row_status in {"refused", "refusal"}
        if explicit_refusal and complete and answer.strip():
            status = "refused"
        elif row_status == "completed" and complete and answer.strip():
            status = "ok"
        else:
            status = "error"
        mentions = mentions_by_result[result_id] if status == "ok" else []
        citations = _citations(metadata, domains) if status == "ok" and citation_status == "measured" else []
        error = None if status in {"ok", "refused"} else str(row.get("error_message") or row.get("finish_reason") or "The provider response was incomplete or failed")
        observations.append(Observation(
            id=result_id,
            prompt_id=query_prompt_ids[query_id],
            provider=_provider(row.get("provider")),
            model=str(row.get("model") or "model not recorded"),
            surface="api",
            configuration=configuration,
            collected_at=collected_at,
            status=status,
            error=error,
            answer=answer,
            mentions=mentions,
            citations=citations,
            citation_status=citation_status if status == "ok" else "unavailable",
        ))

    capture_note = (
        f"Citation metadata was unavailable for {missing_metadata} of {len(result_rows)} saved results; "
        "those answers are not counted as uncited."
    ) if missing_metadata else "Citation capture metadata was available for every saved result."
    method = (
        f"Built from saved AI Visibility run {run.get('id')}. Each persisted provider result is one API observation; "
        "the original answer text is preserved. Prompt intents are the explicit scan selections, with discovery as "
        "the legacy default. Recommendation ranks are included only when the scan parser found an explicitly numbered "
        "answer list. Business mentions use the scan's saved verified Google Place ID matches; unresolved names are not "
        "guessed into the tracked set. Sentiment and fact checks are not collected by this scan and remain unknown or "
        "unavailable. Prompt importance and effort are optional editorial inputs; unprovided values leave opportunity "
        f"scores unavailable. {capture_note} Collection mode: {benchmark_mode}; location: {location}. API results do not "
        "measure visibility in a provider's consumer application."
    )
    if not domains:
        method += " The client's website domain was not configured for this business, so owned-site citation rate and the visibility index are N/A."
    report = Report(
        client_id=client_id,
        agency="AI Visibility Scan",
        category=category or "Local business",
        market=market or location,
        start_date=min(item.date() for item in times),
        end_date=max(item.date() for item in times),
        sample_data=False,
        executive_summary="",
        methodology_notes=method,
        brands=list(brands_by_id.values()),
        prompts=list(prompts_by_order.values()),
        observations=observations,
        roadmap=[],
    )
    stats = kpis(report, observations)
    mention_rate = "N/A" if stats["Mention rate %"] is None else f"{stats['Mention rate %']:.1f}%"
    recommendation_rate = (
        "N/A" if stats["Recommendation rate %"] is None else f"{stats['Recommendation rate %']:.1f}%"
    )
    report.executive_summary = (
        f"{client_name} was matched in {sum(m.brand_id == client_id for item in observations if item.status == 'ok' for m in item.mentions)} "
        f"of {stats['Successful answers']} successful saved answers (mention rate {mention_rate}). "
        f"An explicit numbered recommendation was recorded in {recommendation_rate} of successful answers. "
        f"The scan saved {stats['Failed/refused runs']} failed, incomplete or refused result(s); these are excluded from rates. "
        "This is an API measurement of the selected question panel, not a measurement of visibility in a provider's consumer app."
    )
    return report
