"""Standalone GSO report preview using the package's clearly labelled sample."""

import json
from pathlib import Path
import sys

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from gso_report.page import render_report
from gso_report.schema import Report


SAMPLE_REPORT = PROJECT_ROOT / "gso_report" / "sample_report.json"
UDR_REPORT = PROJECT_ROOT / "gso_report" / "udr_aggregate_report.json"
UDR_SOURCE = PROJECT_ROOT / "gso_report" / "udr_aggregate_source.json"
UDR_HTML = PROJECT_ROOT / "gso_report" / "udr-properties-aggregate-report.html"

st.set_page_config(page_title="AI Visibility Report", page_icon="📊", layout="wide")
choice = st.sidebar.radio(
    "Report data",
    ["UDR Properties · 24 Sep aggregate import", "Sample data · fictional"],
)

if choice.startswith("UDR Properties"):
    report = Report.model_validate_json(UDR_REPORT.read_text(encoding="utf-8"))
    source = json.loads(UDR_SOURCE.read_text(encoding="utf-8"))
    st.warning(
        "AGGREGATE-ONLY IMPORT — The source PDF reports 72 answers, but individual answer records "
        "are not available here. The report leaves observation-derived metrics as N/A; source counts "
        "below are transcribed and have not been independently recounted."
    )
    render_report(report, key="gso_udr_aggregate_report")

    st.header("Source-reported aggregate appendix")
    st.caption(source["source"])
    kpi_cols = st.columns(3)
    kpi_cols[0].metric("Reported UDR appearances", f"{source['appearances']} / {source['answers']}")
    kpi_cols[1].metric("Topics with printed appearances", "3 / 8")
    kpi_cols[2].metric("Answer-level records imported", "0 / 72")

    st.subheader("UDR appearances by provider")
    st.dataframe(source["providers"], hide_index=True, width="stretch")
    st.subheader("UDR appearances by source topic")
    st.dataframe(source["topics"], hide_index=True, width="stretch")
    st.subheader("Businesses named by UDR")
    st.dataframe(source["named_competitors"], hide_index=True, width="stretch")
    st.subheader("Most visible businesses in the source answers")
    st.dataframe(source["ai_discovered_businesses"], hide_index=True, width="stretch")
    st.caption(
        "These are source-reported appearance counts, not an answer-level recalculation, "
        "industry benchmark, market share or measure of business quality."
    )

    st.download_button(
        "Download printable UDR report with aggregate appendix",
        UDR_HTML.read_text(encoding="utf-8"),
        file_name="udr-properties-ai-visibility-aggregate-report.html",
        mime="text/html",
        key="gso_udr_aggregate_printable",
    )
    st.download_button(
        "Download source aggregate data (JSON)",
        UDR_SOURCE.read_text(encoding="utf-8"),
        file_name="udr-properties-source-aggregates.json",
        mime="application/json",
        key="gso_udr_aggregate_source_json",
    )
else:
    report = Report.model_validate_json(SAMPLE_REPORT.read_text(encoding="utf-8"))
    render_report(report, key="gso_sample_report")
