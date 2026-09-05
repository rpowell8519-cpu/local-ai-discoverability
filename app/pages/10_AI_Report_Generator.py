from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from src.poc_audit_production import (  # noqa: E402
    build_reviewable_poc_audit,
    list_report_generator_definitions,
)


BUILD_VERSION = "Accessible AI Report Generator v1.0"
REPORT_STATE_KEY = "accessible_ai_report_generator_result"


st.set_page_config(
    page_title="AI Report Generator",
    page_icon="📄",
    layout="wide",
)

st.title("AI Report Generator")
st.caption(
    "Create the accessible client report from evidence already collected for a "
    "report-ready business."
)
st.caption(f"Build: {BUILD_VERSION}")

st.info(
    "This page only assembles and formats saved evidence. It does not run a new AI "
    "benchmark, collect new website or review data, or freeze a report snapshot."
)

definitions = list_report_generator_definitions()

if not definitions:
    st.warning(
        "No businesses are report-ready yet. Complete the business's owner priorities, "
        "benchmark evidence and report configuration before generating its report."
    )
    st.stop()

definitions_by_key = {definition.key: definition for definition in definitions}
selected_key = st.selectbox(
    "Business",
    options=list(definitions_by_key),
    format_func=lambda key: definitions_by_key[key].client_name,
    help="Only businesses configured for this exact report structure are listed.",
)
definition = definitions_by_key[selected_key]

with st.container(border=True):
    st.markdown(f"**Selected business:** {definition.client_name}")
    st.caption(
        f"Saved benchmark: {definition.baseline_run_id} · "
        f"Google Place ID: {definition.target_google_place_id}"
    )
    generate = st.button(
        "Generate report from saved evidence",
        type="primary",
        use_container_width=True,
    )

if generate:
    try:
        with st.spinner("Assembling the saved evidence and laying out the report…"):
            reviewable = build_reviewable_poc_audit(definition)
    except Exception as exc:
        st.error(
            "The report could not be generated from the configured evidence. "
            "No benchmark was run and no data was changed."
        )
        st.exception(exc)
    else:
        st.session_state[REPORT_STATE_KEY] = reviewable

reviewable = st.session_state.get(REPORT_STATE_KEY)
if reviewable is not None and reviewable.definition.key == selected_key:
    st.success("The reviewable PDF is ready.")
    st.download_button(
        "Download PDF",
        data=reviewable.pdf_bytes,
        file_name=reviewable.definition.pdf_filename,
        mime="application/pdf",
        type="primary",
        use_container_width=True,
    )
    st.caption(
        "This is a reviewable draft generated in memory. Downloading it does not "
        "freeze or save a report snapshot."
    )

st.divider()
st.subheader("Adding another business")
st.write(
    "A business appears here once its owner priorities, customer questions, comparison "
    "group and supporting website and review evidence have been checked and added to "
    "the report registry. That keeps the report useful and evidence-led rather than "
    "filling important judgements automatically."
)
