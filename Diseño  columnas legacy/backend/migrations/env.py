"""
Alembic env.py — Salvi Studio · Columns
Carga todos los modelos para que Alembic genere migraciones automáticas.
"""
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

# Importar Base y TODOS los modelos para que Alembic los detecte
from app.core.database import Base
import app.models.db.users       # noqa: F401
import app.models.db.projects    # noqa: F401
import app.models.db.libraries   # noqa: F401
import app.models.db.audit       # noqa: F401
import app.models.db.geometry    # noqa: F401
import app.models.db.actions     # noqa: F401
import app.models.db.structural  # noqa: F401
import app.models.db.steel       # noqa: F401
import app.models.db.aluminium   # noqa: F401
import app.models.db.concrete    # noqa: F401
import app.models.db.details     # noqa: F401
import app.models.db.joints      # noqa: F401
import app.models.db.baseplate   # noqa: F401
import app.models.db.foundation  # noqa: F401
import app.models.db.catalog     # noqa: F401
import app.models.db.optimization  # noqa: F401
import app.models.db.cad_bom       # noqa: F401
import app.models.db.reports       # noqa: F401
import app.models.db.catenary      # noqa: F401
import app.models.db.validation    # noqa: F401
from app.core.config import settings

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url_sync)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
