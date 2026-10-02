"""All form writes are mocked. Real stores must remain untouched by page loading."""
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
pytest.importorskip('streamlit')
from streamlit.testing.v1 import AppTest

from test_positioning_triangulation import inputs

PAGE = str(Path(__file__).resolve().parents[1] / 'app/pages/13_Positioning.py')


def page(ready=False, *, captures=True, cap_override=None):
    cap, brief, run, questions = inputs()
    cap.update(archived_at="2026-10-02T09:00:00+00:00")
    stack = ExitStack()
    values = {
        'src.evidence_foundations_repository.list_foundation_businesses': [{"google_place_id": "place", "business_name": "Synthetic salon"}],
        'src.evidence_foundations_repository.list_business_runs': [{**run, "started_at": "2026-09-01"}],
        'src.evidence_foundations_repository.load_confirmed_question_map': {"1": "Balayage"},
        'src.evidence_foundations_repository.load_measurement_wave': None,
        'src.positioning_repository.load_owner_brief': brief,
        'src.positioning_repository.load_approved_actions': [],
        'src.public_evidence_archive_repository.list_captures': [cap] if captures else [],
        'src.public_evidence_archive_repository.load_capture': cap_override or cap,
        'src.public_evidence_archive_repository.list_decisions': [],
        'src.ai_visibility_repository.get_run_queries': pd.DataFrame(questions),
        'src.intervention_repository.intervention_storage_ready': ready,
        'src.intervention_repository.list_interventions': [],
    }
    for target, value in values.items(): stack.enter_context(patch(target, return_value=value))
    writer = stack.enter_context(patch('src.intervention_repository.save_intervention', return_value='saved-action'))
    at = AppTest.from_file(PAGE).run()
    return at, stack, writer


def fill(at):
    next(t for t in at.text_area if t.label == 'Observed finding').set_value('Candidate evidence requires review')
    next(t for t in at.text_area if t.label == 'Action and hypothesis to test').set_value('Review preserved source context first')
    next(t for t in at.text_area if t.label == 'Reason for this action record or revision').set_value('Initial investigation')
    next(t for t in at.text_input if t.label == 'Action owner').set_value('Operator')
    next(t for t in at.text_input if t.label == 'Recording operator').set_value('Reviewer')
    evidence = next(m for m in at.multiselect if m.label == 'Affected evidence')
    evidence.set_value([inputs()[0]['payload']['matrix']['observations'][0]['evidence_id']])


@pytest.mark.parametrize('ready', [True, False])
def test_read_only_loading_never_saves_or_auto_approves(ready):
    at, stack, writer = page(ready)
    with stack:
        assert not at.exception and not at.error and not writer.called
        frame = at.dataframe[0].value
        assert frame['customer_support_records'].isna().all()
        assert next(b for b in at.button if b.label == 'Save action revision').disabled is not ready


def test_missing_archive_prevents_action_form():
    at, stack, writer = page(captures=False)
    with stack:
        assert not at.exception and not writer.called
        assert any('Archive saved evidence' in i.value for i in at.info)
        assert not at.text_input and not at.button


def test_draft_validation_is_available_without_schema_and_never_writes():
    at, stack, writer = page(False)
    with stack:
        fill(at)
        next(b for b in at.button if b.label == 'Prepare validated draft').click()
        at.run()
        assert not at.exception and not at.error and not writer.called
        assert any(e.type == 'download_button' for e in at)


def test_explicit_save_preserves_unknown_dates_and_does_not_invent_series():
    at, stack, writer = page(True)
    with stack:
        fill(at)
        next(b for b in at.button if b.label == 'Save action revision').click()
        at.run()
        assert not at.exception and not at.error and writer.call_count == 1
        value = writer.call_args.args[0]
        assert value['implemented_date'] is None and value['completion_evidence'] == []
        assert value['baseline_series_id'] is None and value['approved_action_id'] is None
        assert value['created_by'] == 'Reviewer' and value['finding_snapshot']['capture_sha256']


def test_implemented_action_without_actual_evidence_is_blocked_before_writer():
    at, stack, writer = page(True)
    with stack:
        fill(at)
        next(s for s in at.selectbox if s.label == 'Action status').select('IMPLEMENTED')
        next(b for b in at.button if b.label == 'Save action revision').click()
        at.run()
        assert not at.exception and not writer.called
        assert any('actual date' in e.value for e in at.error)


def test_selected_run_links_confirmed_questions_and_leaves_series_unknown():
    at, stack, writer = page(True)
    with stack:
        run = next(s for s in at.selectbox if s.label == 'Benchmark')
        run.select_index(1)
        at.run()
        assert not at.exception and not at.error and not writer.called
        assert bool(at.dataframe[0].value.loc[at.dataframe[0].value['proposition']=='Balayage','tested'].iloc[0])
