"""Testes do armazenamento e dos limites dos endpoints de autenticação."""

from fastapi.testclient import TestClient
import pytest

from app.api.dependencies import get_db_session
from app.db.session import create_session_factory
from app.main import create_app
from app.security.rate_limiting import (
    AuthRateLimitPolicy,
    AuthenticationRateLimiter,
    InMemoryRateLimitStore,
)
from config.settings import Settings


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


@pytest.fixture
def limited_client(database_engine):
    factory = create_session_factory(database_engine)

    def override_database_session():
        with factory() as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    policy = AuthRateLimitPolicy(
        login_ip_maximum=2,
        login_account_maximum=2,
        login_window_seconds=60,
        register_ip_maximum=2,
        register_account_maximum=1,
        register_window_seconds=60,
    )
    app = create_app(
        Settings(jwt_secret_key="x" * 48),
        rate_limit_policy=policy,
    )
    app.dependency_overrides[get_db_session] = override_database_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_sliding_limits_are_independent_and_expire() -> None:
    clock = FakeClock()
    store = InMemoryRateLimitStore(clock=clock)
    limiter = AuthenticationRateLimiter(
        store,
        AuthRateLimitPolicy(
            login_ip_maximum=2,
            login_account_maximum=2,
            login_window_seconds=10,
        ),
        fingerprint_key=b"chave-de-teste-com-tamanho-suficiente",
    )

    assert limiter.check("login", "ip-1", "Ana@example.com") is None
    assert limiter.check("login", "ip-2", "ana@example.com") is None
    assert limiter.check("login", "ip-3", "ANA@example.com") == 10

    clock.value = 10.1
    assert limiter.check("login", "ip-1", "ana@example.com") is None

    assert limiter.check("login", "ip-9", "conta-1@example.com") is None
    assert limiter.check("login", "ip-9", "conta-2@example.com") is None
    assert limiter.check("login", "ip-9", "conta-3@example.com") == 11


def test_login_ip_limit_ignores_untrusted_forwarded_headers(limited_client) -> None:
    responses = []
    for number in range(3):
        responses.append(
            limited_client.post(
                "/auth/login",
                json={"email": f"pessoa{number}@example.com", "password": "senha-incorreta"},
                headers={"X-Forwarded-For": f"198.51.100.{number + 1}"},
            )
        )

    assert [response.status_code for response in responses] == [401, 401, 429]
    assert responses[-1].json() == {
        "detail": "Muitas tentativas. Tente novamente mais tarde."
    }
    assert int(responses[-1].headers["retry-after"]) > 0


def test_registration_limits_are_generic_for_existing_and_new_emails(limited_client) -> None:
    payload = {"password": "uma-senha-forte-123"}
    first = limited_client.post(
        "/auth/register", json={**payload, "email": "ana@example.com"}
    )
    repeated_account = limited_client.post(
        "/auth/register", json={**payload, "email": "ANA@example.com"}
    )
    another_account = limited_client.post(
        "/auth/register", json={**payload, "email": "bia@example.com"}
    )
    ip_limited = limited_client.post(
        "/auth/register", json={**payload, "email": "caio@example.com"}
    )

    assert first.status_code == 202
    assert repeated_account.status_code == 429
    assert another_account.status_code == 202
    assert ip_limited.status_code == 429
    assert repeated_account.json() == ip_limited.json()
    assert "ana@example.com" not in repeated_account.text.lower()
