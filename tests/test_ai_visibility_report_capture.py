from src.ai_visibility_report_capture import provider_report_metadata


def test_openai_structured_citations_and_refusal_are_captured():
    payload = {
        "output": [{"type": "message", "content": [
            {"type": "output_text", "text": "Answer", "annotations": [
                {"type": "url_citation", "url_citation": {"url": "https://example.com/a", "title": "Example"}},
                {"type": "url_citation", "url_citation": {"url": "https://example.com/a", "title": "Duplicate"}},
                {"type": "url_citation", "url_citation": {"url": "javascript:alert(1)"}},
            ]},
            {"type": "refusal", "refusal": "Can't assist"},
        ]}],
    }
    result = provider_report_metadata("OpenAI", payload, "search_grounded")
    assert result["citation_status"] == "measured"
    assert result["citations"] == [{"url": "https://example.com/a", "title": "Example"}]
    assert result["refused"] is True


def test_anthropic_and_gemini_citations_are_captured():
    anthropic = provider_report_metadata("Claude", {
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": "Answer", "citations": [
            {"type": "web_search_result_location", "url": "https://news.example/story", "title": "Story"}
        ]}],
    }, "search_grounded")
    gemini = provider_report_metadata("Gemini", {
        "steps": [{"type": "model_output", "content": [{"type": "text", "annotations": [
            {"type": "url_citation", "url": "https://docs.example/page", "title": "Docs"}
        ]}]}],
    }, "search_grounded")
    assert anthropic["citations"][0]["url"] == "https://news.example/story"
    assert gemini["citations"][0]["url"] == "https://docs.example/page"


def test_missing_citation_metadata_is_unavailable_not_zero():
    result = provider_report_metadata("Gemini", {"steps": []}, "search_grounded")
    assert result["citation_status"] == "unavailable"
    assert result["citations"] == []


def test_reported_model_is_kept_separately_without_inventing_a_missing_version():
    result = provider_report_metadata("OpenAI", {"model": "returned-model-version"}, "search_grounded")
    assert result["reported_model"] == "returned-model-version"
    assert result["model_version_status"] == "reported_identifier"
    result = provider_report_metadata("Gemini", {}, "model_memory")
    assert result["reported_model"] is None and result["model_version_status"] == "unavailable"


def test_actual_search_markers_are_preserved_without_inference_from_mode_or_citations():
    for provider,payload in (("OpenAI", {"output": [{"type": "web_search_call", "id": "search", "status": "completed", "action": {"type": "search", "query": "salons"}}]}),
                            ("Claude", {"content": [{"type": "server_tool_use", "name": "web_search", "input": {"query": "salons"}}]}),
                            ("Gemini", {"steps": [{"type": "google_search_call", "id": "search"}]})):
        captured = provider_report_metadata(provider,payload,"search_grounded")
        assert captured["search_use_status"] == "observed" and len(captured["search_calls"]) == 1
    absent = provider_report_metadata("OpenAI", {"output": []}, "search_grounded")
    assert absent["search_use_status"] == "unavailable" and absent["search_calls"] == []
