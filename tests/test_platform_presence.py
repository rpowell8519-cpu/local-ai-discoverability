"""Platform presence gap: a review-platform finding distinct from review theme comparison.

Narrow claim only - the client has zero reviews on a platform where at least one leader has
some. Not about review content, and not about "fewer reviews of the same kind" (that's what
_review_findings already covers). Runs through the public analyse_evidence entry point, matching
the rest of this test suite's convention of not reaching into evidence_analysis' private helpers.
"""
import pandas as pd

from src.evidence_analysis import analyse_evidence, select_leaders
from src.review_ingestion import SOURCE, SOURCE_TRIPADVISOR, SOURCE_YELP
from tests import evidence_fixture as F


def _review_row(pid, i, source, rating=5):
    return dict(
        google_place_id=pid, business_name=F.NAMES[pid], review_id=f"{pid}-{source}-{i}",
        review_text="Great service", review_rating=rating, review_timestamp=1,
        review_datetime_utc=pd.Timestamp("2026-08-01"), review_likes=0, author_title="a",
        author_reviews_count=1, owner_answer=None, review_link="", source=source,
    )


def _multi_platform_reviews(*, target_has_yelp=False, leaders_with_yelp=("l1", "l2")):
    rows = []
    # Everyone (target + all leaders) has ordinary Google reviews, matching the base fixture.
    for pid in [F.T, *F.LEADERS]:
        for i in range(3):
            rows.append(_review_row(pid, i, SOURCE))

    if target_has_yelp:
        rows.append(_review_row(F.T, 0, SOURCE_YELP))

    for pid in leaders_with_yelp:
        for i in range(4):
            rows.append(_review_row(pid, i, SOURCE_YELP))

    return pd.DataFrame(rows)


def run(reviews):
    return analyse_evidence(
        target_id=F.T, target_name=F.NAMES[F.T], primary_group="coworking",
        leaders=select_leaders(F.leaders(), F.T), audits=F.audits(), pages_by_run=F.pages_by_run(),
        propositions=F.PROPOSITIONS, reviews=reviews,
    )


def by_id(result):
    return {c["id"]: c for c in result["candidates"]}


def test_a_platform_the_client_has_no_presence_on_but_leaders_do_is_flagged():
    result = run(_multi_platform_reviews())
    candidates = by_id(result)
    finding = candidates[f"reviews:platform-{SOURCE_YELP}"]
    assert finding["kind"] == "action"
    assert finding["prevalence"] == "2 of 3"
    assert "no reviews on Yelp" in finding["observation"]
    assert "Plus X Innovation Brighton" in finding["observation"] and "Runway East Brighton" in finding["observation"]


def test_a_platform_the_client_already_has_some_presence_on_is_not_flagged():
    result = run(_multi_platform_reviews(target_has_yelp=True))
    assert f"reviews:platform-{SOURCE_YELP}" not in by_id(result)


def test_a_platform_no_leader_has_either_is_not_flagged():
    # Nobody has TripAdvisor reviews at all in this fixture - not evidence of a gap.
    result = run(_multi_platform_reviews())
    assert f"reviews:platform-{SOURCE_TRIPADVISOR}" not in by_id(result)


def test_google_itself_is_never_flagged_when_everyone_already_has_some():
    # Every business in the base fixture already has Google reviews, so there's no Google gap.
    result = run(_multi_platform_reviews())
    assert f"reviews:platform-{SOURCE}" not in by_id(result)


def test_more_leaders_present_gives_a_higher_score_than_fewer():
    two_leaders = by_id(run(_multi_platform_reviews(leaders_with_yelp=("l1", "l2"))))
    one_leader = by_id(run(_multi_platform_reviews(leaders_with_yelp=("l1",))))
    key = f"reviews:platform-{SOURCE_YELP}"
    assert two_leaders[key]["score"] > one_leader[key]["score"]
    assert two_leaders[key]["confidence"] == "Medium"
    assert one_leader[key]["confidence"] == "Low"


def test_reviews_without_a_source_column_are_handled_gracefully_no_platform_findings():
    # The original fixture predates multi-platform ingestion and has no `source` column at all.
    result = run(F.reviews())
    assert not [c for c in result["candidates"] if str(c["id"]).startswith("reviews:platform-")]
    assert result["layers"]["reviews"]["status"] == "used"  # the rest of the reviews layer is unaffected
