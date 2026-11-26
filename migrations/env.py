"""Ambiente Alembic: usa DATABASE_URL sem gravar credenciais no ini."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.db.base import Base
from app.db.session import create_database_engine
from config.settings import Settings
import app.db.models  # noqa: F401 - registra todos os mapeamentos na metadata


config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    configured = Settings.from_env().database_url or config.get_main_option("sqlalchemy.url")
    if not configured:
        raise RuntimeError("Defina DATABASE_URL antes de executar migrations Alembic.")
    config.set_main_option("sqlalchemy.url", configured.replace("%", "%%"))
    return configured


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_with_connection(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    injected_connection = config.attributes.get("connection")
    if injected_connection is not None:
        _run_with_connection(injected_connection)
        return

    engine = create_database_engine(_database_url(), poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            _run_with_connection(connection)
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
