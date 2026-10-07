from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from test_focused_monitoring import fixture, DIRECTORY, summary

PAGE = str(Path(__file__).resolve().parents[1]/"app/shelved_pages/14_Focused_Monitoring.py")


def page():
    stack = ExitStack()
    values = {"src.evidence_foundations_repository.list_foundation_businesses": DIRECTORY,
              "src.evidence_foundations_repository.list_business_runs": [fixture()["run"],fixture(True)["run"]],
              "src.evidence_foundations_repository.foundation_status": {"ai_measurement_waves": True},
              "src.intervention_repository.list_interventions": [],
              "src.public_evidence_archive_repository.list_captures": []}
    for key,value in values.items(): stack.enter_context(patch(key,return_value=value))
    stack.enter_context(patch("src.focused_monitoring_repository.load_wave_summary", side_effect=lambda r,b: summary(r["id"]=="after")))
    writer = stack.enter_context(patch("src.focused_monitoring_repository.execute_focused_wave"))
    return AppTest.from_file(PAGE).run(),stack,writer


def test_page_load_and_comparison_remain_read_only():
    at,stack,writer = page()
    with stack:
        assert not at.exception and not at.error and not writer.called
        next(s for s in at.selectbox if s.label=="Before wave").select_index(1)
        next(s for s in at.selectbox if s.label=="After wave").select_index(2)
        at.run()
        assert not at.exception and not at.error and not writer.called
        assert any("compatible" in s.value for s in at.success)


def test_preparing_plan_is_free_and_paid_control_requires_explicit_agreement():
    at,stack,writer = page()
    with stack:
        next(t for t in at.text_area if t.label.startswith("Questions:")).set_value("balayage | Which salons offer balayage?")
        next(m for m in at.multiselect if m.label=="Providers").set_value(["OpenAI"])
        next(t for t in at.text_input if t.label=="Requested OpenAI model").set_value("synthetic-model")
        next(t for t in at.text_input if t.label=="Customer location").set_value("Brighton")
        next(t for t in at.text_input if t.label=="Configuring operator").set_value("Operator")
        next(t for t in at.text_area if t.label.startswith("Why these")).set_value("Explicit local service eligibility")
        next(b for b in at.button if b.label=="Prepare panel").click()
        at.run()
        assert not at.exception and not at.error and not writer.called
        assert next(b for b in at.button if b.label=="Run focused wave (paid)").disabled
