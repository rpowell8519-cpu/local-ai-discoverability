from contextlib import ExitStack
from unittest.mock import patch

import pandas as pd
import pytest

from src.focused_monitoring_repository import execute_focused_wave
from test_focused_monitoring import fixture, DIRECTORY


def execute(**kwargs):
    return execute_focused_wave(panel=fixture()["wave"], business=DIRECTORY[0], businesses=DIRECTORY,
                                api_keys={"OpenAI": "synthetic-key"}, **kwargs)


def mocked():
    stack = ExitStack()
    mocks = {}
    values = {"create_visibility_run": "synthetic-run", "create_visibility_queries": fixture()["queries"],
              "execute_calls": None, "finalise_run_from_results": "completed"}
    for name,value in values.items():
        mocks[name] = stack.enter_context(patch("src.focused_monitoring_repository."+name, return_value=value))
    return stack, mocks


def test_explicit_focused_execution_freezes_settings_and_uses_existing_runner():
    stack,m = mocked()
    with stack:
        result = execute()
        assert result["run_id"] == "synthetic-run" and result["attempted_calls"] == 2
        args = m["create_visibility_run"].call_args.kwargs
        assert args["panel_kind"] == "focused" and args["panel_settings"]["comparator_ids"]
        assert len(m["execute_calls"].call_args.kwargs["call_plan"]) == 2


def test_changed_adapter_and_missing_key_block_before_any_write():
    for change in ("adapter", "key"):
        stack,m = mocked()
        with stack:
            panel = fixture()["wave"]
            if change == "adapter": panel["configuration"]["adapter_sha256"]["OpenAI"] = "stale"
            with pytest.raises(ValueError):
                execute_focused_wave(panel=panel, business=DIRECTORY[0], businesses=DIRECTORY,
                    api_keys={} if change == "key" else {"OpenAI": "synthetic"})
            assert not m["create_visibility_run"].called and not m["execute_calls"].called


def test_retry_only_calls_incomplete_answers_and_retains_run_identity():
    stack,m = mocked()
    with stack, patch("src.ai_visibility_repository.get_visibility_run", return_value=fixture()["run"]), \
        patch("src.focused_monitoring_repository.load_measurement_wave", return_value=fixture()["wave"]), \
        patch("src.focused_monitoring_repository.get_run_queries", return_value=pd.DataFrame(fixture()["queries"])), \
        patch("src.focused_monitoring_repository.get_run_results", return_value=pd.DataFrame(fixture()["results"][:1])):
        result = execute(run_id="before")
        assert result["attempted_calls"] == 1 and result["run_id"] == "before"
        assert not m["create_visibility_run"].called and not m["create_visibility_queries"].called
        assert m["execute_calls"].call_args.kwargs["call_plan"][0]["id"] == "q2"


def test_retry_rejects_changed_saved_question_before_paid_call():
    stack,m=mocked()
    queries=fixture()["queries"]
    queries[0]["prompt_text"]="Edited question"
    with stack, patch("src.ai_visibility_repository.get_visibility_run", return_value=fixture()["run"]), \
        patch("src.focused_monitoring_repository.load_measurement_wave", return_value=fixture()["wave"]), \
        patch("src.focused_monitoring_repository.get_run_queries", return_value=pd.DataFrame(queries)):
        with pytest.raises(ValueError,match="do not retry"):
            execute(run_id="before")
        assert not m["execute_calls"].called
