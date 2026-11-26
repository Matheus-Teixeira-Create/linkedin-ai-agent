"""Testes HTTP de propriedade e isolamento dos dados pessoais por usuário."""

from uuid import UUID
import secrets

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select
from sqlalchemy.orm.exc import StaleDataError
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import get_db_session
from app.db.models import ProfessionalProfileORM, SearchCriteriaORM
from app.db.session import create_session_factory
from app.main import create_app
from app.models.search_criteria import SearchCriteria
from app.repositories.search_criteria_repository import SearchCriteriaRepository
from config.settings import Settings


@pytest.fixture
def personal_data_client(database_engine):
    factory = create_session_factory(database_engine)
    app = create_app(Settings(jwt_secret_key=secrets.token_urlsafe(48)))

    def override_database_session():
        with factory() as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    app.dependency_overrides[get_db_session] = override_database_session
    with TestClient(app) as client:
        yield client, factory
    app.dependency_overrides.clear()


def _register(client: TestClient, email: str) -> None:
    response = client.post(
        "/auth/register",
        json={"email": email, "password": "uma-senha-forte-123"},
    )
    assert response.status_code == 202


def _login(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/auth/login",
        json={"email": email, "password": "uma-senha-forte-123"},
    )
    assert response.status_code == 200
    return {
        name: client.cookies.get(name)
        for name in ("access_token", "refresh_token", "csrf_token")
    }


def _as_user(client: TestClient, credentials: dict[str, str]) -> None:
    client.cookies.clear()
    for name, value in credentials.items():
        client.cookies.set(name, value)


def _csrf(credentials: dict[str, str]) -> dict[str, str]:
    return {"X-CSRF-Token": credentials["csrf_token"]}


def test_criteria_are_isolated_for_read_update_delete_and_forged_ids(personal_data_client) -> None:
    client, factory = personal_data_client
    _register(client, "ana@example.com")
    ana = _login(client, "ana@example.com")
    _register(client, "bia@example.com")
    bia = _login(client, "bia@example.com")
    _as_user(client, ana)
    ana_id = client.get("/auth/me").json()["id"]
    _as_user(client, bia)
    bia_id = client.get("/auth/me").json()["id"]
    assert ana_id != bia_id

    _as_user(client, ana)
    created_ana = client.put(
        "/me/search-criteria",
        json={"desired_title": "Vaga exclusiva de Ana", "skills": ["Python"]},
        headers=_csrf(ana),
    )
    _as_user(client, bia)
    created_bia = client.put(
        "/me/search-criteria",
        json={"desired_title": "Vaga exclusiva de Bia", "skills": ["SQL"]},
        headers=_csrf(bia),
    )
    assert created_ana.status_code == created_bia.status_code == 200
    assert "user_id" not in created_ana.json()

    _as_user(client, ana)
    own = client.get("/me/search-criteria", params={"user_id": bia_id})
    assert own.status_code == 200
    assert own.json()["desired_title"] == "Vaga exclusiva de Ana"
    forged_body = client.patch(
        "/me/search-criteria",
        json={"user_id": bia_id, "desired_title": "conteudo privado que nao deve voltar"},
        headers=_csrf(ana),
    )
    assert forged_body.status_code == 422
    assert "conteudo privado" not in forged_body.text
    assert "user_id" not in forged_body.text

    forged_path = client.get(f"/me/search-criteria/{bia_id}")
    assert forged_path.status_code == 404
    update_own = client.patch(
        "/me/search-criteria?user_id=" + bia_id,
        json={"desired_title": "Ana atualizada"},
        headers=_csrf(ana),
    )
    assert update_own.status_code == 200
    assert update_own.json()["desired_title"] == "Ana atualizada"
    assert update_own.json()["skills"] == ["Python"]
    with factory() as session:
        assert session.scalar(
            select(SearchCriteriaORM).where(SearchCriteriaORM.user_id == UUID(bia_id))
        ).desired_title == "Vaga exclusiva de Bia"

    deleted_ana = client.delete(
        "/me/search-criteria?user_id=" + bia_id,
        headers=_csrf(ana),
    )
    assert deleted_ana.status_code == 204
    _as_user(client, bia)
    assert client.get("/me/search-criteria").json()["desired_title"] == "Vaga exclusiva de Bia"
    _as_user(client, ana)
    assert client.get("/me/search-criteria").status_code == 404


def test_profiles_are_isolated_and_ids_in_payloads_are_rejected(personal_data_client) -> None:
    client, factory = personal_data_client
    _register(client, "ana@example.com")
    ana = _login(client, "ana@example.com")
    _register(client, "bia@example.com")
    bia = _login(client, "bia@example.com")
    _as_user(client, bia)
    bia_id = client.get("/auth/me").json()["id"]

    _as_user(client, ana)
    ana_response = client.put(
        "/me/professional-profile",
        json={"name": "Ana", "technical_skills": ["Python"]},
        headers=_csrf(ana),
    )
    _as_user(client, bia)
    bia_response = client.put(
        "/me/professional-profile",
        json={"name": "Bia", "technical_skills": ["SQL"]},
        headers=_csrf(bia),
    )
    assert ana_response.status_code == bia_response.status_code == 200
    assert "user_id" not in bia_response.json()

    _as_user(client, ana)
    profile_with_forged_query = client.get(
        "/me/professional-profile", params={"user_id": bia_id}
    )
    assert profile_with_forged_query.status_code == 200
    assert profile_with_forged_query.json()["name"] == "Ana"

    forged = client.patch(
        "/me/professional-profile",
        json={"user_id": bia_id, "name": "informacao privada sensivel"},
        headers=_csrf(ana),
    )
    assert forged.status_code == 422
    assert "informacao privada" not in forged.text

    changed_ana = client.patch(
        "/me/professional-profile?user_id=" + bia_id,
        json={"name": "Ana atualizada"},
        headers=_csrf(ana),
    )
    assert changed_ana.status_code == 200
    assert changed_ana.json()["name"] == "Ana atualizada"
    assert changed_ana.json()["technical_skills"] == ["Python"]
    with factory() as session:
        bia_profile = session.scalar(
            select(ProfessionalProfileORM).where(
                ProfessionalProfileORM.user_id == UUID(bia_id)
            )
        )
        assert bia_profile.name == "Bia"

    deleted = client.delete(
        "/me/professional-profile?user_id=" + bia_id,
        headers=_csrf(ana),
    )
    assert deleted.status_code == 204
    _as_user(client, bia)
    assert client.get("/me/professional-profile").json()["name"] == "Bia"


def test_personal_routes_require_authentication_and_csrf(personal_data_client) -> None:
    client, _ = personal_data_client
    assert client.get("/me/search-criteria").status_code == 401
    assert client.get("/me/professional-profile").status_code == 401
    assert client.put("/me/search-criteria", json={"desired_title": "Teste"}).status_code == 401
    assert client.delete("/me/professional-profile").status_code == 401

    _register(client, "ana@example.com")
    credentials = _login(client, "ana@example.com")
    client.cookies.clear()
    client.cookies.set("access_token", credentials["access_token"])
    assert client.put("/me/search-criteria", json={"desired_title": "Teste"}).status_code == 403


def test_existing_repository_data_remains_available_to_its_owner(personal_data_client) -> None:
    client, factory = personal_data_client
    _register(client, "ana@example.com")
    ana = _login(client, "ana@example.com")
    _as_user(client, ana)
    user_id = client.get("/auth/me").json()["id"]
    with factory.begin() as session:
        SearchCriteriaRepository().save(
            session,
            UUID(user_id),
            SearchCriteria(desired_title="Critério legado"),
        )
    assert client.get("/me/search-criteria").json()["desired_title"] == "Critério legado"


def test_concurrent_write_conflict_returns_generic_http_409(personal_data_client, monkeypatch) -> None:
    client, _ = personal_data_client
    _register(client, "ana@example.com")
    credentials = _login(client, "ana@example.com")
    _as_user(client, credentials)

    def stale_write(*args, **kwargs):
        raise StaleDataError("valor sensível de banco")

    monkeypatch.setattr(SearchCriteriaRepository, "save", stale_write)
    response = client.put(
        "/me/search-criteria",
        json={"desired_title": "Desenvolvedora"},
        headers=_csrf(credentials),
    )
    assert response.status_code == 409
    assert response.json() == {
        "detail": "Os dados foram alterados simultaneamente. Recarregue e tente novamente."
    }
    assert "valor sensível" not in response.text


def test_creation_constraint_conflict_returns_http_409(personal_data_client, monkeypatch) -> None:
    client, _ = personal_data_client
    _register(client, "bia@example.com")
    credentials = _login(client, "bia@example.com")
    _as_user(client, credentials)

    def duplicate_creation(*args, **kwargs):
        raise IntegrityError("INSERT", {}, RuntimeError("valor interno"))

    monkeypatch.setattr(SearchCriteriaRepository, "save", duplicate_creation)
    response = client.put(
        "/me/search-criteria",
        json={"desired_title": "Analista"},
        headers=_csrf(credentials),
    )
    assert response.status_code == 409
    assert "valor interno" not in response.text


def test_internal_error_response_and_log_do_not_expose_personal_data(
    personal_data_client, monkeypatch, caplog
) -> None:
    import logging
    from fastapi.testclient import TestClient

    client, _ = personal_data_client
    _register(client, "caio@example.com")
    credentials = _login(client, "caio@example.com")
    safe_client = TestClient(client.app, raise_server_exceptions=False)
    _as_user(safe_client, credentials)

    def database_failure(*args, **kwargs):
        raise RuntimeError("e-mail privado e SQL confidencial")

    monkeypatch.setattr(SearchCriteriaRepository, "get_by_user_id", database_failure)
    with caplog.at_level(logging.ERROR):
        response = safe_client.get("/me/search-criteria")

    assert response.status_code == 500
    assert response.json()["detail"] == "Não foi possível processar a requisição."
    assert len(response.json()["request_id"]) == 16
    assert "e-mail privado" not in response.text
    assert "e-mail privado" not in caplog.text
    safe_client.close()
