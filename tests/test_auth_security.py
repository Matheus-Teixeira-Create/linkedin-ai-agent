"""Testes unitários para senhas, configurações e JWTs."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.security.passwords import PasswordManager
from app.security.tokens import AccessTokenManager, InvalidAccessToken
from config.settings import Settings, SettingsError


def test_passwords_use_salted_argon2id_hashes() -> None:
    manager = PasswordManager()
    first = manager.hash("senha-de-teste-segura")
    second = manager.hash("senha-de-teste-segura")

    assert first.startswith("$argon2id$")
    assert first != second
    assert manager.verify("senha-de-teste-segura", first)
    assert not manager.verify("senha-incorreta", first)
    assert not manager.verify("senha-de-teste-segura", None)


def test_jwt_has_required_identity_claims_and_decodes_with_fixed_algorithm() -> None:
    manager = AccessTokenManager(Settings(jwt_secret_key="s" * 48))
    user_id, session_id = uuid4(), uuid4()
    issued = manager.issue(user_id, session_id)

    assert manager.decode(issued.value).user_id == user_id
    assert manager.decode(issued.value).session_id == session_id
    assert issued.expires_at > datetime.now(UTC)


def test_expired_tampered_wrong_issuer_and_wrong_audience_tokens_are_rejected() -> None:
    secret = "s" * 48
    settings = Settings(jwt_secret_key=secret)
    manager = AccessTokenManager(settings)
    now = datetime.now(UTC)
    user_id, session_id = uuid4(), uuid4()

    expired = manager.issue(user_id, session_id, now - timedelta(hours=1))
    with pytest.raises(InvalidAccessToken):
        manager.decode(expired.value)

    valid = manager.issue(user_id, session_id).value
    altered = valid[:-1] + ("a" if valid[-1] != "a" else "b")
    with pytest.raises(InvalidAccessToken):
        manager.decode(altered)

    other_issuer = AccessTokenManager(Settings(jwt_secret_key=secret, jwt_issuer="outro-emissor"))
    with pytest.raises(InvalidAccessToken):
        manager.decode(other_issuer.issue(user_id, session_id).value)

    other_audience = AccessTokenManager(Settings(jwt_secret_key=secret, jwt_audience="outro-cliente"))
    with pytest.raises(InvalidAccessToken):
        manager.decode(other_audience.issue(user_id, session_id).value)


def test_authentication_secret_is_required_and_hidden_from_repr() -> None:
    settings = Settings.from_env({"JWT_SECRET_KEY": "segredo-de-teste-que-nao-deve-aparecer-123"})
    assert "segredo-de-teste" not in repr(settings)
    settings.validate_authentication()

    with pytest.raises(SettingsError, match="JWT_SECRET_KEY"):
        AccessTokenManager(Settings())
    with pytest.raises(SettingsError, match="produção"):
        Settings(
            app_env="production",
            jwt_secret_key="s" * 48,
            auth_cookie_secure=False,
        ).validate_authentication()


def test_cookie_settings_validate_same_site_and_positive_token_lifetimes() -> None:
    assert Settings.from_env(
        {"APP_ENV": "production", "AUTH_COOKIE_SECURE": "true"}
    ).auth_cookie_secure is True
    with pytest.raises(SettingsError, match="SameSite 'none'"):
        Settings.from_env({"AUTH_COOKIE_SAMESITE": "none", "JWT_SECRET_KEY": "s" * 48}).validate_authentication()
    with pytest.raises(SettingsError, match="ACCESS_TOKEN_TTL_MINUTES"):
        Settings.from_env({"ACCESS_TOKEN_TTL_MINUTES": "0"})
