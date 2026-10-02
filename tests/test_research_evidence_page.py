from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from src.research_evidence import build_dataset
from test_focused_monitoring import fixture,summary
from test_research_evidence import evidence

PAGE=str(Path(__file__).resolve().parents[1]/"app/pages/15_Evidence_Research.py")


def page(dataset):
    stack=ExitStack()
    run={**fixture()["run"],"target_business_name":"Synthetic Salon"}
    stack.enter_context(patch("src.research_evidence_repository.list_research_runs",return_value=[run]))
    loader=stack.enter_context(patch("src.research_evidence_repository.load_research_dataset",return_value=dataset))
    at=AppTest.from_file(PAGE).run()
    return at,stack,loader,run


def test_initial_load_does_not_fetch_evidence_until_selection():
    at,stack,loader,_=page({})
    with stack:
        assert not at.exception and not loader.called
        assert not at.button


def test_historical_missing_metadata_is_visible_without_fabricated_research():
    old=summary();old.update(wave=None,rows=[],issues=["Historical panel metadata is unavailable"])
    at,stack,loader,run=page(build_dataset([old]))
    with stack:
        at.multiselect[0].set_value([run]).run()
        assert not at.exception and not at.error and loader.called
        assert any("Historical panel metadata" in i.value for i in at.info)
        assert not at.button


def test_research_render_and_small_sample_association():
    cap,d,p=evidence()
    data=build_dataset([summary()],profiles=[p],captures=[cap],decisions=d)
    at,stack,_,run=page(data)
    with stack:
        at.multiselect[0].set_value([run]).run()
        assert not at.exception and not at.error
        at.button[0].click().run()
        assert not at.exception and not at.error
        assert any("Small sample" in c.value for c in at.caption)
