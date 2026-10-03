"""Immutable panel configuration, compatible series and dated run/wave identities."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from src.llm_providers.base import instruction_for_mode

PANEL_VERSION = "measurement-panel-v1"
# Only core runs feed canonical reports and benchmarks; every other kind is kept out by core_run_filter.
PANEL_KINDS = frozenset({"core", "focused", "free_check"})
PROVIDER_FILES = {"OpenAI": "openai_provider.py", "Claude": "anthropic_provider.py", "Gemini": "gemini_provider.py"}


def build_panel(*, prompts: list[dict[str, Any]], providers: list[str], models: dict[str, str],
                location_context: str, benchmark_mode: str, repeat_count: int,
                primary_group: str, panel_kind: str = "core", settings: dict[str, Any] | None = None) -> dict[str, Any]:
    if panel_kind not in PANEL_KINDS:
        raise ValueError("Panel kind must be core, focused or free_check")
    if not prompts or len(prompts) != len({p["prompt"] for p in prompts}):
        raise ValueError("Panel prompts must be nonempty and distinct")
    if isinstance(repeat_count, bool) or int(repeat_count) < 1:
        raise ValueError("A positive repeat count is required")
    if not providers or len(providers) != len(set(providers)):
        raise ValueError("Distinct providers are required")
    adapter_hashes = {}
    for provider in providers:
        if provider not in PROVIDER_FILES or not models.get(provider):
            raise ValueError("Every provider needs a supported adapter and requested model")
        adapter_hashes[provider] = hashlib.sha256(
            (Path(__file__).parent / "llm_providers" / PROVIDER_FILES[provider]).read_bytes()).hexdigest()
    config = {"version": PANEL_VERSION, "panel_kind": panel_kind,
              "prompts": [{"text": p["prompt"], "source": p.get("source"), "category": p.get("category"),
                           "weight": p.get("weight", 1)} for p in prompts],
              "providers": sorted(providers), "requested_models": {p: models[p] for p in sorted(providers)},
              "benchmark_mode": benchmark_mode, "location_context": location_context, "primary_group": primary_group,
              "repeat_count": int(repeat_count), "instruction": instruction_for_mode(benchmark_mode),
              "adapter_sha256": adapter_hashes, "settings": settings or {},
              "model_version_status": "requested_only"}
    encoded = json.dumps(config, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    checksum = hashlib.sha256(encoded.encode()).hexdigest()
    return {"panel_id": checksum, "configuration_sha256": checksum, "configuration": config, "panel_kind": panel_kind}


def comparison_compatibility(before: dict[str, Any] | None, after: dict[str, Any] | None,
                             *, before_model_versions: dict | None = None,
                             after_model_versions: dict | None = None) -> dict[str, Any]:
    reasons = []
    if not before or not after:
        reasons.append("Historical panel metadata is unavailable")
    else:
        if before["configuration_sha256"] != after["configuration_sha256"]:
            reasons.append("Prompt, provider, mode, model, location, repeat or adapter configuration differs")
        if before.get("series_id") != after.get("series_id") or not before.get("series_id"):
            reasons.append("Waves are not in the same comparison series")
        expected = set(before["configuration"]["providers"])
        if not before_model_versions or not after_model_versions or any(
            not before_model_versions.get(p) or not after_model_versions.get(p) for p in expected
        ):
            reasons.append("Served model versions are not verified for every provider")
        elif before_model_versions != after_model_versions:
            reasons.append("Served model versions differ")
    return {"compatible": not reasons, "reasons": reasons}
