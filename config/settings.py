"""Configurações da aplicação lidas do ambiente do processo."""

from collections.abc import Mapping
from dataclasses import dataclass, field
import os


_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


class SettingsError(ValueError):
    """Indica que uma configuração do ambiente tem um valor inválido."""


@dataclass(frozen=True, slots=True)
class Settings:
    """Objeto de configurações da aplicação, sem dependências externas."""

    app_env: str = "development"
    log_level: str = "INFO"
    ai_provider: str | None = None
    ai_api_key: str | None = field(default=None, repr=False)
    linkedin_client_id: str | None = None
    linkedin_client_secret: str | None = field(default=None, repr=False)
    linkedin_redirect_uri: str | None = None

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        """Cria configurações a partir de um mapeamento ou de ``os.environ``.

        Valores secretos não aparecem na representação do objeto, evitando
        expor credenciais em logs ou durante a depuração.
        """
        source = os.environ if environ is None else environ

        def optional_value(name: str) -> str | None:
            value = source.get(name, "").strip()
            return value or None

        app_env = optional_value("APP_ENV") or "development"
        raw_log_level = optional_value("LOG_LEVEL") or "INFO"
        log_level = raw_log_level.upper()
        if log_level not in _LOG_LEVELS:
            allowed = ", ".join(sorted(_LOG_LEVELS))
            raise SettingsError(f"LOG_LEVEL inválido. Escolha um destes valores: {allowed}.")

        return cls(
            app_env=app_env,
            log_level=log_level,
            ai_provider=optional_value("AI_PROVIDER"),
            ai_api_key=optional_value("AI_API_KEY"),
            linkedin_client_id=optional_value("LINKEDIN_CLIENT_ID"),
            linkedin_client_secret=optional_value("LINKEDIN_CLIENT_SECRET"),
            linkedin_redirect_uri=optional_value("LINKEDIN_REDIRECT_URI"),
        )
