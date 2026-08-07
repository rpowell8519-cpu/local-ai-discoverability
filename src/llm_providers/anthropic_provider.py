from __future__ import annotations

import time

import requests

from src.llm_providers.base import (
    ProviderError,
    ProviderResponse,
    SYSTEM_INSTRUCTION,
)


ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"


def call_anthropic(
    *,
    api_key: str,
    model: str,
    prompt: str,
    timeout_seconds: int = 90,
) -> ProviderResponse:
    started = time.perf_counter()

    response = requests.post(
        ANTHROPIC_URL,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 1200,
            "system": SYSTEM_INSTRUCTION,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
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
            f"Anthropic returned HTTP {response.status_code} "
            "with a non-JSON response."
        ) from exc

    if not response.ok:
        error = payload.get("error") or {}
        message = (
            error.get("message")
            or str(payload)[:500]
        )
        raise ProviderError(
            f"Anthropic HTTP {response.status_code}: {message}"
        )

    parts = [
        str(item.get("text", ""))
        for item in payload.get("content", [])
        if item.get("type") == "text"
    ]

    text_value = "\n".join(parts).strip()

    if not text_value:
        raise ProviderError(
            "Anthropic returned no text output."
        )

    usage = payload.get("usage") or {}

    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")

    try:
        total_tokens = (
            int(input_tokens or 0)
            + int(output_tokens or 0)
        )
    except (TypeError, ValueError):
        total_tokens = None

    stop_reason = str(
        payload.get("stop_reason")
        or "unknown"
    )

    response_complete = stop_reason in {
        "end_turn",
        "stop_sequence",
    }

    return ProviderResponse(
        provider="Claude",
        model=model,
        text=text_value,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        reasoning_tokens=None,
        latency_ms=latency_ms,
        finish_reason=stop_reason,
        response_complete=response_complete,
        raw=payload,
    )
