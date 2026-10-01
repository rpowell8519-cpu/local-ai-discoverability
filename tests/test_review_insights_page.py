"""Smoke tests for the Review Insights page's platform selector.

This page had no automated coverage before the Sprint 1 multi-platform
change (adding a Google/Yelp/TripAdvisor checkbox selector that gates
which "get reviews" section renders). These tests exist specifically to
verify that gating behaves correctly, since the Google section - unchanged
in content, only now conditional - is a page rob uses for real client work
and this is its first test coverage of any kind.

No network, no paid calls, no real database: get_engine is stubbed
wherever it's bound (the page itself, review_repository, and
business_platform_links each hold their own imported reference).
"""

from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path
from unittest import mock

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402


PAGE = str(Path(__file__).resolve().parents[1] / "app" / "pages" / "7_Review_Insights.py")


class _Result:
    def __init__(self, rows=()):
        self._rows = list(rows)

    def mappings(self):
        return self

    def all(self):
        return list(self._rows)


class _Connection:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, statement, params=None):
        sql = " ".join(str(statement).lower().split())

        if "from business_features" in sql:
            return _Result([])
        if "from business_reviews" in sql:
            return _Result([])
        if "from business_platform_links" in sql:
            return _Result([])
        if "from competitor_relationship_reviews" in sql:
            return _Result([])

        raise AssertionError(f"Unexpected query in the page under test: {sql[:120]}")


class _Engine:
    def connect(self):
        return _Connection()


def run_page(*, secrets=None):
    import streamlit as st

    st.cache_data.clear()
    stack = ExitStack()
    patches = [
        mock.patch("src.database.get_engine", return_value=_Engine()),
        mock.patch("src.review_repository.get_engine", return_value=_Engine()),
        mock.patch("src.business_platform_links.get_engine", return_value=_Engine()),
    ]
    for patch in patches:
        stack.enter_context(patch)

    at = AppTest.from_file(PAGE, default_timeout=60)
    at.secrets["TEST_ONLY_PLACEHOLDER"] = "unused"
    for key, value in (secrets or {}).items():
        at.secrets[key] = value
    at.run()
    return at, stack


def checkbox(at, key):
    return next(c for c in at.checkbox if c.key == key)


def test_the_page_loads_with_google_checked_and_others_unchecked_by_default():
    at, stack = run_page()
    with stack:
        assert not at.exception, [e.value for e in at.exception]
        assert checkbox(at, "pull_platform_google").value is True
        assert checkbox(at, "pull_platform_yelp").value is False
        assert checkbox(at, "pull_platform_tripadvisor").value is False
        assert any("Get Google reviews" in h.value for h in at.subheader)
        assert not any("Get Yelp reviews" in h.value for h in at.subheader)
        assert not any("Get TripAdvisor reviews" in h.value for h in at.subheader)


def test_unchecking_google_hides_its_section_and_shows_the_select_a_platform_hint():
    at, stack = run_page()
    with stack:
        checkbox(at, "pull_platform_google").set_value(False).run()
        assert not at.exception, [e.value for e in at.exception]
        assert not any("Get Google reviews" in h.value for h in at.subheader)
        assert any(
            "Select at least one platform" in i.value for i in at.info
        )


def test_checking_yelp_shows_its_section_without_disturbing_google():
    at, stack = run_page()
    with stack:
        checkbox(at, "pull_platform_yelp").set_value(True).run()
        assert not at.exception, [e.value for e in at.exception]
        assert any("Get Google reviews" in h.value for h in at.subheader)
        assert any("Get Yelp reviews" in h.value for h in at.subheader)


def test_checking_tripadvisor_without_an_api_key_shows_the_not_connected_warning():
    at, stack = run_page()
    with stack:
        checkbox(at, "pull_platform_tripadvisor").set_value(True).run()
        assert not at.exception, [e.value for e in at.exception]
        assert any("Get TripAdvisor reviews" in h.value for h in at.subheader)
        assert any(
            "Outscraper is not connected" in w.value for w in at.warning
        )


def test_the_reviews_currently_stored_section_is_unconditional():
    at, stack = run_page()
    with stack:
        checkbox(at, "pull_platform_google").set_value(False).run()
        assert not at.exception, [e.value for e in at.exception]
        # Still present even with every platform unchecked.
        assert any("Reviews currently stored" in h.value for h in at.subheader)
