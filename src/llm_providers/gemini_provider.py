from __future__ import annotations

import time
from urllib.parse import quote

import requests

from src.llm_providers.base import (
    ProviderError,
    ProviderResponse,
    SYSTEM_INSTRUCTION,
)


def call_gemini(
    *,
    api_key: str,
    model: str,
    prompt: str,
    timeout_seconds: int = 90,
) -> ProviderResponse:
    encoded_model = quote(
        model,
        safe="-._",
    )

    url = (
        "https://generativelanguage.googleapis.com/"
        f"v1beta/models/{encoded_model}:generateContent"
    )

    started = time.perf_counter()

    response = requests.post(
        url,
        headers={
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        },
        json={
            "systemInstruction": {
                "parts": [
                    {
                        "text": SYSTEM_INSTRUCTION,
                    }
                ]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": prompt,
                        }
                    ],
                }
            ],
            "generationConfig": {
                "maxOutputTokens": 700,
            },
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
            f"Gemini returned HTTP {response.status_code} "
            "with a non-JSON response."
        ) from exc

    if not response.ok:
        error = payload.get("error") or {}
        message = (
            error.get("message")
            or str(payload)[:500]
        )
        raise ProviderError(
            f"Gemini HTTP {response.status_code}: {message}"
        )

    parts = []

    for candidate in payload.get("candidates", []):
        content = candidate.get("content") or {}

        for item in content.get("parts", []):
            text_value = item.get("text")
            if text_value:
                parts.append(str(text_value))

        if parts:
            break

    text_value = "\n".join(parts).strip()

    if not text_value:
        raise ProviderError(
            "Gemini returned no text output."
        )

    usage = payload.get("usageMetadata") or {}

    input_tokens = usage.get("promptTokenCount")
    output_tokens = usage.get(
        "candidatesTokenCount"
    )
    total_tokens = usage.get("totalTokenCount")

    return ProviderResponse(
        provider="Gemini",
        model=model,
        text=text_value,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        latency_ms=latency_ms,
        raw=payload,
    )
