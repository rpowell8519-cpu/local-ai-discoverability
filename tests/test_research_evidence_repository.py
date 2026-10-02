from unittest.mock import MagicMock, patch

import pytest

from src.research_evidence_repository import load_research_dataset

RUN = "11111111-1111-4111-8111-111111111111"


def test_legacy_run_without_optional_stores_is_read_only_and_explicitly_excluded():
    engine = MagicMock()
    connection = engine.connect.return_value.__enter__.return_value
    queries = []

    def rows(conn, sql, params=None):
        assert conn is connection
        queries.append(sql)
        if "to_regclass" in sql:
            return [{"name": name, "available": False} for name in params["names"]]
        if "from public.ai_visibility_runs" in sql:
            return [{"id": RUN, "target_google_place_id": "target", "started_at": "2026-09-01T00:00:00+00:00"}]
        return []

    summary = {"run_id": RUN, "rows": [], "issues": ["Historical panel metadata is unavailable"]}
    with patch("src.research_evidence_repository._rows", side_effect=rows), \
         patch("src.research_evidence_repository.summarise_wave", return_value=summary):
        result = load_research_dataset([RUN], engine=engine)
    assert not result["rows"]
    assert result["excluded_runs"][0]["reasons"] == summary["issues"]
    assert "repeatable read, read only" in str(connection.execute.call_args.args[0])
    assert all(sql.strip().lower().startswith("select") for sql in queries)
    assert not any("from public.public_evidence_captures" in sql for sql in queries)


@pytest.mark.parametrize("ids", [[], [RUN, RUN], ["invalid"], [RUN] * 11])
def test_invalid_or_unbounded_selection_never_opens_database(ids):
    engine = MagicMock()
    with pytest.raises(ValueError):
        load_research_dataset(ids, engine=engine)
    engine.connect.assert_not_called()
