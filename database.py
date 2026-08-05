import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


load_dotenv()


def get_engine() -> Engine:
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError("DATABASE_URL is not defined in .env")

    database_url = database_url.replace(
        "postgresql://",
        "postgresql+psycopg://",
        1,
    )

    return create_engine(
        database_url,
        pool_pre_ping=True,
    )