"""Fixtures de persistência em SQLite em memória, sem servidor externo."""

import pytest
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import create_database_engine, create_session_factory
import app.db.models  # noqa: F401 - registra todos os modelos antes do create_all


@pytest.fixture
def database_engine():
    engine = create_database_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db_session(database_engine):
    factory = create_session_factory(database_engine)
    with factory() as session:
        yield session
        if session.in_transaction():
            session.rollback()
