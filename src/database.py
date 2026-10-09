import os
from functools import lru_cache

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


load_dotenv()


@lru_cache(maxsize=4)
def _engine_for(database_url: str) -> Engine:
    # One shared engine per process. Creating a new engine on every call left each one holding its
    # own open connection, so a long save (a 200-page website scan) exhausted the database's limit
    # of 15 sessions and failed part-way. The pool is kept small because the app, the free-check
    # worker and local sessions share that limit.
    return create_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=3,
        max_overflow=3,
        pool_recycle=300,
    )


def get_engine() -> Engine:
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError("DATABASE_URL is not defined in .env")

    database_url = database_url.replace(
        "postgresql://",
        "postgresql+psycopg://",
        1,
    )

    return _engine_for(database_url)
