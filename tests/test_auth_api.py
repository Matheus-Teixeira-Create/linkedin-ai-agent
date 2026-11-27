"""Testes HTTP de cadastro, autenticação e gerenciamento de sessões."""

from fastapi.testclient import TestClient
import secrets
import pytest
from sqlalchemy import select

from app.api.dependencies import get_db_session
from app.db.models import AuthSessionORM, RefreshTokenORM, UserORM
from app.db.session import create_session_factory
from app.main import create_app
from config.settings import Settings


@pytest.fixture
def auth_client(database_engine):
    factory = create_session_factory(database_engine)
    app = create_app(
        Settings(
            app_env="test",
            database_url=None,
            jwt_secret_key=secrets.token_urlsafe(48),
            auth_cookie_secure=False,
            auth_cookie_samesite="lax",
        )
    )

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
        yield client
    app.dependency_overrides.clear()


def _register(client: TestClient, email: str = "ana@example.com") -> None:
    response = client.post(
        "/auth/register",
        json={"email": email, "password": "uma-senha-forte-123"},
    )
    assert response.status_code == 202


def _login(client: TestClient, email: str = "ana@example.com"):
    return client.post(
        "/auth/login",
        json={"email": email, "password": "uma-senha-forte-123"},
    )


def test_register_normalizes_email_and_never_returns_password_hash(auth_client, database_engine) -> None:
    response = auth_client.post(
        "/auth/register",
        json={"email": " Ana@Example.com ", "password": "uma-senha-forte-123"},
    )
    assert response.status_code == 202
    assert response.json() == {"message": "Solicitação de cadastro processada."}
    assert "password" not in response.text
    assert "password_hash" not in response.text

    with create_session_factory(database_engine)() as session:
        user = session.scalar(select(UserORM))
        assert user is not None
        assert user.email == "ana@example.com"
        assert user.email_normalized == "ana@example.com"
        assert user.password_hash is not None
        assert user.password_hash != "uma-senha-forte-123"
        assert user.password_hash.startswith("$argon2id$")


def test_duplicate_registration_has_generic_response_and_database_uniqueness(auth_client, database_engine) -> None:
    _register(auth_client)
    first = auth_client.post(
        "/auth/register",
        json={"email": "ANA@example.com", "password": "uma-senha-forte-123"},
    )
    assert first.status_code == 202
    assert first.json() == {"message": "Solicitação de cadastro processada."}
    with create_session_factory(database_engine)() as session:
        assert len(session.scalars(select(UserORM)).all()) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "endereço-inválido", "password": "uma-senha-forte-123"},
        {"email": "ana@example.com", "password": "curta"},
    ],
)
def test_registration_validates_email_and_password(auth_client, payload) -> None:
    response = auth_client.post("/auth/register", json=payload)
    assert response.status_code == 422


@pytest.mark.parametrize("email,password", [("ana@example.com", "senha-errada-123"), ("naoexiste@example.com", "senha-errada-123")])
def test_login_failures_are_generic(auth_client, email: str, password: str) -> None:
    _register(auth_client)
    response = auth_client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 401
    assert response.json() == {"detail": "E-mail ou senha inválidos."}
    assert "access_token" not in response.text
    assert "refresh_token" not in response.text


def test_login_sets_http_only_cookies_and_authenticated_user_response(auth_client) -> None:
    _register(auth_client)
    response = _login(auth_client)

    assert response.status_code == 200
    assert response.json()["email"] == "ana@example.com"
    assert "access_token" not in response.json()
    assert "refresh_token" not in response.json()
    assert "password_hash" not in response.json()
    for cookie_name in ("access_token", "refresh_token"):
        cookie = response.cookies.get(cookie_name)
        assert cookie
        header = next(value for value in response.headers.get_list("set-cookie") if value.startswith(cookie_name))
        assert "httponly" in header.lower()
        assert "samesite=lax" in header.lower()
    csrf_header = next(
        value for value in response.headers.get_list("set-cookie") if value.startswith("csrf_token")
    )
    assert "httponly" not in csrf_header.lower()
    assert "no-store" in response.headers["cache-control"]

    me = auth_client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "ana@example.com"
    assert "password_hash" not in me.json()


def test_production_cookie_configuration_sets_secure_flag(auth_client) -> None:
    auth_client.app.state.settings = Settings(
        app_env="test",
        jwt_secret_key=secrets.token_urlsafe(48),
        auth_cookie_secure=True,
        auth_cookie_samesite="strict",
    )
    _register(auth_client)
    response = _login(auth_client)
    assert response.status_code == 200
    auth_cookies = [
        value.lower()
        for value in response.headers.get_list("set-cookie")
        if value.startswith(("access_token", "refresh_token"))
    ]
    assert len(auth_cookies) == 2
    assert all("secure" in cookie and "httponly" in cookie for cookie in auth_cookies)
    assert all("samesite=strict" in cookie for cookie in auth_cookies)


def test_refresh_rotates_tokens_and_replay_revokes_the_session(auth_client, database_engine) -> None:
    _register(auth_client)
    login = _login(auth_client)
    assert login.status_code == 200
    old_refresh = auth_client.cookies.get("refresh_token")
    old_access = auth_client.cookies.get("access_token")
    old_csrf = auth_client.cookies.get("csrf_token")
    assert old_refresh and old_access and old_csrf

    missing_csrf = auth_client.post("/auth/refresh")
    assert missing_csrf.status_code == 403

    refreshed = auth_client.post("/auth/refresh", headers={"X-CSRF-Token": old_csrf})
    assert refreshed.status_code == 200
    assert refreshed.json() == {"message": "Sessão renovada."}
    new_refresh = auth_client.cookies.get("refresh_token")
    new_access = auth_client.cookies.get("access_token")
    new_csrf = auth_client.cookies.get("csrf_token")
    assert new_refresh and new_access and new_csrf
    assert new_refresh != old_refresh
    assert new_access != old_access
    assert new_csrf != old_csrf
    assert "refresh_token" not in refreshed.json()
    assert "access_token" not in refreshed.json()

    auth_client.cookies.clear()
    auth_client.cookies.set("refresh_token", old_refresh)
    auth_client.cookies.set("csrf_token", new_csrf)
    replay = auth_client.post("/auth/refresh", headers={"X-CSRF-Token": new_csrf})
    assert replay.status_code == 401
    auth_client.cookies.clear()
    auth_client.cookies.set("access_token", new_access)
    assert auth_client.get("/auth/me").status_code == 401
    with create_session_factory(database_engine)() as session:
        auth_session = session.scalar(select(AuthSessionORM))
        assert auth_session is not None
        assert auth_session.revoked_at is not None
        refresh_rows = session.scalars(select(RefreshTokenORM)).all()
        assert len(refresh_rows) == 2
        assert all(item.revoked_at is not None for item in refresh_rows)


def test_logout_revokes_session_and_csrf_is_required(auth_client) -> None:
    _register(auth_client)
    login = _login(auth_client)
    old_access = auth_client.cookies.get("access_token")
    csrf = auth_client.cookies.get("csrf_token")
    assert old_access and csrf

    denied = auth_client.post("/auth/logout")
    assert denied.status_code == 403
    # O logout deve funcionar mesmo quando o access token não é mais utilizável.
    auth_client.cookies.set("access_token", "access-token-expirado")
    logout = auth_client.post("/auth/logout", headers={"X-CSRF-Token": csrf})
    assert logout.status_code == 204
    auth_client.cookies.clear()
    auth_client.cookies.set("access_token", old_access)
    assert auth_client.get("/auth/me").status_code == 401
    assert "max-age=0" in " ".join(logout.headers.get_list("set-cookie")).lower()


def test_client_cannot_choose_authenticated_user_id(auth_client) -> None:
    _register(auth_client, "ana@example.com")
    _register(auth_client, "bia@example.com")
    _login(auth_client, "ana@example.com")
    own_id = auth_client.get("/auth/me").json()["id"]

    _login(auth_client, "bia@example.com")
    other_id = auth_client.get("/auth/me").json()["id"]
    assert own_id != other_id

    _login(auth_client, "ana@example.com")
    forged_query = auth_client.get("/auth/me", params={"user_id": other_id})
    assert forged_query.status_code == 200
    assert forged_query.json()["id"] == own_id
    forged_body = auth_client.post(
        "/auth/register",
        json={"user_id": other_id, "email": "c@example.com", "password": "uma-senha-forte-123"},
    )
    assert forged_body.status_code == 422
