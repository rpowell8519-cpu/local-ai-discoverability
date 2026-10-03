from contextlib import contextmanager
from unittest.mock import patch

import pytest

from src.ai_visibility_repository import get_latest_run, create_visibility_run
from test_evidence_foundations import Connection


class Result:
    def mappings(self): return self
    def first(self): return {"id": "core-run"}
    def scalar_one(self): return True


class ReadConnection:
    def __init__(self): self.sql = []
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def execute(self,statement,params=None):
        self.sql.append(str(statement))
        return Result()


class Engine:
    def __init__(self,connection): self.connection=connection
    def connect(self): return self.connection
    @contextmanager
    def begin(self): yield self.connection


def test_main_benchmark_latest_selector_excludes_focused_runs():
    connection = ReadConnection()
    with patch("src.ai_visibility_repository.get_engine",return_value=Engine(connection)):
        assert get_latest_run("target")["id"] == "core-run"
    assert "not exists" in connection.sql[-1] and "w.panel_kind<>'core'" in connection.sql[-1]


def test_focused_run_requires_wave_storage_and_cannot_silently_become_core():
    with patch("src.ai_visibility_repository.get_engine",return_value=Engine(Connection(ready=False))):
        with pytest.raises(ValueError,match="measurement-wave storage"):
            create_visibility_run(target_google_place_id="target",target_business_name="Synthetic salon",
                primary_group="hair_services",location_context="Brighton",providers=["OpenAI"],models={"OpenAI":"requested"},
                prompt_count=1,prompts=[{"prompt":"Which salons offer balayage?"}],panel_kind="focused")


def test_free_check_run_requires_frozen_panel_and_wave_storage():
    common=dict(target_google_place_id="target",target_business_name="Synthetic bistro",primary_group="restaurants",
        location_context="Hove",providers=["OpenAI"],models={"OpenAI":"requested"},prompt_count=1,panel_kind="free_check")
    with patch("src.ai_visibility_repository.get_engine",return_value=Engine(Connection(ready=False))):
        with pytest.raises(ValueError,match="frozen prompt panel"):
            create_visibility_run(**common)
        with pytest.raises(ValueError,match="measurement-wave storage"):
            create_visibility_run(**common,prompts=[{"prompt":"Where is good for private dining in Hove?"}])


def test_unknown_panel_kind_is_rejected():
    with pytest.raises(ValueError,match="Panel kind"):
        create_visibility_run(target_google_place_id="target",target_business_name="Synthetic bistro",
            primary_group="restaurants",location_context="Hove",providers=["OpenAI"],models={"OpenAI":"requested"},
            prompt_count=1,prompts=[{"prompt":"Where is good for private dining in Hove?"}],panel_kind="invented")
