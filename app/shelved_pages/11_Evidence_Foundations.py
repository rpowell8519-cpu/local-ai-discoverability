"""Read-only operator inspection of tested-intent and evidence provenance foundations."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.ai_visibility_repository import get_run_queries
from src.evidence_foundations_repository import (
    foundation_status, list_foundation_businesses, list_business_runs, load_catalogue,
    load_confirmed_question_map, load_measurement_wave, load_profile_evidence,
)
from src.proposition_catalog import build_tested_intent_links
from src.public_evidence_repository import load_public_evidence_matrix
from src.report_generator_readiness import ACTIVE_REPORT_PROJECT_KEY

st.set_page_config(page_title="Evidence Foundations", page_icon="🔎", layout="wide")
st.title("Evidence foundations")
st.caption("Internal operator view. Review totals, text samples and tested intent are separate observations; none is an AI ranking score.")


@st.cache_data(ttl=60)
def load_businesses():
    return list_foundation_businesses()


try:
    status = foundation_status()
    businesses = load_businesses()
except Exception as exc:
    st.error(f"Evidence foundations could not be loaded ({type(exc).__name__}).")
    st.stop()

pending = [name for name, available in status.items() if not available]
if pending:
    st.info("The additive migration has not been applied. Existing evidence can be inspected; new stored catalogue/profile history and benchmark-wave metadata are pending.")
if not businesses:
    st.info("No verified businesses are available.")
    st.stop()
active_id = st.session_state.get(ACTIVE_REPORT_PROJECT_KEY)
default = next((i for i, b in enumerate(businesses) if b["google_place_id"] == active_id), 0)
business = st.selectbox("Business", businesses, index=default,
                        format_func=lambda b: f"{b['business_name']} · {b['google_place_id']}")
place_id = str(business["google_place_id"])

try:
    catalogue, aliases, catalogue_source = load_catalogue()
    runs = list_business_runs(place_id)
    profile = load_profile_evidence(place_id)
except Exception as exc:
    st.error(f"This business's evidence could not be loaded ({type(exc).__name__}).")
    st.stop()

profile_tab, intent_tab, panel_tab, matrix_tab = st.tabs(["Review profiles and samples", "Tested intent", "Benchmark provenance", "Public evidence matrix"])
with profile_tab:
    st.subheader("Published profile metrics")
    st.caption("These are dated source captures, not a current refresh. An unknown published count is never replaced with the number of saved texts.")
    observations = profile["profile_observations"]
    if observations:
        st.dataframe(pd.DataFrame(observations), hide_index=True, width="stretch")
    else:
        st.info("Published profile metrics are unknown for this business.")
    if profile["stored_profile_history"]:
        with st.expander("Stored profile metric history"):
            st.dataframe(pd.DataFrame(profile["stored_profile_history"]), hide_index=True)
    st.subheader("Collected review-text samples")
    st.caption("Dates cover only collected texts. Recent platform review velocity and the platform's latest review date cannot be inferred from a capped sample.")
    if profile["samples"]:
        st.dataframe(pd.DataFrame(profile["samples"]), hide_index=True, width="stretch")
    else:
        st.info("No usable review-text sample is stored.")
    if profile["unusable_observations"]:
        st.warning("Some source captures lack usable provenance; their metrics were left unknown.")
        st.dataframe(pd.DataFrame(profile["unusable_observations"]), hide_index=True)

run = None
if runs:
    with intent_tab:
        run = st.selectbox("Benchmark wave", runs,
                           format_func=lambda r: f"{r['started_at']} · {r['benchmark_mode']} · {r['id']}")
        questions = get_run_queries(str(run["id"])).to_dict("records")
        confirmed = load_confirmed_question_map(str(run["id"]), place_id)
        links = build_tested_intent_links(run, questions, confirmed, catalogue, aliases)
        st.caption(f"Catalogue: {catalogue_source}. Labels resolve only through catalogue entries and reviewed aliases; unresolved labels remain visible.")
        st.subheader("Recorded run context")
        st.caption("Source: ai_visibility_runs.target_propositions. Being listed here does not establish that a question tested this proposition.")
        if links["run_context"]:
            st.dataframe(pd.DataFrame(links["run_context"]), hide_index=True, width="stretch")
        else:
            st.info("Historical proposition context is unknown.")
        st.subheader("Confirmed question mappings")
        st.caption("Uses the completed review's question_priority_map for this exact run. This is tested intent, not demand or search volume.")
        st.dataframe(pd.DataFrame(links["tested_questions"]), hide_index=True, width="stretch")
else:
    with intent_tab:
        st.info("No saved benchmark is available for this business.")

with panel_tab:
    st.caption("Panel = frozen configuration. Wave = one run. Series = compatible waves. Core and focused panels retain separate identities and denominators.")
    wave = load_measurement_wave(str(run["id"])) if run else None
    if wave:
        st.write({key: str(wave[key]) for key in ("run_id", "series_id", "panel_id", "panel_kind", "configuration_sha256")})
        st.json(wave["configuration"])
        st.info("Requested models are recorded; served model identifiers are preserved separately when providers report them. Unknown model versions prevent a verified before/after comparison.")
    else:
        st.info("This run has no frozen panel metadata. It remains valid historical evidence, but is not automatically assigned to a comparison series.")

with matrix_tab:
    st.caption("Read-only preview over saved sources. Collection, fact comparison and proposition candidates are separate. No new collection or report changes occur here.")
    try:
        matrix = load_public_evidence_matrix(business, catalogue, aliases)
    except Exception as exc:
        st.error(f"The saved-source matrix could not be loaded ({type(exc).__name__}).")
    else:
        st.subheader("What was collected")
        st.dataframe(pd.DataFrame(matrix["collection"]), hide_index=True, width="stretch")
        st.subheader("Contact fact comparison")
        st.caption("The Google capture is a comparison source, not an approved truth. MISSING means no value in the checked saved text; it is not a claim about the whole website.")
        st.dataframe(pd.DataFrame(matrix["facts"]), hide_index=True, width="stretch")
        st.subheader("Proposition evidence candidates")
        st.caption("Exact phrase matches and polarity hints require operator review. Candidate source counts are not substantive evidence breadth. Tested intent remains linked to the existing run context and confirmed question mappings in the Tested intent tab.")
        if matrix["propositions"]:
            st.dataframe(pd.DataFrame(matrix["propositions"]), hide_index=True, width="stretch")
        else:
            st.info("No proposition phrase candidates were found in these saved texts. This does not establish that the business lacks those strengths.")
        if matrix["observations"]:
            with st.expander("Underlying evidence: exact excerpts, source records and capture dates"):
                st.dataframe(pd.DataFrame(matrix["observations"]), hide_index=True, width="stretch",
                             column_config={"source_url": st.column_config.LinkColumn("Source URL")})
        for limitation in matrix["limitations"]:
            st.caption(limitation)
