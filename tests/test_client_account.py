import pytest

from src.client_account import carry_forward, competitor_names, project_test, undecided_client_names


def answer(prompt, provider, names, citations=(), order=1, status="completed"):
    text = "\n".join(f"{i}. **{name}** - a good choice" for i, name in enumerate(names, 1))
    return {"prompt_text": prompt, "base_prompt_order": order, "run_order": 0, "provider": provider, "status": status,
            "response_complete": True, "raw_response": text, "report_metadata": {"citations": [{"url": u} for u in citations]}}


DECISIONS = carry_forward(None, client_names=["WRAP Brighton"], short_name="WRAP", own_domains=["https://www.wrap.space/"])
DECISIONS["prompt_sets"] = {"Coworking in Brighton": "Core"}


def test_counts_each_answer_once_by_tool_and_keeps_competitor_spellings_together():
    rows = [
        answer("Coworking in Brighton", "openai", ["WRAP Brighton", "Runway East", "Runway East Brighton"], ["https://wrap.space/x", "https://runwayea.st"]),
        answer("Coworking in Brighton", "claude", ["Runway East"], ["https://runwayea.st/a", "https://runwayea.st/b"]),
        answer("Coworking in Brighton", "gemini", ["WRAP", "Plus X"]),
        answer("Coworking in Brighton", "gemini", ["WRAP"], status="failed"),
    ]
    decisions = {**DECISIONS, "competitor_groups": {"Runway East": ["Runway East Brighton"]}}
    prompt = project_test(rows, decisions, tested_on="2026-10-09")["prompts"][0]
    assert (prompt["recommended"], prompt["answers"], prompt["set"]) == (2, 3, "Core")
    assert prompt["providers"] == {"OpenAI": {"answers": 1, "recommended": 1}, "Claude": {"answers": 1, "recommended": 0},
                                   "Gemini": {"answers": 1, "recommended": 1}}
    assert prompt["competitors"] == [{"name": "Runway East", "answers": 2}, {"name": "Plus X", "answers": 1}]
    assert prompt["sources"] == [{"domain": "runwayea.st", "answers": 2}]
    assert prompt["own_site_answers"] == 1
    assert "raw_response" not in str(project_test(rows, decisions, tested_on="2026-10-09"))


def test_short_name_matches_only_in_its_own_letter_case():
    rows = [answer("Coworking in Brighton", "openai", ["Wrap Café"])]
    assert undecided_client_names(rows, DECISIONS) == [{"name": "Wrap Café", "answers": 1}]
    with pytest.raises(ValueError, match="Wrap Café"):
        project_test(rows, DECISIONS, tested_on="2026-10-09")
    rejected = {**DECISIONS, "rejected_names": ["Wrap Café"]}
    prompt = project_test(rows, rejected, tested_on="2026-10-09")["prompts"][0]
    assert prompt["recommended"] == 0 and prompt["competitors"] == [{"name": "Wrap Café", "answers": 1}]


def test_carry_forward_keeps_earlier_decisions_and_adds_reviewed_names():
    earlier = {**DECISIONS, "rejected_names": ["Wrap Café"], "competitor_groups": {"Runway East": ["Runway East Brighton"]}}
    carried = carry_forward(earlier, client_names=["WRAP Brighton", "WRAP Coworking"])
    assert carried["client_names"] == ["WRAP Brighton", "WRAP Coworking"]
    assert carried["rejected_names"] == ["Wrap Café"] and carried["own_domains"] == ["wrap.space"]
    assert carried["prompt_sets"] == {"Coworking in Brighton": "Core"}
    assert competitor_names([answer("Coworking in Brighton", "openai", ["Runway East Brighton"])], carried)[0]["name"] == "Runway East"


def test_a_prompt_note_travels_with_the_published_prompt_and_is_carried_forward():
    decisions = {**DECISIONS, "prompt_notes": {"Coworking in Brighton": "  Read with  care. "}}
    prompt = project_test([answer("Coworking in Brighton", "openai", ["WRAP"])], decisions, tested_on="2026-10-09")["prompts"][0]
    assert prompt["note"] == "Read with care."
    assert carry_forward(decisions)["prompt_notes"] == {"Coworking in Brighton": "  Read with  care. "}
    assert "note" not in project_test([answer("Coworking in Brighton", "openai", ["WRAP"])], DECISIONS, tested_on="x")["prompts"][0]


def test_plan_actions_are_numbered_titled_and_given_a_known_status():
    from src.client_account import clean_plan_actions
    actions = clean_plan_actions([{"title": "  Name the  service ", "status": "done"}, {"title": ""}, {"title": "Listings", "status": "maybe"}])
    assert [(a["number"], a["title"], a["status"]) for a in actions] == [("01", "Name the service", "done"), ("02", "Listings", "proposed")]
    with pytest.raises(ValueError):
        clean_plan_actions([{"title": " "}])
