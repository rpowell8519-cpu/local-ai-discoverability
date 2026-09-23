from __future__ import annotations

import inspect
import pytest
from unittest.mock import Mock, patch

from src.ai_discovery_repository import create_discovery_run
from src.ai_visibility_repository import create_visibility_run
from src.ai_visibility_runner import SUPPORTED_BENCHMARK_MODES
from src.llm_providers.anthropic_provider import call_anthropic
from src.llm_providers.base import ProviderError
from src.llm_providers.gemini_provider import call_gemini
from src.llm_providers.openai_provider import call_openai


def _response(payload: dict) -> Mock:
    response = Mock()
    response.ok = True
    response.status_code = 200
    response.json.return_value = payload
    return response


def test_persisted_search_mode_matches_database_contract() -> None:
    assert inspect.signature(create_visibility_run).parameters["benchmark_mode"].default == "search_grounded"
    assert inspect.signature(create_discovery_run).parameters["benchmark_mode"].default == "search_grounded"
    assert SUPPORTED_BENCHMARK_MODES == {"model_memory", "search_grounded"}


def test_openai_consumer_web_forces_localised_search() -> None:
    payload = {
        "status": "completed",
        "output": [
            {"type": "web_search_call", "status": "completed"},
            {"type": "message", "content": [{"type": "output_text", "text": "1. Example"}]},
        ],
        "usage": {},
    }
    with patch("src.llm_providers.openai_provider.requests.post", return_value=_response(payload)) as post:
        result = call_openai(
            api_key="test", model="test-model", prompt="Best cleaner?",
            benchmark_mode="search_grounded", location_context="Brighton",
        )

    body = post.call_args.kwargs["json"]
    assert body["tool_choice"] == "required"
    assert body["tools"][0]["type"] == "web_search"
    assert body["tools"][0]["user_location"]["city"] == "Brighton"
    assert result.text == "1. Example"


def test_claude_consumer_web_enables_localised_search() -> None:
    payload = {
        "stop_reason": "end_turn",
        "content": [
            {"type": "server_tool_use", "name": "web_search"},
            {"type": "text", "text": "1. Example"},
        ],
        "usage": {},
    }
    with patch("src.llm_providers.anthropic_provider.requests.post", return_value=_response(payload)) as post:
        result = call_anthropic(
            api_key="test", model="test-model", prompt="Best cleaner?",
            benchmark_mode="search_grounded", location_context="Brighton",
        )

    tool = post.call_args.kwargs["json"]["tools"][0]
    assert post.call_args.kwargs["json"]["tool_choice"] == {"type": "tool", "name": "web_search"}
    assert tool["type"] == "web_search_20260318"
    assert tool["max_uses"] == 3
    assert tool["user_location"]["city"] == "Brighton"
    assert result.text == "1. Example"


def test_claude_still_rejects_an_ungrounded_answer() -> None:
    payload = {
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": "1. Example"}],
        "usage": {},
    }
    with patch("src.llm_providers.anthropic_provider.requests.post", return_value=_response(payload)):
        with pytest.raises(ProviderError, match="without completing a live web search"):
            call_anthropic(api_key="test", model="test-model", prompt="Nurseries?",
                           benchmark_mode="search_grounded")


def test_claude_memory_benchmark_does_not_enable_or_force_search() -> None:
    payload = {
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": "1. Example"}],
        "usage": {},
    }
    with patch("src.llm_providers.anthropic_provider.requests.post", return_value=_response(payload)) as post:
        result = call_anthropic(api_key="test", model="test-model", prompt="Nurseries?",
                                benchmark_mode="model_memory")
    assert "tool_choice" not in post.call_args.kwargs["json"]
    assert "tools" not in post.call_args.kwargs["json"]
    assert result.response_complete


def test_gemini_consumer_web_uses_google_search_interaction() -> None:
    payload = {
        "status": "completed",
        "steps": [
            {"type": "google_search_call", "arguments": {"queries": ["cleaners Brighton"]}},
            {"type": "model_output", "content": [{"type": "text", "text": "1. Example"}]},
        ],
        "usage": {
            "total_input_tokens": 120,
            "total_output_tokens": 35,
            "total_tokens": 155,
            "total_thought_tokens": 4,
            "grounding_tool_count": [{"type": "google_search", "count": 1}],
        },
    }
    with patch("src.llm_providers.gemini_provider.requests.post", return_value=_response(payload)) as post:
        result = call_gemini(
            api_key="test", model="test-model", prompt="Best cleaner?",
            benchmark_mode="search_grounded", location_context="Brighton",
        )

    assert post.call_args.args[0].endswith("/v1beta/interactions")
    assert post.call_args.kwargs["json"]["tools"] == [{"type": "google_search"}]
    assert "Customer location: Brighton" in post.call_args.kwargs["json"]["input"]
    assert result.text == "1. Example"
    assert result.input_tokens == 120
    assert result.output_tokens == 35
    assert result.total_tokens == 155
    assert result.reasoning_tokens == 4
