"""Initialize an empty PostgreSQL database at the current model revision."""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from app.database import Base, engine
import app.models  # noqa: F401  Registers every model in Base.metadata.


def initialize() -> bool:
    if engine.dialect.name != "postgresql":
        raise RuntimeError("LUX Studio requires PostgreSQL")

    scripts = ScriptDirectory.from_config(Config(str(BACKEND_DIR / "alembic.ini")))
    head = scripts.get_current_head()
    if not head:
        raise RuntimeError("Alembic has no single head revision")

    with engine.begin() as connection:
        tables = set(inspect(connection).get_table_names())
        if "alembic_version" in tables:
            return False

        occupied = tables.intersection(Base.metadata.tables)
        if occupied:
            raise RuntimeError(
                "PostgreSQL contains application tables but no Alembic version; "
                "refusing to alter an unknown schema"
            )

        Base.metadata.create_all(connection)
        connection.execute(
            text(
                "CREATE TABLE alembic_version "
                "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
            )
        )
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:head)"),
            {"head": head},
        )

    print("Initialized empty PostgreSQL schema.")
    return True


if __name__ == "__main__":
    initialize()
