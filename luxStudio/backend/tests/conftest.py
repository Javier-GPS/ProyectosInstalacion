from __future__ import annotations

import atexit
import os
import uuid

import pytest
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import create_engine, text


_schemas: list[tuple[str, str]] = []


def create_test_engine():
    """Create an isolated PostgreSQL schema and return an engine scoped to it."""
    database_url = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("PostgreSQL tests require TEST_DATABASE_URL or DATABASE_URL")
    schema = f"test_{uuid.uuid4().hex}"
    admin_engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with admin_engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    except SQLAlchemyError as exc:
        admin_engine.dispose()
        pytest.skip(f"PostgreSQL test database is unavailable: {exc}")
    admin_engine.dispose()
    _schemas.append((database_url, schema))
    return create_engine(
        database_url,
        connect_args={"options": f"-csearch_path={schema}"},
        pool_pre_ping=True,
    )


@atexit.register
def _drop_test_schemas() -> None:
    for database_url, schema in _schemas:
        engine = create_engine(database_url)
        try:
            with engine.begin() as connection:
                connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        finally:
            engine.dispose()
