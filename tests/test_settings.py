import pytest
import secrets
import base64
from fastapi.testclient import TestClient

from app.main import create_app
from config.settings import Settings, SettingsError


class FakeDeclaredSharedStore:
    """Reproduz um adaptador que apenas declara compartilhar o estado."""

    is_shared = True

    def check_and_record(self, rules):
        return None


def _production_settings(jwt_secret: str | None) -> Settings:
    return Settings(
        app_env="production",
        jwt_secret_key=jwt_secret,
        database_url="postgresql+psycopg://user:password@localhost/app",
        auth_cookie_secure=True,
    )


def test_from_env_uses_safe_defaults() -> None:
    settings = Settings.from_env({"APP_ENV": "development"})

    assert settings.app_env == "development"
    assert settings.log_level == "INFO"
    assert settings.ai_provider is None
    assert settings.ai_api_key is None
    assert settings.linkedin_client_id is None
    assert settings.linkedin_client_secret is None
    assert settings.linkedin_redirect_uri is None
    assert settings.database_url is None
    assert settings.app_env == "development"
    settings.validate_environment()


def test_from_env_rejects_missing_or_blank_app_env() -> None:
    with pytest.raises(SettingsError, match="APP_ENV deve ser definido"):
        Settings.from_env({})
    with pytest.raises(SettingsError, match="APP_ENV deve ser definido"):
        Settings.from_env({"APP_ENV": "   "})


def test_from_env_without_mapping_requires_process_app_env(monkeypatch) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    with pytest.raises(SettingsError, match="APP_ENV deve ser definido"):
        Settings.from_env()


def test_settings_requires_explicit_environment_when_constructed_directly() -> None:
    with pytest.raises(SettingsError, match="APP_ENV deve ser definido"):
        Settings()
    with pytest.raises(SettingsError, match="APP_ENV deve ser definido"):
        create_app(Settings())


def test_from_env_trims_values_and_normalizes_log_level() -> None:
    settings = Settings.from_env(
        {
            "APP_ENV": " staging ",
            "LOG_LEVEL": " debug ",
            "AI_PROVIDER": " local-model ",
            "LINKEDIN_CLIENT_ID": " client-id ",
            "DATABASE_URL": " postgresql+psycopg://local:secret@localhost/app ",
        }
    )

    assert settings.app_env == "staging"
    assert settings.log_level == "DEBUG"
    assert settings.ai_provider == "local-model"
    assert settings.linkedin_client_id == "client-id"
    assert settings.database_url == "postgresql+psycopg://local:secret@localhost/app"


def test_from_env_treats_blank_values_as_unset() -> None:
    settings = Settings.from_env(
        {
            "APP_ENV": "development",
            "LOG_LEVEL": "",
            "AI_PROVIDER": "  ",
            "AI_API_KEY": "",
            "LINKEDIN_CLIENT_ID": "",
            "LINKEDIN_CLIENT_SECRET": " ",
            "LINKEDIN_REDIRECT_URI": "",
            "DATABASE_URL": " ",
        }
    )

    assert settings.app_env == "development"
    assert settings.log_level == "INFO"
    assert settings.ai_provider is None
    assert settings.ai_api_key is None
    assert settings.linkedin_client_id is None
    assert settings.linkedin_client_secret is None
    assert settings.linkedin_redirect_uri is None
    assert settings.database_url is None


def test_from_env_rejects_unknown_log_level() -> None:
    with pytest.raises(SettingsError, match="LOG_LEVEL inválido"):
        Settings.from_env({"APP_ENV": "development", "LOG_LEVEL": "verbose"})


def test_from_env_rejects_unknown_app_env_and_normalizes_known_values() -> None:
    with pytest.raises(SettingsError, match="APP_ENV inválido"):
        Settings.from_env({"APP_ENV": "prod"})
    assert Settings.from_env({"APP_ENV": " STAGING "}).app_env == "staging"


def test_production_requires_explicit_secure_cookie_configuration() -> None:
    with pytest.raises(SettingsError, match="AUTH_COOKIE_SECURE=true"):
        Settings.from_env({"APP_ENV": "production"})
    assert Settings.from_env(
        {"APP_ENV": "production", "AUTH_COOKIE_SECURE": "true"}
    ).auth_cookie_secure is True
    for value in ("1", "yes"):
        with pytest.raises(SettingsError, match="exatamente como true"):
            Settings.from_env({"APP_ENV": "production", "AUTH_COOKIE_SECURE": value})


def test_samesite_error_lists_every_supported_value() -> None:
    with pytest.raises(SettingsError, match="'lax', 'strict' ou 'none'"):
        Settings.from_env({"APP_ENV": "development", "AUTH_COOKIE_SAMESITE": "invalid"})


def test_app_rejects_invalid_or_insecure_production_settings() -> None:
    with pytest.raises(SettingsError, match="APP_ENV inválido"):
        create_app(Settings(app_env="prod"))
    with pytest.raises(SettingsError, match="AUTH_COOKIE_SECURE"):
        create_app(
            Settings(
                app_env="production",
                jwt_secret_key=secrets.token_urlsafe(48),
                database_url="sqlite+pysqlite:///:memory:",
                auth_cookie_secure=False,
            )
        )
    with pytest.raises(SettingsError, match="JWT_SECRET_KEY"):
        create_app(
            Settings(
                app_env="production",
                database_url="sqlite+pysqlite:///:memory:",
                auth_cookie_secure=True,
            )
        )
    with pytest.raises(SettingsError, match="DATABASE_URL"):
        create_app(
            Settings(
                app_env="production",
                jwt_secret_key=secrets.token_urlsafe(48),
                auth_cookie_secure=True,
            )
        )


def test_development_configuration_starts_without_production_secrets() -> None:
    with TestClient(create_app(Settings.from_env({"APP_ENV": "development"}))) as client:
        assert client.get("/docs").status_code == 200


def test_asgi_entrypoint_refuses_to_start_without_explicit_app_env(monkeypatch) -> None:
    from app.main import _create_asgi_entrypoint

    monkeypatch.delenv("APP_ENV", raising=False)
    with pytest.raises(RuntimeError, match="Configuração obrigatória"):
        with TestClient(_create_asgi_entrypoint()):
            pass


def test_valid_production_settings_still_cannot_start_without_a_concrete_shared_store() -> None:
    settings = Settings.from_env(
        {
            "APP_ENV": "production",
            "AUTH_COOKIE_SECURE": "true",
            "JWT_SECRET_KEY": secrets.token_urlsafe(48),
            "DATABASE_URL": "postgresql+psycopg://user:password@localhost/app",
        }
    )
    settings.validate_authentication()
    with pytest.raises(SettingsError, match="armazenamento compartilhado.*concreto e validado"):
        create_app(settings)


def test_jwt_secret_accepts_at_least_256_random_bits() -> None:
    secret = secrets.token_urlsafe(48)
    settings = _production_settings(secret)
    settings.validate_authentication()


@pytest.mark.parametrize(
    "secret",
    [
        None,
        "",
        "chave*malformada",
        secrets.token_urlsafe(16),
        base64.urlsafe_b64encode(b"R" * 32).decode("ascii").rstrip("="),
        "abcdefghijkl" * 3,
        base64.urlsafe_b64encode(bytes(range(32))).decode("ascii").rstrip("="),
        base64.urlsafe_b64encode(b"Passw0rd!EntropyX" * 2).decode("ascii").rstrip("="),
        base64.urlsafe_b64encode(b"password" + secrets.token_bytes(32)).decode("ascii").rstrip("="),
        base64.urlsafe_b64encode(b"qwertyuiop" + secrets.token_bytes(32)).decode("ascii").rstrip("="),
    ],
    ids=[
        "ausente", "vazio", "malformado", "curto", "repetitivo", "sequencia-alfabetica",
        "bytes-sequenciais", "padrao-da-auditoria", "senha-conhecida", "sequencia-de-teclado",
    ],
)
def test_jwt_secret_rejects_short_empty_repetitive_and_predictable_values(secret) -> None:
    with pytest.raises(SettingsError, match="JWT_SECRET_KEY"):
        create_app(_production_settings(secret), rate_limit_store=FakeDeclaredSharedStore())


def test_production_rejects_missing_memory_and_fake_declared_shared_rate_limit_stores() -> None:
    settings = Settings(
        app_env="production",
        jwt_secret_key=secrets.token_urlsafe(48),
        database_url="postgresql+psycopg://user:password@localhost/app",
        auth_cookie_secure=True,
    )
    with pytest.raises(SettingsError, match="armazenamento compartilhado.*concreto e validado"):
        create_app(settings)
    from app.security.rate_limiting import InMemoryRateLimitStore

    with pytest.raises(SettingsError, match="armazenamento compartilhado.*concreto e validado"):
        create_app(settings, rate_limit_store=InMemoryRateLimitStore())
    with pytest.raises(SettingsError, match="armazenamento compartilhado.*concreto e validado"):
        create_app(settings, rate_limit_store=FakeDeclaredSharedStore())


def test_secret_values_are_not_in_settings_repr() -> None:
    settings = Settings.from_env(
        {
            "APP_ENV": "development",
            "AI_API_KEY": "ai-secret-value",
            "LINKEDIN_CLIENT_SECRET": "linkedin-secret-value",
            "DATABASE_URL": "postgresql+psycopg://user:db-secret@localhost/app",
        }
    )

    assert "ai-secret-value" not in repr(settings)
    assert "linkedin-secret-value" not in repr(settings)
    assert "db-secret" not in repr(settings)


def test_database_url_is_validated_without_echoing_credentials() -> None:
    with pytest.raises(SettingsError, match="URL de banco v\u00e1lida"):
        create_app(Settings(app_env="development", database_url="not-a-url"))
    with pytest.raises(SettingsError, match="PostgreSQL em produ\u00e7\u00e3o"):
        create_app(
            Settings(
                app_env="production",
                jwt_secret_key=secrets.token_urlsafe(48),
                database_url="sqlite+pysqlite:///:memory:",
                auth_cookie_secure=True,
            ),
            rate_limit_store=object(),
        )
