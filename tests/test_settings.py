import pytest

from config.settings import Settings, SettingsError


def test_from_env_uses_safe_defaults() -> None:
    settings = Settings.from_env({})

    assert settings.app_env == "development"
    assert settings.log_level == "INFO"
    assert settings.ai_provider is None
    assert settings.ai_api_key is None
    assert settings.linkedin_client_id is None
    assert settings.linkedin_client_secret is None
    assert settings.linkedin_redirect_uri is None


def test_from_env_trims_values_and_normalizes_log_level() -> None:
    settings = Settings.from_env(
        {
            "APP_ENV": " staging ",
            "LOG_LEVEL": " debug ",
            "AI_PROVIDER": " local-model ",
            "LINKEDIN_CLIENT_ID": " client-id ",
        }
    )

    assert settings.app_env == "staging"
    assert settings.log_level == "DEBUG"
    assert settings.ai_provider == "local-model"
    assert settings.linkedin_client_id == "client-id"


def test_from_env_treats_blank_values_as_unset() -> None:
    settings = Settings.from_env(
        {
            "APP_ENV": "   ",
            "LOG_LEVEL": "",
            "AI_PROVIDER": "  ",
            "AI_API_KEY": "",
            "LINKEDIN_CLIENT_ID": "",
            "LINKEDIN_CLIENT_SECRET": " ",
            "LINKEDIN_REDIRECT_URI": "",
        }
    )

    assert settings.app_env == "development"
    assert settings.log_level == "INFO"
    assert settings.ai_provider is None
    assert settings.ai_api_key is None
    assert settings.linkedin_client_id is None
    assert settings.linkedin_client_secret is None
    assert settings.linkedin_redirect_uri is None


def test_from_env_rejects_unknown_log_level() -> None:
    with pytest.raises(SettingsError, match="LOG_LEVEL inválido"):
        Settings.from_env({"LOG_LEVEL": "verbose"})


def test_secret_values_are_not_in_settings_repr() -> None:
    settings = Settings.from_env(
        {
            "AI_API_KEY": "ai-secret-value",
            "LINKEDIN_CLIENT_SECRET": "linkedin-secret-value",
        }
    )

    assert "ai-secret-value" not in repr(settings)
    assert "linkedin-secret-value" not in repr(settings)
