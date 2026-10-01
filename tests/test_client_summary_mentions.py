"""End-to-end: mentioned-vs-recommended data flows from a raw payload through to the rendered LS.

Builds on synthetic_owner_services_payload() (its own responses don't set
persisted_target_mentioned/persisted_target_recommended at all, so by default this feature is
inert for it - every existing test using that fixture is unaffected). Here those fields are
injected directly onto the frozen responses, exactly like a real ai_visibility_results row would
carry them, to prove the whole chain (owner_services_report -> client_summary.adapter ->
client_summary.pdf) end to end rather than only unit-testing target_mention_summary in isolation.
"""
from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader

from src.client_summary.adapter import build_client_summary_report, render_client_summary_pdf
from src.owner_services_report import build_owner_report
from src.owner_services_synthetic import synthetic_owner_services_payload


def _payload_with_mentions(*, mentioned_orders=(), recommended_orders=()):
    payload = synthetic_owner_services_payload()
    for response in payload["baseline_validation"]["responses"]:
        order = int(response["base_prompt_order"])
        response["parser_reconciliation"]["persisted_target_mentioned"] = order in mentioned_orders
        response["parser_reconciliation"]["persisted_target_recommended"] = order in recommended_orders
    return payload


def test_build_owner_report_carries_a_target_mention_summary():
    payload = _payload_with_mentions(mentioned_orders={1, 2}, recommended_orders={1})
    report = build_owner_report(payload)
    summary = report["target_mention_summary"]
    assert summary["complete"] == 24  # 4 prompts x 2 repeats x 3 providers, all completed
    assert summary["mentioned"] == 12  # 2 orders x 2 repeats x 3 providers
    assert summary["recommended"] == 6  # 1 order x 2 repeats x 3 providers


def test_the_rendered_ls_shows_both_figures_and_the_gap_table():
    payload = _payload_with_mentions(mentioned_orders={1, 2, 3}, recommended_orders={1})
    summary = build_client_summary_report(payload)
    assert summary["mention_analysis"]["mentioned"] == 18
    assert summary["mention_analysis"]["recommended"] == 6
    text = " ".join(
        p.extract_text() for p in PdfReader(BytesIO(render_client_summary_pdf(summary))).pages
    )
    text = " ".join(text.split())
    assert "MENTIONED VS. RECOMMENDED" in text  # the eyebrow label is upper-cased on render
    assert "18 of 24" in text  # mentioned tile
    assert "6 of 24" in text  # recommended tile
    assert "9 / 12" in text  # page 9 of 12: this fixture also has review data (pages 10-12)


def test_when_mentioned_equals_recommended_the_page_says_so_plainly():
    payload = _payload_with_mentions(mentioned_orders={1}, recommended_orders={1})
    summary = build_client_summary_report(payload)
    assert summary["mention_analysis"]["mentioned"] == summary["mention_analysis"]["recommended"]
    text = " ".join(
        p.extract_text() for p in PdfReader(BytesIO(render_client_summary_pdf(summary))).pages
    )
    assert "there is no gap" in " ".join(text.split())


def test_the_synthetic_fixtures_default_inert_behaviour_is_unaffected():
    # The shared fixture (used by many other tests) sets no persisted_target_mentioned/
    # persisted_target_recommended at all - confirms that's still safe and produces all-zero,
    # not an error, matching every pre-existing test that renders this fixture unmodified.
    payload = synthetic_owner_services_payload()
    summary = build_client_summary_report(payload)
    assert summary["mention_analysis"]["mentioned"] == 0
    assert summary["mention_analysis"]["recommended"] == 0
