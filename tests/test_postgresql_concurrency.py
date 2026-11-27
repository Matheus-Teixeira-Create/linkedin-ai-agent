"""Testes optativos de concorrência real em PostgreSQL.

Defina TEST_POSTGRESQL_URL para um banco dedicado. Cada execução cria e remove
um schema isolado com nome aleatório; nunca use a URL de um banco de produção.
"""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import os
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
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
    if engine.dialect.name != "postgresql":
        engine.dispose()
        pytest.fail("TEST_POSTGRESQL_URL deve apontar para PostgreSQL.")
    with engine.begin() as connection:
        connection.exec_driver_sql(f"CREATE SCHEMA {quote(schema)}")
    isolated_engine = engine.execution_options(schema_translate_map={None: schema})
    try:
        Base.metadata.create_all(isolated_engine)
        yield create_session_factory(isolated_engine)
    finally:
        with engine.begin() as connection:
            connection.exec_driver_sql(f"DROP SCHEMA IF EXISTS {quote(schema)} CASCADE")
        engine.dispose()


@pytest.mark.parametrize("resource", ["criteria", "profile"])
def test_postgresql_rejects_simultaneous_personal_data_updates(postgresql_session_factory, resource) -> None:
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

    barrier = Barrier(2)

    def update(value: str) -> str:
        with factory() as session:
            if resource == "criteria":
                repository = SearchCriteriaRepository()
                repository.get_by_user_id(session, user_id)
                replacement = SearchCriteria(desired_title=value)
            else:
                repository = ProfessionalProfileRepository()
                repository.get_by_user_id(session, user_id)
                replacement = ProfessionalProfile(name=value)
            barrier.wait(timeout=15)
            try:
                repository.save(session, user_id, replacement)
                session.commit()
                return "salvo"
            except StaleDataError:
                session.rollback()
                return "conflito"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(update, ("Primeira", "Segunda")))
    assert sorted(outcomes) == ["conflito", "salvo"]

    with factory() as verification:
        if resource == "criteria":
            current = SearchCriteriaRepository().get_by_user_id(verification, user_id)
            assert current is not None and current.desired_title in {"Primeira", "Segunda"}
        else:
            current = ProfessionalProfileRepository().get_by_user_id(verification, user_id)
            assert current is not None and current.name in {"Primeira", "Segunda"}


@pytest.mark.parametrize("resource", ["criteria", "profile"])
def test_postgresql_maps_simultaneous_creation_to_one_winner(postgresql_session_factory, resource) -> None:
    factory = postgresql_session_factory
    with factory.begin() as setup:
        user = UserORM()
        setup.add(user)
        setup.flush()
        user_id = user.id

    barrier = Barrier(2)

    def create(value: str) -> str:
        with factory() as session:
            if resource == "criteria":
                repository = SearchCriteriaRepository()
                assert repository.get_by_user_id(session, user_id) is None
                replacement = SearchCriteria(desired_title=value)
            else:
                repository = ProfessionalProfileRepository()
                assert repository.get_by_user_id(session, user_id) is None
                replacement = ProfessionalProfile(name=value)
            barrier.wait(timeout=15)
            try:
                repository.save(session, user_id, replacement)
                session.commit()
                return "criado"
            except (IntegrityError, StaleDataError):
                session.rollback()
                return "conflito"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(create, ("Primeira", "Segunda")))
    assert sorted(outcomes) == ["conflito", "criado"]
