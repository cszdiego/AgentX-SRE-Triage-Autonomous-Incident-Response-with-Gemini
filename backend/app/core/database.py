import psycopg2
import psycopg2.extras
import psycopg2.pool
import logging
from contextlib import contextmanager
from typing import Generator
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def init_pool():
    global _pool
    _pool = psycopg2.pool.ThreadedConnectionPool(
        minconn=2,
        maxconn=20,
        dsn=settings.DATABASE_URL,
    )
    logger.info("Database connection pool initialized")


def init_schema():
    """Run schema.sql on startup."""
    import os
    schema_path = os.path.join(os.path.dirname(__file__), "../db/schema.sql")
    schema_path = os.path.abspath(schema_path)
    with open(schema_path, "r") as f:
        sql = f.read()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    logger.info("Database schema initialized")


@contextmanager
def get_conn() -> Generator[psycopg2.extensions.connection, None, None]:
    global _pool
    if _pool is None:
        init_pool()
    conn = _pool.getconn()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)


def fetchone(sql: str, params=None) -> dict | None:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            return dict(row) if row else None


def fetchall(sql: str, params=None) -> list[dict]:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]


def execute(sql: str, params=None) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()


def execute_returning(sql: str, params=None) -> dict | None:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            conn.commit()
            return dict(row) if row else None
