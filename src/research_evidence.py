"""Read-only research projections with dated evidence and explicit sampling limitations."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import hashlib
import json
import math
import random

import pandas as pd

from src.proposition_catalog import resolve_labels
from src.public_evidence_archive import AFFIRMATIVE, verify_capture, validate_decision
from src.review_profile_metrics import review_sample_metrics

VERSION = "research-evidence-v1"
FEATURES = ("published_review_count", "profile_rating", "sampled_review_count",
            "latest_sample_age_days", "customer_support_rate", "customer_source_breadth")
STRATUM_FIELDS = ("panel_id", "panel_kind", "family", "provider", "served_model",
                  "benchmark_mode", "market", "primary_group")


def dated(value):
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else None
    except (ValueError, TypeError):
        return None


def choose_asof(records, field, cutoff):
    eligible = [r for r in records if dated(r.get(field)) and cutoff and dated(r[field]) <= cutoff]
    return max(eligible, key=lambda r: (dated(r[field]), str(r.get("id") or r.get("source_record_id") or ""))) if eligible else None


def evidence_features(pid, family, when, profiles, captures, decisions, *, max_age_days=90):
    """Strict exposure features use evidence and judgments already stored by wave start.

    A later archive of older-looking mutable source text cannot establish historical
    exposure. Later review decisions never backdate a human judgment.
    """
    cutoff = dated(when)
    profiles = [p for p in profiles if str(p.get("google_place_id")) == pid and p.get("platform") == "google"]
    captures = [c for c in captures if str(c.get("google_place_id")) == pid]
    profile = choose_asof(profiles, "observed_at", cutoff)
    capture = choose_asof(captures, "archived_at", cutoff)
    result = {key: None for key in FEATURES}
    result.update(profile_status="missing_or_post_wave", capture_status="missing_or_post_wave",
        profile_source_id=None, profile_observed_at=None, profile_age_days=None,
        profile_evidence_sha256=None, profile_adapter_version=None, profile_source_url=None,
        capture_id=None, capture_sha256=None, sample_platforms=[], sample_dated_count=None,
        latest_known_in_sample=None, recent_review_velocity=None, proposition_key=None,
        reviewed_customer_records=None, supporting_customer_records=None, contradicting_customer_records=None,
        candidate_review_coverage=None, evidence_ids=[], decision_ids=[], feature_eligible={key: False for key in FEATURES})
    if profile:
        age = (cutoff-dated(profile["observed_at"])).total_seconds()/86400
        result.update(profile_source_id=str(profile["source_record_id"]), profile_observed_at=str(profile["observed_at"]),
            profile_evidence_sha256=profile.get("evidence_sha256"), profile_adapter_version=profile.get("adapter_version"),
            profile_source_url=profile.get("source_url"),
            profile_age_days=age, profile_status="as_of" if age <= max_age_days else "stale",
            published_review_count=profile.get("published_review_count"), profile_rating=profile.get("rating"))
        for key in ("published_review_count", "profile_rating"):
            result["feature_eligible"][key] = age <= max_age_days and result[key] is not None
    if not capture:
        return result
    payload = verify_capture(capture)
    result.update(capture_id=str(capture["id"]), capture_sha256=capture["payload_sha256"], capture_status="as_of")
    reviews = payload["source_bundle"].get("reviews") or []
    # An archived sample is not a platform total; its latest known date is not platform recency.
    reviews = [r for r in reviews if
        (not dated(r.get("review_datetime_utc")) or dated(r["review_datetime_utc"]) <= cutoff)
        and (not dated(r.get("imported_at")) or dated(r["imported_at"]) <= cutoff)]
    metrics = review_sample_metrics(pd.DataFrame(reviews))
    if metrics:
        result["sampled_review_count"] = sum(m["sampled_review_count"] for m in metrics)
        result["sample_dated_count"] = sum(m["dated_sample_size"] for m in metrics)
        result["sample_platforms"] = [m["platform"] for m in metrics]
        ends = [dated(m["latest_known_in_sample"]) for m in metrics if dated(m["latest_known_in_sample"])]
        latest = max(ends) if ends else None
        result["latest_known_in_sample"] = latest.isoformat() if latest else None
        result["latest_sample_age_days"] = (cutoff-latest).total_seconds()/86400 if latest else None
        # Source retrieval dates, not archive dates, determine freshness.
        retrieved = [dated(r.get("imported_at")) for r in reviews if str(r.get("review_text") or "").strip()]
        fresh = bool(retrieved) and all(d and 0 <= (cutoff-d).total_seconds()/86400 <= max_age_days for d in retrieved)
        result["capture_status"] = "as_of" if fresh else "source_dates_unknown_or_stale"
        result["feature_eligible"]["sampled_review_count"] = fresh
        result["feature_eligible"]["latest_sample_age_days"] = fresh and latest is not None
    catalogue = payload["catalogue"]
    key = family if family in {p["proposition_key"] for p in catalogue} else resolve_labels([family], catalogue, payload["aliases"])[0]["proposition_key"]
    result["proposition_key"] = key
    if not key:
        return result
    latest_decisions = {}
    for decision in decisions:
        if str(decision.get("capture_id")) != str(capture["id"]):
            continue
        if not dated(decision.get("created_at")) or dated(decision["created_at"]) > cutoff:
            continue
        validate_decision(capture, **{k: decision[k] for k in ("evidence_id", "decision", "origin", "reviewer", "note", "identity_confirmed")})
        old = latest_decisions.get(decision["evidence_id"])
        if old is None or decision["revision"] > old["revision"]:
            latest_decisions[decision["evidence_id"]] = decision
    observations = [o for o in payload["matrix"]["observations"] if o.get("kind") == "proposition_candidate" and o.get("proposition_key") == key]
    customer_records = defaultdict(set)
    support_classes, evidence_ids, decision_ids = set(), [], []
    fresh_sources = []
    definitive = 0
    for obs in observations:
        decision = latest_decisions.get(obs["evidence_id"])
        if not decision or not decision["identity_confirmed"] or decision["decision"] == "UNCERTAIN":
            continue
        definitive += 1
        if decision["origin"] != "customer_report":
            continue
        customer_records[(obs["source_class"], obs["source_record_id"])].add(decision["decision"])
        evidence_ids.append(obs["evidence_id"])
        decision_ids.append(str(decision["id"]))
        fresh_sources.append(dated(obs.get("captured_at")))
        if decision["decision"] in AFFIRMATIVE:
            support_classes.add(obs["source_class"])
    result["candidate_review_coverage"] = definitive/len(observations) if observations else None
    if customer_records:
        n = len(customer_records)
        supported = sum(bool(values & AFFIRMATIVE) for values in customer_records.values())
        conflicts = sum("CONTRADICTS" in values for values in customer_records.values())
        fresh = all(d and 0 <= (cutoff-d).total_seconds()/86400 <= max_age_days for d in fresh_sources)
        result.update(reviewed_customer_records=n, supporting_customer_records=supported,
            contradicting_customer_records=conflicts, customer_support_rate=supported/n,
            customer_source_breadth=len(support_classes), evidence_ids=evidence_ids, decision_ids=decision_ids)
        for field in ("customer_support_rate", "customer_source_breadth"):
            result["feature_eligible"][field] = fresh and definitive == len(observations) and conflicts == 0
    return result


def build_dataset(summaries, *, profiles=(), captures=(), decisions=(), max_age_days=90):
    if max_age_days < 1:
        raise ValueError("Evidence age limit must be positive")
    rows, excluded_runs, seen = [], [], set()
    for summary in summaries:
        run_id = summary["run_id"]
        if run_id in seen:
            raise ValueError("Select each measurement wave once")
        seen.add(run_id)
        wave = summary.get("wave") or {}
        config = wave.get("configuration") or {}
        if not summary["rows"]:
            excluded_runs.append({"run_id": run_id, "reasons": summary["issues"] or ["No frozen family/cohort rows"]})
        for measured in summary["rows"]:
            reasons = list(summary["issues"])
            provider = measured["provider"]
            served = summary["served_versions"].get(provider)
            if not served:
                reasons.append("Served version unavailable or mixed")
            if measured["identity_status"] != "linked":
                reasons.append("Business identity needs review")
            if not measured["expected_answers"] or measured["completed_answers"] != measured["expected_answers"]:
                reasons.append("Incomplete answer denominator")
            if not dated(summary["started_at"]):
                reasons.append("Wave date unavailable")
            pid = measured["google_place_id"]
            feature = evidence_features(pid, measured["family"], summary["started_at"], profiles, captures, decisions, max_age_days=max_age_days)
            row = {**measured, **feature, "version": VERSION, "run_id": run_id, "wave_at": summary["started_at"],
                "series_id": str(wave.get("series_id") or ""), "panel_id": wave.get("panel_id"),
                "panel_kind": wave.get("panel_kind"), "served_model": served,
                "reported_models": summary["reported_models"].get(provider, []),
                "requested_model": config.get("requested_models", {}).get(provider),
                "benchmark_mode": config.get("benchmark_mode"), "market": config.get("location_context"),
                "primary_group": config.get("primary_group"),
                "cohort_selection_basis": config.get("settings", {}).get("cohort_basis"),
                "measurement_eligible": not reasons, "exclusion_reasons": sorted(set(reasons))}
            row["stratum_id"] = hashlib.sha256(json.dumps([row[f] for f in STRATUM_FIELDS], ensure_ascii=False).encode()).hexdigest()
            rows.append(row)
    return {"version": VERSION, "rows": rows, "excluded_runs": excluded_runs,
        "max_evidence_age_days": max_age_days,
        "limitations": ["Exploratory associations are not AI ranking factors or causal effects.",
            "Only frozen, independently selected focused cohorts qualify; legacy/core runs without that design remain excluded.",
            "Zero appearances are retained for eligible canonical businesses; unconfirmed identities are excluded.",
            "Published Google counts/ratings differ from collected text samples and reviewed proposition candidates.",
            "Recent platform review velocity is unknown unless actual platform coverage supports it; sample recency is not platform recency.",
            "Human judgments must predate a wave. Late archives and judgments never become historical exposure.",
            "Legacy listing profiles retain source dates and hashes but their raw store is mutable; this is not an immutable historical profile archive.",
            "Directory/alias resolution uses the current saved mapping; measurement exports retain the linking basis."]}


def spearman(xs, ys):
    """Pearson correlation of average ranks; ties retained, no scipy dependency."""
    x, y = pd.Series(xs, dtype=float).rank(), pd.Series(ys, dtype=float).rank()
    if len(x) < 3 or x.nunique() < 2 or y.nunique() < 2:
        return None
    return float(x.corr(y))


def association(rows, feature, *, bootstrap_samples=500, seed=20261002, min_clusters=10):
    if feature not in FEATURES:
        raise ValueError("Choose a supported evidence feature")
    if not 100 <= bootstrap_samples <= 5000 or min_clusters < 3:
        raise ValueError("Use 100–5000 bootstrap samples and at least three business clusters")
    if len({r["stratum_id"] for r in rows}) > 1:
        raise ValueError("Select one compatible panel/family/provider/model/market stratum")
    def finite(value):
        return value is not None and not isinstance(value, bool) and math.isfinite(float(value))
    selected = [r for r in rows if r["measurement_eligible"] and r["feature_eligible"].get(feature)
                and finite(r.get(feature)) and finite(r.get("appearance_rate"))]
    clusters = defaultdict(list)
    for r in selected:
        clusters[r["google_place_id"]].append(r)
    xs = [r[feature] for r in selected]
    ys = [r["appearance_rate"] for r in selected]
    rho = spearman(xs, ys)
    warnings = ["Multiple exploratory comparisons can produce chance associations; no causal or significance claim is made."]
    if len(selected) != len(rows):
        warnings.append("Missing, stale, post-wave or incomplete evidence/measurements excluded; no zero imputation")
    if len(clusters) < min_clusters:
        warnings.append(f"Small sample: {len(clusters)} unique businesses; interval requires {min_clusters}")
    if len({len(values) for values in clusters.values()}) > 1:
        warnings.append("Unequal wave coverage across businesses")
    if rho is None:
        warnings.append("Too few pairs or constant feature/outcome; Spearman is unavailable")
    interval = None
    if rho is not None and len(clusters) >= min_clusters:
        rng = random.Random(seed)
        keys = sorted(clusters)
        samples = []
        for _ in range(bootstrap_samples):
            drawn = [r for pid in rng.choices(keys, k=len(keys)) for r in clusters[pid]]
            value = spearman([r[feature] for r in drawn], [r["appearance_rate"] for r in drawn])
            if value is not None:
                samples.append(value)
        if len(samples) >= 0.9*bootstrap_samples:
            interval = [float(pd.Series(samples).quantile(q)) for q in (0.025, 0.975)]
        else:
            warnings.append("Too many degenerate cluster resamples; interval withheld")
    return {"feature": feature, "n_rows": len(selected), "unique_businesses": len(clusters),
        "waves": len({r["run_id"] for r in selected}), "markets": len({r["market"] for r in selected}),
        "excluded_rows": len(rows)-len(selected), "spearman_rho": rho, "cluster_interval_95": interval,
        "bootstrap_unit": "canonical business with all selected waves", "bootstrap_samples": bootstrap_samples,
        "seed": seed, "min_clusters": min_clusters, "warnings": warnings,
        "distribution": pd.Series(xs, dtype=float).describe().where(lambda s: s.notna(), None).to_dict() if xs else {},
        "points": [{"google_place_id": r["google_place_id"], "business_name": r["business_name"],
            "run_id": r["run_id"], "value": r[feature], "appearance_rate": r["appearance_rate"]} for r in selected]}
