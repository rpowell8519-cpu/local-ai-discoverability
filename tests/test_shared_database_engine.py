"""Every caller shares one database engine, so repeated saves cannot exhaust the connection limit."""
from unittest.mock import patch

from src import database


def test_get_engine_returns_the_same_small_pooled_engine():
    database._engine_for.cache_clear()
    with patch.dict("os.environ", {"DATABASE_URL": "postgresql://user:secret@localhost:5432/example"}):
        first, second = database.get_engine(), database.get_engine()
    try:
        assert first is second
        assert first.pool.size() == 3 and first.pool._max_overflow == 3
        assert first.url.drivername == "postgresql+psycopg"
    finally:
        database._engine_for.cache_clear()
