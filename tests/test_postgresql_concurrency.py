"""Testes optativos de concorrência real em PostgreSQL.

Defina TEST_POSTGRESQL_URL para um banco dedicado. Cada execução cria e remove
um schema isolado com nome aleatório; nunca use a URL de um banco de produção.
"""

import os
from uuid import uuid4

import pytest
from sqlalchemy.orm.exc import StaleDataError

from app.db.base import Base
from app.db.models import UserORM
from app.db.session import create_database_engine, create_session_factory
from app.models.professional_profile import ProfessionalProfile
from app.models.search_criteria import SearchCriteria
from app.repositories.professional_profile_repository import ProfessionalProfileRepository
from app.repositories.search_criteria_repository import SearchCriteriaRepository


_POSTGRESQL_URL = os.getenv("TEST_POSTGRESQL_URL")
pytestmark = pytest.mark.skipif(
    not _POSTGRESQL_URL,
    reason="Defina TEST_POSTGRESQL_URL para executar este teste em PostgreSQL.",
)


@pytest.fixture
def postgresql_session_factory():
    assert _POSTGRESQL_URL is not None
    engine = create_database_engine(_POSTGRESQL_URL, pool_pre_ping=True)
    schema = f"issue21_{uuid4().hex}"
    quote = engine.dialect.identifier_preparer.quote
    with engine.begin() as connection:
        connection.exec_driver_sql(f"CREATE SCHEMA {quote(schema)}")
    isolated_engine = engine.execution_options(schema_translate_map={None: schema})
    Base.metadata.create_all(isolated_engine)
    try:
        yield create_session_factory(isolated_engine)
    finally:
        Base.metadata.drop_all(isolated_engine)
        with engine.begin() as connection:
            connection.exec_driver_sql(f"DROP SCHEMA {quote(schema)}")
        engine.dispose()


@pytest.mark.parametrize("resource", ["criteria", "profile"])
def test_postgresql_rejects_stale_personal_data_write(postgresql_session_factory, resource) -> None:
    factory = postgresql_session_factory
    with factory.begin() as setup:
        user = UserORM()
        setup.add(user)
        setup.flush()
        user_id = user.id
        if resource == "criteria":
            SearchCriteriaRepository().save(setup, user_id, SearchCriteria(desired_title="Original"))
        else:
            ProfessionalProfileRepository().save(setup, user_id, ProfessionalProfile(name="Original"))

    with factory() as first, factory() as stale:
        if resource == "criteria":
            repository = SearchCriteriaRepository()
            repository.get_by_user_id(first, user_id)
            repository.get_by_user_id(stale, user_id)
            repository.save(first, user_id, SearchCriteria(desired_title="Atualizado"))
            first.commit()
            with pytest.raises(StaleDataError):
                repository.save(stale, user_id, SearchCriteria(desired_title="Obsoleto"))
            stale.rollback()
            current = repository.get_by_user_id(stale, user_id)
            assert current is not None and current.desired_title == "Atualizado"
        else:
            repository = ProfessionalProfileRepository()
            repository.get_by_user_id(first, user_id)
            repository.get_by_user_id(stale, user_id)
            repository.save(first, user_id, ProfessionalProfile(name="Atualizado"))
            first.commit()
            with pytest.raises(StaleDataError):
                repository.save(stale, user_id, ProfessionalProfile(name="Obsoleto"))
            stale.rollback()
            current = repository.get_by_user_id(stale, user_id)
            assert current is not None and current.name == "Atualizado"
