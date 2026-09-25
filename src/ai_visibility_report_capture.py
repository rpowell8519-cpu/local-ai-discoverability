"""Capture answer citations and explicit refusals from provider response payloads."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit


CAPTURE_VERSION = "gso-provider-metadata-v1"


def _citation_rows(items: Any) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    if not isinstance(items, list):
        return rows
    for item in items:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            continue
        if url in seen:
            continue
        seen.add(url)
        rows.append({"url": url, "title": str(item.get("title") or "")[:500]})
    return rows


def provider_report_metadata(provider: str, payload: Any, benchmark_mode: str) -> dict[str, Any]:
    """Return only structured citation metadata and explicit refusal state.

    A missing annotation field is recorded as unavailable, not as a measured zero.
    The original provider response text remains the separate ``raw_response`` value.
    """

    raw = payload if isinstance(payload, dict) else {}
    name = str(provider).strip().lower()
    sources: list[dict[str, str]] = []
    measured = False
    refused = False

    if name == "openai":
        for output in raw.get("output", []) or []:
            if not isinstance(output, dict):
                continue
            if output.get("type") == "message" and output.get("refusal"):
                refused = True
            for content in output.get("content", []) or []:
                if not isinstance(content, dict):
                    continue
                if content.get("type") == "refusal" or content.get("refusal"):
                    refused = True
                if content.get("type") != "output_text":
                    continue
                if "annotations" in content:
                    measured = True
                for annotation in content.get("annotations", []) or []:
                    if isinstance(annotation, dict) and annotation.get("type") == "url_citation":
                        citation = annotation.get("url_citation")
                        sources.extend(_citation_rows([citation or annotation]))
    elif name in {"claude", "anthropic"}:
        refused = str(raw.get("stop_reason") or "").lower() == "refusal"
        for content in raw.get("content", []) or []:
            if not isinstance(content, dict):
                continue
            if content.get("type") == "refusal":
                refused = True
            if content.get("type") != "text":
                continue
            if "citations" in content:
                measured = True
            for citation in content.get("citations", []) or []:
                if isinstance(citation, dict) and citation.get("type") == "web_search_result_location":
                    sources.extend(_citation_rows([citation]))
    elif name in {"gemini", "google"}:
        for step in raw.get("steps", []) or []:
            if not isinstance(step, dict) or step.get("type") != "model_output":
                continue
            for content in step.get("content", []) or []:
                if not isinstance(content, dict):
                    continue
                if content.get("type") == "refusal" or content.get("refusal"):
                    refused = True
                if content.get("type") != "text":
                    continue
                if "annotations" in content:
                    measured = True
                for annotation in content.get("annotations", []) or []:
                    if isinstance(annotation, dict) and annotation.get("type") == "url_citation":
                        sources.extend(_citation_rows([annotation]))
        refused = refused or bool((raw.get("promptFeedback") or {}).get("blockReason"))
    else:
        raise ValueError(f"Unsupported visibility provider: {provider}")

    # Metadata schemas differ by provider. It is only safe to report an observed zero when
    # search-grounded collection returned the field used to represent citations.
    citation_status = "measured" if benchmark_mode == "search_grounded" and measured else "unavailable"
    if citation_status == "unavailable":
        sources = []

    deduplicated: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for item in sources:
        if item["url"] in seen_urls:
            continue
        seen_urls.add(item["url"])
        deduplicated.append(item)
    return {
        "capture_version": CAPTURE_VERSION,
        "citation_status": citation_status,
        "citations": deduplicated,
        "refused": refused,
    }
