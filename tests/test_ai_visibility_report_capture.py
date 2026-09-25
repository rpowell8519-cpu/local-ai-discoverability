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
