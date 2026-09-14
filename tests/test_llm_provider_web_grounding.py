from __future__ import annotations

from unittest.mock import Mock, patch

from src.llm_providers.anthropic_provider import call_anthropic
from src.llm_providers.gemini_provider import call_gemini
from src.llm_providers.openai_provider import call_openai


def _response(payload: dict) -> Mock:
    response = Mock()
    response.ok = True
    response.status_code = 200
    response.json.return_value = payload
    return response


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
            benchmark_mode="consumer_web", location_context="Brighton",
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
            benchmark_mode="consumer_web", location_context="Brighton",
        )

    tool = post.call_args.kwargs["json"]["tools"][0]
    assert tool["type"] == "web_search_20260318"
    assert tool["max_uses"] == 3
    assert tool["user_location"]["city"] == "Brighton"
    assert result.text == "1. Example"


def test_gemini_consumer_web_uses_google_search_interaction() -> None:
    payload = {
        "status": "completed",
        "steps": [
            {"type": "google_search_call", "arguments": {"queries": ["cleaners Brighton"]}},
            {"type": "model_output", "content": [{"type": "text", "text": "1. Example"}]},
        ],
        "usage": {},
    }
    with patch("src.llm_providers.gemini_provider.requests.post", return_value=_response(payload)) as post:
        result = call_gemini(
            api_key="test", model="test-model", prompt="Best cleaner?",
            benchmark_mode="consumer_web", location_context="Brighton",
        )

    assert post.call_args.args[0].endswith("/v1beta/interactions")
    assert post.call_args.kwargs["json"]["tools"] == [{"type": "google_search"}]
    assert "Customer location: Brighton" in post.call_args.kwargs["json"]["input"]
    assert result.text == "1. Example"
