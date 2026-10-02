"""Positioning suggestions and explicit action drafts; loading is read-only."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.ai_visibility_repository import get_run_queries
from src.evidence_foundations_repository import list_foundation_businesses, list_business_runs, load_confirmed_question_map, load_measurement_wave
from src.intervention_repository import intervention_storage_ready, list_interventions, list_intervention_history, save_intervention
from src.interventions import VERSION, STATUSES, PRIORITIES, new_action_id, validate_intervention
from src.positioning_repository import load_owner_brief, load_approved_actions
from src.positioning_triangulation import triangulate, TriangulationRules
from src.public_evidence_archive import canonical_json
from src.public_evidence_archive_repository import list_captures, load_capture, list_decisions
from src.report_generator_readiness import ACTIVE_REPORT_PROJECT_KEY

st.set_page_config(page_title="Positioning and actions", page_icon="🧭", layout="wide")
st.title("Positioning and actions")
st.caption("Compare recorded owner priorities, reviewed customer evidence and confirmed tested questions. Suggestions are provisional; they do not measure demand or explain AI rankings.")
try:
    businesses = list_foundation_businesses()
except Exception as exc:
    st.error(f"Businesses could not be loaded ({type(exc).__name__}).")
    st.stop()
if not businesses:
    st.info("No canonical businesses are available.")
    st.stop()
active = st.session_state.get(ACTIVE_REPORT_PROJECT_KEY)
index = next((i for i, b in enumerate(businesses) if b["google_place_id"] == active), 0)
business = st.selectbox("Business", businesses, index=index, format_func=lambda b: b["business_name"])
pid = str(business["google_place_id"])
try:
    captures = list_captures(pid)
    brief = load_owner_brief(pid)
    runs = list_business_runs(pid)
    approved = load_approved_actions(pid)
    ready = intervention_storage_ready()
    actions = list_interventions(pid)
except Exception as exc:
    st.error(f"Positioning inputs could not be loaded ({type(exc).__name__}).")
    st.stop()
if not captures:
    st.info("Archive saved evidence in Evidence Review before comparing positioning.")
    st.stop()
chosen = st.selectbox("Evidence capture", captures, format_func=lambda c: f"{c['archived_at']} · {c['id']}")
run = st.selectbox("Benchmark", [None, *runs], format_func=lambda r: "No benchmark selected" if r is None else f"{r['started_at']} · {r['id']}")
with st.expander("Suggestion thresholds"):
    st.caption("Counts are distinct saved review records and source classes, not independent witnesses. No universal score is calculated.")
    minimum = st.number_input("Minimum supporting customer records", min_value=1, value=2, step=1)
    breadth = st.number_input("Minimum customer source classes", min_value=1, value=1, step=1)
try:
    capture = load_capture(str(chosen["id"]))
    if str(capture["google_place_id"]) != pid:
        raise ValueError("Capture belongs to another business")
    decisions = list_decisions(str(capture["id"]))
    questions = get_run_queries(str(run["id"])).to_dict("records") if run else []
    confirmed = load_confirmed_question_map(str(run["id"]), pid) if run else {}
    wave = load_measurement_wave(str(run["id"])) if run else None
    view = triangulate(capture, decisions, owner_brief=brief, run=run, questions=questions,
                       confirmed_question_map=confirmed, rules=TriangulationRules(int(minimum), int(breadth)))
except ValueError as exc:
    st.error(str(exc))
    st.stop()
except Exception as exc:
    st.error(f"Evidence could not be verified ({type(exc).__name__}).")
    st.stop()
st.subheader("Positioning evidence")
st.caption("Owner intent uses the selected business's latest saved priority list. Blank cells mean unknown. Not tested applies only to a completely mapped selected panel. These sources may have different dates.")
st.dataframe(pd.DataFrame([{k: r[k] for k in ("proposition", "owner_intended", "tested", "customer_support_records", "customer_source_classes", "suggestion", "reason")} for r in view["rows"]]), hide_index=True, width="stretch")
with st.expander("Owner context, question links and evidence provenance"):
    st.json(view)
for limitation in view["limitations"]:
    st.caption(limitation)
st.download_button("Download positioning evidence", canonical_json(view), file_name="positioning-evidence.json", mime="application/json")
st.subheader("Intervention tracking")
st.caption("An intervention records a hypothesis and an action, separately from a report recommendation. Unknown effort and baseline series stay explicit. A bundle ID groups simultaneous changes; it does not isolate their effects.")
if not ready:
    st.info("Intervention storage awaits the separately approved C migration. You can prepare and download a validated draft; no action can be saved yet.")
options = [None, *actions]
selected = st.selectbox("Action to edit", options, format_func=lambda a: "New action" if a is None else f"{a['record']['finding']} · revision {a['revision']}")
previous = selected["record"] if selected else {}
if selected:
    with st.expander("Action revision history"):
        try:
            st.json(list_intervention_history(str(selected["action_id"])))
        except Exception as exc:
            st.error(f"Action history could not be loaded ({type(exc).__name__}).")
    if str(previous["capture_id"]) != str(capture["id"]):
        st.info("Select this action's original evidence capture to append a revision.")
        st.stop()
    if previous.get("baseline_run_id") and (run is None or str(run["id"]) != str(previous["baseline_run_id"])):
        st.info("Select this action's baseline benchmark before editing so its measurement link is preserved.")
        st.stop()
if not selected:
    st.session_state.setdefault(f"new_action_{pid}_{capture['id']}", new_action_id())
action_id = str(selected["action_id"]) if selected else st.session_state[f"new_action_{pid}_{capture['id']}"]
props = capture["payload"]["catalogue"]
prop_index = next((i for i, p in enumerate(props) if p["proposition_key"] == previous.get("proposition_key")), 0)
proposition = st.selectbox("Action proposition", props, index=prop_index, disabled=bool(selected), format_func=lambda p: p["label"])
observations = capture["payload"]["matrix"]["observations"]
evidence_options = [o["evidence_id"] for o in observations]
evidence_labels = {o["evidence_id"]: f"{o['source_class']} · {o['raw_value'][:110]}" for o in observations}
with st.form(f"intervention_{action_id}_{selected['revision'] if selected else 0}"):
    finding = st.text_area("Observed finding", value=previous.get("finding", ""))
    hypothesis = st.text_area("Action and hypothesis to test", value=previous.get("hypothesis", ""))
    affected = st.multiselect("Affected evidence", evidence_options, default=previous.get("affected_evidence_ids", []), format_func=lambda e: evidence_labels[e])
    owner = st.text_input("Action owner", value=previous.get("owner", ""))
    priority = st.selectbox("Agreed priority", PRIORITIES, index=PRIORITIES.index(previous.get("priority", PRIORITIES[0])))
    effort = st.text_input("Effort or estimate basis", value=previous.get("effort", "Not yet estimated"))
    state = st.selectbox("Action status", STATUSES, index=STATUSES.index(previous.get("status", "PLANNED")))
    planned = st.text_input("Planned date (YYYY-MM-DD, optional)", value=previous.get("planned_date") or "")
    implemented = st.text_input("Actual implementation date (YYYY-MM-DD, optional)", value=previous.get("implemented_date") or "")
    completion = st.text_area("Completion evidence URLs (one per line)", value="\n".join(previous.get("completion_evidence", [])))
    bundle = st.text_input("Simultaneous-action bundle UUID (optional)", value=previous.get("bundle_id") or "")
    families = st.text_area("Focused families to monitor (one explicit label per line)", value="\n".join(previous.get("focused_families", [])))
    baseline = st.checkbox("Use selected benchmark as baseline", value=bool(previous.get("baseline_run_id")), disabled=run is None)
    if run and not wave:
        st.caption("Selected historical benchmark has no frozen series metadata. It can be linked, but a compatible before/after series is unknown.")
    linked_options = [None, *approved]
    link_index = next((i for i, a in enumerate(linked_options) if a and a["action_id"] == previous.get("approved_action_id") and a["revision_id"] == previous.get("approved_revision_id")), 0)
    linked = st.selectbox("Existing approved report action (optional link)", linked_options, index=link_index,
                          format_func=lambda a: "No approved action link" if a is None else a["action"] or a["action_id"])
    operator = st.text_input("Recording operator", value="")
    revision_note = st.text_area("Reason for this action record or revision")
    draft = st.form_submit_button("Prepare validated draft")
    save = st.form_submit_button("Save action revision", disabled=not ready)
if draft or save:
    try:
        record = validate_intervention({"version": VERSION, "action_id": action_id, "google_place_id": pid,
            "proposition_key": proposition["proposition_key"], "capture_id": str(capture["id"]),
            "finding": finding, "hypothesis": hypothesis, "affected_evidence_ids": affected,
            "owner": owner, "priority": priority, "effort": effort, "status": state,
            "planned_date": planned or None, "implemented_date": implemented or None,
            "completion_evidence": [s.strip() for s in completion.splitlines() if s.strip()],
            "bundle_id": bundle or None, "focused_families": [s.strip() for s in families.splitlines() if s.strip()],
            "baseline_run_id": str(run["id"]) if baseline and run else None,
            "baseline_series_id": str(wave["series_id"]) if baseline and wave else None,
            "approved_revision_id": linked["revision_id"] if linked else None,
            "approved_action_id": linked["action_id"] if linked else None, "created_by": operator,
            "finding_snapshot": view, "revision_note": revision_note}, capture)
        if save:
            saved_id = save_intervention(record, expected_revision=int(selected["revision"]) if selected else 0)
            st.success(f"Saved action revision {saved_id}.")
            st.session_state.pop(f"new_action_{pid}_{capture['id']}", None)
        else:
            st.download_button("Download intervention draft", canonical_json(record), file_name="intervention-draft.json", mime="application/json")
    except (ValueError, TypeError) as exc:
        st.error(str(exc))
    except Exception as exc:
        st.error(f"Action could not be saved ({type(exc).__name__}).")
