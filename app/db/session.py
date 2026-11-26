"""Criação explícita de engines e fábricas de sessão SQLAlchemy."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


class DatabaseConfigurationError(ValueError):
    """Indica uma configuração ausente ou inválida do banco."""


def create_database_engine(database_url: str, **engine_options: Any) -> Engine:
    """Cria um engine e habilita chaves estrangeiras em cada conexão SQLite."""
    if not isinstance(database_url, str) or not database_url.strip():
        raise DatabaseConfigurationError("DATABASE_URL deve conter uma URL de conexão.")
    engine = create_engine(database_url.strip(), **engine_options)
    if engine.dialect.name == "sqlite":
        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(connection: Any, _record: Any) -> None:
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Cria a fábrica; cada operação ou requisição abre sua própria Session."""
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Fecha a sessão e reverte a transação em caso de erro.

    A confirmação fica a cargo de quem chama, por exemplo com session.begin().
    """
    with factory() as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise
