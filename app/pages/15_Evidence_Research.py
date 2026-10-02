"""Internal exploratory evidence view. Every action is read-only."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[2]))
from src.public_evidence_archive import canonical_json
from src.research_evidence import association, FEATURES
from src.research_evidence_repository import list_research_runs, load_research_dataset

st.set_page_config(page_title="Evidence research", page_icon="🔬", layout="wide")
st.title("Evidence research")
st.caption("Internal exploration of saved measurements and dated evidence. Associations describe this selected sample; they do not establish AI ranking factors or causes.")
try:
    runs = list_research_runs()
except Exception as exc:
    st.error(f"Saved runs could not be loaded ({type(exc).__name__}).")
    st.stop()
st.caption("Showing the latest 100 saved runs. Select up to ten; no collection or paid test is triggered.")
chosen = st.multiselect("Saved measurement waves", runs, max_selections=10,
    format_func=lambda r: f"{r['target_business_name']} · {r['started_at']} · {r['id']}")
age = st.number_input("Maximum evidence age at measurement (days)", min_value=1, max_value=3650, value=90)
if not chosen:
    st.info("Select saved waves to inspect their eligibility. Historical runs without a frozen family/cohort plan will show an exclusion reason.")
    st.caption("Prepare a focused measurement panel in Focused Monitoring, available from the sidebar.")
    st.stop()
try:
    dataset = load_research_dataset([str(r["id"]) for r in chosen], max_age_days=int(age))
except ValueError as exc:
    st.error(str(exc))
    st.stop()
except Exception as exc:
    st.error(f"Research evidence could not be loaded ({type(exc).__name__}).")
    st.stop()
rows = dataset["rows"]
eligible = [r for r in rows if r["measurement_eligible"]]
st.write(f"{len(rows)} rows · {len(eligible)} measurement-eligible · {len({r['google_place_id'] for r in eligible})} unique businesses · {len({r['market'] for r in eligible})} markets")
for item in dataset["excluded_runs"]:
    st.info(f"{item['run_id']}: " + "; ".join(item["reasons"]))
if rows:
    st.dataframe(pd.DataFrame([{k:v for k,v in r.items() if k not in {"feature_eligible", "unapproved_possible_names"}} for r in rows]), hide_index=True, width="stretch")
with st.expander("Source timing, exclusions, linking records and limitations"):
    st.json(dataset)
st.download_button("Download research evidence", canonical_json(dataset), file_name="research-evidence.json", mime="application/json")
if not rows:
    st.info("No research rows qualify yet. A new focused wave needs an independently selected cohort and explicit question families.")
    st.stop()
strata = {r["stratum_id"]:r for r in rows}
sid = st.selectbox("Compatible comparison group", list(strata),
    format_func=lambda s: " · ".join(str(strata[s][f] or "unknown") for f in ("family", "provider", "served_model", "market", "benchmark_mode")) + " · " + str(strata[s]["panel_id"])[:10])
feature = st.selectbox("Evidence feature", FEATURES)
log_scale = st.checkbox("Show log1p review count on the scatterplot", disabled=feature != "published_review_count")
st.caption("Raw and log1p review counts have the same Spearman ranks. Log display is not another correlation test. Support rates concern reviewed matching source records, not all customers.")
if st.button("Calculate exploratory association"):
    result = association([r for r in rows if r["stratum_id"] == sid], feature)
    st.write({k:v for k,v in result.items() if k not in {"points", "warnings"}})
    for warning in result["warnings"]:
        st.caption(warning)
    if result["points"]:
        points = pd.DataFrame(result["points"])
        if log_scale and feature == "published_review_count":
            points["log1p published review count"] = points["value"].map(lambda value: math.log1p(float(value)))
            x = "log1p published review count"
        else:
            x = "value"
        st.scatter_chart(points, x=x, y="appearance_rate")
    st.download_button("Download association", canonical_json(result), file_name="research-association.json", mime="application/json")
