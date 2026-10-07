"""Explicit operator archival and evidence decisions; never starts source collection."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.evidence_foundations_repository import list_foundation_businesses, load_catalogue
from src.public_evidence_archive import DECISIONS, ORIGINS, summarize_reviewed_evidence
from src.public_evidence_archive_repository import (
    ARCHIVE_TABLES, archive_status, list_captures, load_capture, list_decisions, save_capture, save_decision,
    list_collection_attempts, save_collection_attempt,
)
from src.public_evidence_repository import load_public_evidence_bundle
from src.report_generator_readiness import ACTIVE_REPORT_PROJECT_KEY

st.set_page_config(page_title="Evidence Review", page_icon="📚", layout="wide")
st.title("Evidence review")
st.caption("Save durable copies of existing evidence and review exact proposition excerpts. These are evidence observations, not AI ranking factors.")

try:
    status = archive_status()
except Exception as exc:
    st.error(f"Evidence storage could not be checked ({type(exc).__name__}).")
    st.stop()
if not all(status.get(t) for t in ARCHIVE_TABLES):
    st.info("The separate Increment B archive migration is not applied. This page cannot save captures or decisions yet. The read-only matrix remains available in Evidence Foundations.")
    st.stop()
try:
    businesses = list_foundation_businesses()
    catalogue, aliases, _ = load_catalogue()
except Exception as exc:
    st.error(f"Businesses could not be loaded ({type(exc).__name__}).")
    st.stop()
if not businesses:
    st.info("No canonical businesses are available.")
    st.stop()
active = st.session_state.get(ACTIVE_REPORT_PROJECT_KEY) or st.session_state.get("client_evidence_business")
index = next((i for i, b in enumerate(businesses) if b["google_place_id"] == active), 0)
business = st.selectbox("Business", businesses, index=index, format_func=lambda b: f"{b['business_name']} · {b['google_place_id']}")
pid = str(business["google_place_id"])
st.caption("Archiving copies saved records; it does not refresh a website/profile or create a new collection attempt. Original source dates are retained. Issued reports are unchanged.")
with st.form("archive_saved_evidence"):
    operator = st.text_input("Archiving operator")
    submitted = st.form_submit_button("Archive current saved evidence")
if submitted:
    try:
        bundle = load_public_evidence_bundle(business)
        saved_id = save_capture(bundle, catalogue, aliases, archived_by=operator)
        st.success(f"Saved evidence capture {saved_id}. Identical evidence reuses its existing capture.")
    except ValueError as exc:
        st.error(str(exc))
    except Exception as exc:
        st.error(f"Evidence could not be archived ({type(exc).__name__}).")
with st.expander("Record or inspect a completed collection attempt"):
    st.caption("Record an actual check and what happened. This does not collect anything, update a profile link, or establish that the business has no platform presence. Counts are usable text found in the check, not published review totals.")
    with st.form(f"collection_attempt_{pid}"):
        source_class = st.text_input("Collection source class", value="google_reviews")
        source_url = st.text_input("Checked source URL")
        outcome = st.selectbox("Collection outcome", ("FAILED", "UNAVAILABLE", "CHECKED_EMPTY", "COLLECTED"))
        observed = st.text_input("Actual check timestamp (ISO format with timezone)", value=datetime.now(timezone.utc).isoformat())
        count = st.number_input("Usable text sample size", min_value=0, step=1)
        st.caption("Sample size is used for COLLECTED/CHECKED_EMPTY only. FAILED/UNAVAILABLE retain an unknown size.")
        scope = st.text_input("What was checked")
        explanation = st.text_area("Collection outcome explanation")
        attempt_saved = st.form_submit_button("Save collection outcome")
    if attempt_saved:
        try:
            save_collection_attempt(google_place_id=pid, source_class=source_class, source_url=source_url,
                status=outcome, observed_at=observed, sample_size=int(count) if outcome in {"COLLECTED", "CHECKED_EMPTY"} else None,
                scope=scope, note=explanation, adapter_version="operator-collection-check-v1")
            st.success("Completed collection outcome recorded. No evidence was fetched.")
        except ValueError as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(f"Collection outcome could not be saved ({type(exc).__name__}).")
    try:
        attempts = list_collection_attempts(pid)
        st.dataframe(pd.DataFrame(attempts), hide_index=True, width="stretch")
    except Exception as exc:
        st.error(f"Collection history could not be loaded ({type(exc).__name__}).")
try:
    captures = list_captures(pid)
except Exception as exc:
    st.error(f"Captures could not be loaded ({type(exc).__name__}).")
    st.stop()
if not captures:
    st.info("No durable evidence capture has been saved for this business.")
    st.stop()
selected = st.selectbox("Saved capture", captures, format_func=lambda c: f"{c['archived_at']} · {c['id']}")
try:
    capture = load_capture(str(selected["id"]))
    if str(capture["google_place_id"]) != pid:
        raise ValueError("Capture belongs to another business")
    decisions = list_decisions(str(capture["id"]))
    summary = summarize_reviewed_evidence(capture, decisions)
except ValueError as exc:
    st.error(str(exc))
    st.stop()
except Exception as exc:
    st.error(f"The saved capture could not be verified ({type(exc).__name__}).")
    st.stop()
st.subheader("Reviewed proposition evidence")
st.caption("Breadth counts reviewed supporting source classes, not independent confirmations or a visibility score. Syndicated claims do not increase breadth. Unknowns and incomplete review remain visible.")
st.dataframe(pd.DataFrame(summary), hide_index=True, width="stretch")
observations = [o for o in capture["payload"]["matrix"]["observations"] if o["kind"] == "proposition_candidate"]
latest = {d["evidence_id"]: d for d in decisions}
undecided = [o for o in observations if o["evidence_id"] not in latest]
if observations:
    st.subheader("Review excerpts")
    st.progress((len(observations) - len(undecided)) / len(observations),
                text=f"{len(observations) - len(undecided)} of {len(observations)} excerpts have a decision.")
    only_undecided = st.checkbox("Show only excerpts without a decision", value=True, key=f"undecided_{capture['id']}")
    # Customer sources first: they are what positioning counts; website copy is the owner's own claim.
    queue = sorted(undecided if only_undecided else observations, key=lambda o: o["source_class"] == "website")
    if not queue:
        st.success("Every excerpt in this capture has a decision. Untick the box above to revise one.")
        observations = []
if observations:
    chosen = st.selectbox("Excerpt to review", queue,
        format_func=lambda o: f"{o['field']} · {o['source_class']} · {o['raw_value'][:100]}", key=f"excerpt_{capture['id']}")
    st.write(chosen["raw_value"])
    if chosen["evidence_id"] in latest:
        previous = latest[chosen["evidence_id"]]
        st.caption(f"Current decision: {previous['decision']} ({previous['origin']}), by {previous['reviewer']}. Saving adds a new revision.")
    st.write({k: chosen.get(k) for k in ("source_class", "source_url", "source_url_basis", "source_record_id", "captured_at", "source_published_at", "polarity_hint")})
    st.caption("Polarity is an extraction hint. Use the preserved source context and your judgment; overall review stars do not establish proposition sentiment.")
    with st.form(f"review_{capture['id']}_{chosen['evidence_id']}"):
        decision = st.selectbox("Decision", DECISIONS)
        origin = st.selectbox("Evidence origin", ORIGINS)
        confirmed = st.checkbox("I confirmed this evidence refers to this business")
        reviewer = st.text_input("Reviewer", value=st.session_state.get("evidence_reviewer", ""))
        note = st.text_area("Explanation, including source context and origin")
        reviewed = st.form_submit_button("Save evidence decision")
    if reviewed:
        try:
            save_decision(str(capture["id"]), evidence_id=chosen["evidence_id"], decision=decision, origin=origin,
                identity_confirmed=confirmed, reviewer=reviewer, note=note)
            st.session_state["evidence_reviewer"] = reviewer
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(f"Decision could not be saved ({type(exc).__name__}).")
with st.expander("Preserved primary context and capture provenance"):
    st.write({k: str(capture[k]) for k in ("id", "archived_at", "archived_by", "payload_sha256")})
    st.json(capture["payload"]["source_bundle"])
with st.expander("Decision history"):
    st.dataframe(pd.DataFrame(decisions), hide_index=True, width="stretch")
