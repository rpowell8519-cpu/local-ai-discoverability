from __future__ import annotations

import time

import requests

from src.llm_providers.base import (
    ProviderError,
    ProviderResponse,
    SYSTEM_INSTRUCTION,
)


OPENAI_URL = "https://api.openai.com/v1/responses"


def _extract_text(payload: dict) -> str:
    direct = payload.get("output_text")

    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    parts = []

    for item in payload.get("output", []):
        if item.get("type") != "message":
            continue

        for content in item.get("content", []):
            if content.get("type") == "output_text":
                value = content.get("text")
                if value:
                    parts.append(str(value))

    return "\n".join(parts).strip()


def call_openai(
    *,
    api_key: str,
    model: str,
    prompt: str,
    timeout_seconds: int = 90,
) -> ProviderResponse:
    started = time.perf_counter()

    response = requests.post(
        OPENAI_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "instructions": SYSTEM_INSTRUCTION,
            "input": prompt,
            "reasoning": {
                "effort": "none",
            },
            "max_output_tokens": 900,
        },
        timeout=timeout_seconds,
    )

    latency_ms = int(
        (time.perf_counter() - started) * 1000
    )

    try:
        payload = response.json()
    except ValueError as exc:
        raise ProviderError(
            f"OpenAI returned HTTP {response.status_code} "
            "with a non-JSON response."
        ) from exc

    if not response.ok:
        message = (
            payload.get("error", {}).get("message")
            or str(payload)[:500]
        )
        raise ProviderError(
            f"OpenAI HTTP {response.status_code}: {message}"
        )

    text_value = _extract_text(payload)

    if not text_value:
        raise ProviderError(
            "OpenAI returned no text output."
        )

    usage = payload.get("usage") or {}
    output_details = (
        usage.get("output_tokens_details")
        or {}
    )

    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    total_tokens = usage.get("total_tokens")
    reasoning_tokens = output_details.get(
        "reasoning_tokens"
    )

    status = str(
        payload.get("status")
        or "completed"
    )

    incomplete_details = (
        payload.get("incomplete_details")
        or {}
    )

    incomplete_reason = (
        incomplete_details.get("reason")
    )

    response_complete = (
        status == "completed"
    )

    finish_reason = status

    if incomplete_reason:
        finish_reason = (
            f"{status}:{incomplete_reason}"
        )

    return ProviderResponse(
        provider="OpenAI",
        model=model,
        text=text_value,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        reasoning_tokens=reasoning_tokens,
        latency_ms=latency_ms,
        finish_reason=finish_reason,
        response_complete=response_complete,
        raw=payload,
    )
