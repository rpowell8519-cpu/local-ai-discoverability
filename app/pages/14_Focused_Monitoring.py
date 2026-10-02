"""Operator-controlled focused panels and read-only before/after comparisons."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.evidence_foundations_repository import list_foundation_businesses, list_business_runs, foundation_status, load_measurement_wave
from src.focused_monitoring import focused_panel, compare_waves
from src.focused_monitoring_repository import load_wave_summary, execute_focused_wave
from src.intervention_repository import list_interventions
from src.public_evidence_archive import canonical_json
from src.public_evidence_archive_repository import list_captures, load_capture
from src.report_generator_readiness import ACTIVE_REPORT_PROJECT_KEY

st.set_page_config(page_title="Focused monitoring", page_icon="📈", layout="wide")
st.title("Focused monitoring")
st.caption("Repeat an agreed question panel and inspect change alongside the same selected businesses. Focused panels have separate identities and denominators from the main benchmark. No runs start on page load.")
try:
    businesses = list_foundation_businesses()
except Exception as exc:
    st.error(f"Businesses could not be loaded ({type(exc).__name__}).")
    st.stop()
if not businesses:
    st.info("No canonical businesses are available.")
    st.stop()
active = st.session_state.get(ACTIVE_REPORT_PROJECT_KEY)
index = next((i for i,b in enumerate(businesses) if b["google_place_id"] == active), 0)
business = st.selectbox("Business", businesses, index=index, format_func=lambda b: b["business_name"])
pid = str(business["google_place_id"])
try:
    runs = list_business_runs(pid)
    actions = list_interventions(pid)
    captures = list_captures(pid)
    ready = foundation_status().get("ai_measurement_waves", False)
except Exception as exc:
    st.error(f"Monitoring inputs could not be loaded ({type(exc).__name__}).")
    st.stop()

st.subheader("Prepare a focused panel")
st.caption("Record agreed questions verbatim. Select businesses for geographic/service relevance before seeing their results, including businesses with no appearances. The selected cohort applies to every family; explain that eligibility below.")
peers = [b for b in businesses if str(b["google_place_id"]) != pid and b.get("primary_group") == business.get("primary_group")]
with st.form(f"focused_plan_{pid}"):
    text = st.text_area("Questions: family | exact question (one per line)", placeholder="balayage | Which salons in Brighton offer balayage?")
    providers = st.multiselect("Providers", ["OpenAI", "Claude", "Gemini"], default=[])
    models = {p: st.text_input(f"Requested {p} model", value="") for p in ("OpenAI", "Claude", "Gemini")}
    location = st.text_input("Customer location", value="")
    repeat = st.number_input("Repeats per question/provider", min_value=1, max_value=10, value=3)
    mode = st.selectbox("Measurement mode", ["search_grounded", "model_memory"])
    cohort = st.multiselect("Comparison businesses", peers, format_func=lambda b: b["business_name"])
    basis = st.text_area("Why these businesses are eligible for every selected family and location")
    operator = st.text_input("Configuring operator")
    linked = st.multiselect("Actions to monitor", actions, format_func=lambda a: a["record"]["finding"])
    prepare = st.form_submit_button("Prepare panel")
if prepare:
    try:
        prompts = []
        for line in text.splitlines():
            if not line.strip():
                continue
            if "|" not in line:
                raise ValueError("Separate each explicit family and question with |")
            family, question = line.split("|", 1)
            prompts.append({"family": family.strip(), "prompt": question.strip(), "source": "operator_focused", "category": family.strip()})
        if not location.strip():
            raise ValueError("A customer location is required")
        panel = focused_panel(prompts=prompts, providers=providers, models=models, location_context=location.strip(),
            primary_group=business.get("primary_group") or "", repeat_count=int(repeat), benchmark_mode=mode,
            comparator_ids=[b["google_place_id"] for b in cohort], cohort_basis=basis, configured_by=operator,
            action_ids=[a["action_id"] for a in linked])
        st.session_state[f"focused_panel_{pid}"] = panel
    except ValueError as exc:
        st.session_state.pop(f"focused_panel_{pid}", None)
        st.error(str(exc))
panel = st.session_state.get(f"focused_panel_{pid}")
if panel:
    config = panel["configuration"]
    calls = len(config["prompts"])*config["repeat_count"]*len(config["providers"])
    st.write(f"Prepared panel: {calls} paid provider calls for a new wave. Check the current provider pricing before running.")
    with st.expander("Prepared configuration"):
        st.json(panel)
    st.download_button("Download focused panel", canonical_json(panel), file_name="focused-panel.json", mime="application/json")
    approved = st.checkbox("The owner has agreed these questions and I authorise the paid calls", key=f"focused_paid_{pid}_{panel['panel_id']}")
    if st.button("Run focused wave (paid)", disabled=not ready or not approved):
        try:
            keys = {p: str(st.secrets.get(key, "") or "") for p,key in {"OpenAI": "OPENAI_API_KEY", "Claude": "ANTHROPIC_API_KEY", "Gemini": "GEMINI_API_KEY"}.items()}
            progress = st.progress(0.0)
            outcome = execute_focused_wave(panel=panel, business=business, businesses=businesses, api_keys=keys,
                progress_callback=lambda done,total: progress.progress(done/total))
            st.success(f"Saved focused wave {outcome['run_id']}: {outcome['status']}.")
        except ValueError as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(f"Wave interrupted ({type(exc).__name__}); inspect saved runs below before starting another wave.")
if not ready:
    st.info("Focused execution requires the existing measurement-wave store. Prepare/export remains available.")

st.subheader("Inspect saved waves")
label = lambda r: "No wave selected" if r is None else f"{r['started_at']} · {r['id']}"
before_run = st.selectbox("Before wave", [None, *runs], format_func=label)
after_run = st.selectbox("After wave", [None, *runs], format_func=label)
summaries = []
for label_text, run in (("Before", before_run), ("After", after_run)):
    if run:
        try:
            summary = load_wave_summary(run, businesses)
            summaries.append(summary)
            st.write(f"{label_text}: {run['id']}")
            for issue in summary["issues"]:
                st.info(issue)
            st.dataframe(pd.DataFrame(summary["rows"]), hide_index=True, width="stretch")
            with st.expander(f"{label_text} models, citations, tool use and unresolved names"):
                st.json(summary)
            wave = summary["wave"]
            if wave and wave.get("panel_kind") == "focused":
                agree = st.checkbox(f"Authorise paid retry of missing/incomplete {label_text.lower()} answers", key=f"retry_paid_{run['id']}_{label_text}")
                if st.button(f"Retry {label_text.lower()} focused wave (paid)", disabled=not agree):
                    try:
                        keys = {p: str(st.secrets.get(key, "") or "") for p,key in {"OpenAI": "OPENAI_API_KEY", "Claude": "ANTHROPIC_API_KEY", "Gemini": "GEMINI_API_KEY"}.items()}
                        outcome = execute_focused_wave(panel=wave, business=business, businesses=businesses, api_keys=keys, run_id=str(run["id"]))
                        st.success(f"Retried {outcome['attempted_calls']} calls; reload the saved wave to inspect results.")
                    except ValueError as exc:
                        st.error(str(exc))
                    except Exception as exc:
                        st.error(f"Retry interrupted ({type(exc).__name__}).")
        except Exception as exc:
            st.error(f"Saved wave could not be loaded ({type(exc).__name__}).")
capture = st.selectbox("Evidence capture for freshness (optional)", [None, *captures],
    format_func=lambda c: "No evidence selected" if c is None else f"{c['archived_at']} · {c['id']}")
minimum = st.number_input("Minimum eligible comparators for contextual change", min_value=1, value=3)
if before_run and after_run and len(summaries) == 2:
    try:
        evidence = []
        if capture:
            cap = load_capture(str(capture["id"]))
            if str(cap["google_place_id"]) != pid:
                raise ValueError("Evidence capture belongs to another business")
            evidence = [{k: o.get(k) for k in ("evidence_id", "source_record_id", "source_class", "captured_at", "source_published_at")}
                        for o in cap["payload"]["matrix"]["observations"]]
        comparison = compare_waves(*summaries, interventions=actions, evidence=evidence, minimum_comparators=int(minimum))
        if comparison["compatible"]:
            st.success("Configuration, served identifiers and complete answer grids are compatible.")
        else:
            for reason in comparison["reasons"]:
                st.info(reason)
        st.dataframe(pd.DataFrame(comparison["rows"]), hide_index=True, width="stretch")
        for warning in comparison["warnings"]:
            st.caption(warning)
        st.caption(comparison["interpretation"])
        with st.expander("Comparison provenance, action timing and source freshness"):
            st.json(comparison)
        st.download_button("Download comparison", canonical_json(comparison), file_name="focused-comparison.json", mime="application/json")
    except ValueError as exc:
        st.error(str(exc))
