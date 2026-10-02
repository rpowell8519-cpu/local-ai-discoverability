from copy import deepcopy
import math

import pytest

from src.proposition_catalog import starter_catalogue
from src.public_evidence_archive import build_capture
from src.research_evidence import association, build_dataset, evidence_features, spearman
from test_focused_monitoring import summary
from test_positioning_triangulation import reviews as decisions_for


WHEN = "2026-09-01T15:00:00+00:00"


def evidence():
    catalogue, aliases = starter_catalogue()
    bundle = {"business": {"google_place_id": "target", "business_name": "Synthetic Salon"},
        "listing": None, "audit": None, "pages": [], "checks": {}, "platform_links": [],
        "reviews": [{"id": f"review-{i}", "google_place_id": "target", "source": "outscraper_google_reviews",
            "review_id": str(i), "review_text": "I love my balayage. My balayage looks lovely.",
            "imported_at": "2026-08-20T12:00:00+00:00", "review_datetime_utc": "2026-08-01T12:00:00+00:00"} for i in range(2)]}
    cap = {"id": "capture", "archived_at": "2026-08-21T12:00:00+00:00", **build_capture(bundle, catalogue, aliases)}
    decisions = [{**d, "created_at": "2026-08-22T12:00:00+00:00"} for d in decisions_for(cap)]
    profile = {"google_place_id": "target", "platform": "google", "source_record_id": "listing",
        "observed_at": "2026-08-20T12:00:00+00:00", "rating": 4.6, "published_review_count": 214}
    return cap, decisions, profile


def features(cap=None, decisions=None, profiles=None, **kwargs):
    c,d,p=evidence()
    return evidence_features("target", "balayage", WHEN, profiles if profiles is not None else [p],
        [cap or c], decisions if decisions is not None else d, **kwargs)


def test_published_sample_and_reviewed_record_populations_stay_separate():
    row=features()
    assert row["published_review_count"] == 214 and row["sampled_review_count"] == 2
    assert row["reviewed_customer_records"] == row["supporting_customer_records"] == 2
    assert row["customer_support_rate"] == 1 and row["customer_source_breadth"] == 1
    assert len(row["evidence_ids"]) == 4  # two sentences each, not four customers
    assert row["recent_review_velocity"] is None
    assert all(row["feature_eligible"].values())


def test_late_archive_cannot_backdate_source_text():
    cap,_,_=evidence()
    cap["archived_at"]="2026-09-02T12:00:00+00:00"
    row=features(cap=cap)
    assert row["capture_status"] == "missing_or_post_wave" and row["sampled_review_count"] is None
    assert row["customer_support_rate"] is None


def test_late_or_undated_judgments_cannot_backdate_human_support():
    for date in ("2026-09-02T12:00:00+00:00",None):
        _,decisions,_=evidence()
        for d in decisions: d["created_at"]=date
        row=features(decisions=decisions)
        assert row["customer_support_rate"] is None and not row["feature_eligible"]["customer_source_breadth"]


def test_asof_latest_decision_ignores_later_withdrawal_but_honours_prior_withdrawal():
    _,decisions,_=evidence()
    changes=[{**d,"revision":2,"decision":"UNCERTAIN","created_at":"2026-09-02T12:00:00+00:00"} for d in decisions]
    assert features(decisions=decisions+changes)["customer_support_rate"] == 1
    for d in changes: d["created_at"]="2026-08-25T12:00:00+00:00"
    assert features(decisions=decisions+changes)["customer_support_rate"] is None


def test_future_profile_does_not_replace_prior_profile_and_unknown_is_not_zero():
    _,_,p=evidence()
    future={**p,"source_record_id":"future","observed_at":"2026-10-01T00:00:00+00:00","published_review_count":999}
    assert features(profiles=[p,future])["published_review_count"] == 214
    assert features(profiles=[future])["published_review_count"] is None
    assert features(profiles=[{**p,"published_review_count":0}])["published_review_count"] == 0


def test_stale_values_remain_inspectable_but_not_eligible_for_associations():
    row=features(max_age_days=1)
    assert row["published_review_count"] == 214 and row["profile_status"] == "stale"
    assert not any(row["feature_eligible"].values())


def test_partial_review_and_contradictions_exclude_support_associations():
    _,decisions,_=evidence()
    assert not features(decisions=decisions[:1])["feature_eligible"]["customer_support_rate"]
    decisions[0]["decision"]="CONTRADICTS"
    row=features(decisions=decisions)
    assert row["contradicting_customer_records"]==1 and not row["feature_eligible"]["customer_support_rate"]


def test_dataset_retains_eligible_zero_business_and_reports_historical_exclusions():
    cap,d,p=evidence()
    data=build_dataset([summary()],profiles=[p],captures=[cap],decisions=d)
    assert len(data["rows"]) == 5
    zero=next(r for r in data["rows"] if r["google_place_id"]=="zero")
    assert zero["appearance_rate"]==0 and zero["measurement_eligible"]
    assert zero["published_review_count"] is None
    old=summary();old.update(wave=None,rows=[],issues=["Historical panel metadata is unavailable"])
    assert build_dataset([old])["excluded_runs"][0]["reasons"] == old["issues"]


def test_unknown_identity_or_served_model_is_excluded_and_duplicate_waves_rejected():
    s=summary()
    s["served_versions"]={}
    s["rows"][0]["identity_status"]="needs_review"
    assert not any(r["measurement_eligible"] for r in build_dataset([s])["rows"])
    with pytest.raises(ValueError,match="once"): build_dataset([s,s])


def test_spearman_ties_known_direction_and_log_equivalence():
    assert spearman([1,2,3,4],[4,3,2,1]) == pytest.approx(-1)
    assert spearman([1,1,3,4],[2,2,3,4]) == pytest.approx(1)
    x=[0,5,5,30,100]; y=[0.2,0.6,0.4,0.8,1]
    assert spearman(x,y)==pytest.approx(spearman([math.log1p(v) for v in x],y))
    assert spearman([1,1,1],[1,2,3]) is None


def research_rows(n=12):
    return [{"stratum_id":"same","measurement_eligible":True,"feature_eligible":{"published_review_count":True},
        "google_place_id":f"place-{i}","business_name":f"Synthetic {i}","run_id":"wave", "market":"Brighton",
        "published_review_count":i,"appearance_rate":i/(n-1)} for i in range(n)]


def test_cluster_bootstrap_reproducible_and_repeats_do_not_inflate_unique_businesses():
    rows=research_rows()
    rows += [{**r,"run_id":"second-wave"} for r in rows]
    result=association(rows,"published_review_count",bootstrap_samples=100)
    assert result["n_rows"]==24 and result["unique_businesses"]==12
    assert result["spearman_rho"]==pytest.approx(1)
    assert result["cluster_interval_95"]==pytest.approx([1,1])
    assert result==association(rows,"published_review_count",bootstrap_samples=100)


def test_small_constant_missing_and_unequal_coverage_are_explicit():
    rows=research_rows(4)
    rows.append({**rows[0],"run_id":"second"})
    rows[1]["feature_eligible"]["published_review_count"]=False
    result=association(rows,"published_review_count",bootstrap_samples=100)
    assert result["cluster_interval_95"] is None and result["excluded_rows"]==1
    assert any("Small sample" in w for w in result["warnings"])
    assert any("Unequal" in w for w in result["warnings"])
    for row in rows: row["appearance_rate"]=0
    assert association(rows,"published_review_count")["spearman_rho"] is None


def test_mixed_panel_model_or_market_cannot_be_pooled():
    rows=research_rows()
    rows[0]["stratum_id"]="different"
    with pytest.raises(ValueError,match="one compatible"): association(rows,"published_review_count")
