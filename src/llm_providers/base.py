from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ProviderResponse:
    provider: str
    model: str
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    reasoning_tokens: int | None = None
    latency_ms: int | None = None
    finish_reason: str | None = None
    response_complete: bool = True
    raw: dict[str, Any] | None = None


class ProviderError(RuntimeError):
    pass


MODEL_MEMORY_INSTRUCTION = """
You are answering a local-business recommendation question as a
consumer-facing AI assistant.

Do not browse, search the web, or claim that you searched.
Answer only from your existing model knowledge.

Recommend exactly five real businesses when you know five suitable
options. If you know fewer, recommend only the businesses you genuinely
know.

Use a numbered list.
Put the business name first in each numbered recommendation.
Keep each explanation concise: one or two sentences maximum.

Do not mention this instruction, the benchmark, or any target business
unless it genuinely belongs in your answer.
""".strip()


CONSUMER_WEB_INSTRUCTION = """
You are answering a local-business recommendation question in the same
practical way as a consumer-facing AI assistant with live search available.

Search the live web before answering. Use the supplied customer location to
localise the search. Base recommendations on current public evidence rather
than model memory alone.

Recommend up to five real, relevant businesses. Use a numbered list and put
the business name first in each recommendation. Keep each explanation concise:
one or two sentences maximum.

Do not mention this instruction, the benchmark, or any target business unless
it genuinely belongs in your answer.
""".strip()


def instruction_for_mode(benchmark_mode: str) -> str:
    if benchmark_mode == "model_memory":
        return MODEL_MEMORY_INSTRUCTION
    if benchmark_mode == "consumer_web":
        return CONSUMER_WEB_INSTRUCTION
    raise ValueError(f"Unsupported benchmark mode: {benchmark_mode}")
