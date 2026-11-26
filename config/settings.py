"""Configurações da aplicação lidas do ambiente do processo."""

from collections.abc import Mapping
from dataclasses import dataclass, field
import os


_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
_APP_ENVIRONMENTS = frozenset({"development", "test", "staging", "production"})
_SAME_SITE_VALUES = frozenset({"lax", "strict", "none"})


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
    database_url: str | None = field(default=None, repr=False)
    jwt_secret_key: str | None = field(default=None, repr=False)
    jwt_issuer: str = "linkedin-ai-agent"
    jwt_audience: str = "linkedin-ai-agent-client"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 14
    auth_cookie_secure: bool = False
    auth_cookie_samesite: str = "lax"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        """Cria configurações a partir de um mapeamento ou de ``os.environ``.

        Segredos e a URL do banco não aparecem na representação do objeto,
        evitando exposição acidental em logs ou durante a depuração.
        """
        source = os.environ if environ is None else environ

        def optional_value(name: str) -> str | None:
            value = source.get(name, "").strip()
            return value or None

        app_env = (optional_value("APP_ENV") or "development").casefold()
        if app_env not in _APP_ENVIRONMENTS:
            allowed = ", ".join(sorted(_APP_ENVIRONMENTS))
            raise SettingsError(f"APP_ENV inválido. Escolha um destes valores: {allowed}.")
        raw_log_level = optional_value("LOG_LEVEL") or "INFO"
        log_level = raw_log_level.upper()
        if log_level not in _LOG_LEVELS:
            allowed = ", ".join(sorted(_LOG_LEVELS))
            raise SettingsError(f"LOG_LEVEL inválido. Escolha um destes valores: {allowed}.")

        same_site = (optional_value("AUTH_COOKIE_SAMESITE") or "lax").lower()
        if same_site not in _SAME_SITE_VALUES:
            raise SettingsError("AUTH_COOKIE_SAMESITE deve ser 'lax', 'strict' ou 'none'.")

        def positive_integer(name: str, default: int) -> int:
            raw = optional_value(name)
            if raw is None:
                return default
            try:
                value = int(raw)
            except ValueError:
                raise SettingsError(f"{name} deve ser um número inteiro positivo.") from None
            if value <= 0:
                raise SettingsError(f"{name} deve ser um número inteiro positivo.")
            return value

        raw_cookie_secure = optional_value("AUTH_COOKIE_SECURE")
        if app_env == "production" and raw_cookie_secure is None:
            raise SettingsError("AUTH_COOKIE_SECURE=true deve ser configurado em produção.")
        if raw_cookie_secure is None:
            cookie_secure = app_env.casefold() == "production"
        elif raw_cookie_secure.casefold() in {"true", "1", "yes"}:
            cookie_secure = True
        elif raw_cookie_secure.casefold() in {"false", "0", "no"}:
            cookie_secure = False
        else:
            raise SettingsError("AUTH_COOKIE_SECURE deve ser true ou false.")

        jwt_issuer = optional_value("JWT_ISSUER") or "linkedin-ai-agent"
        jwt_audience = optional_value("JWT_AUDIENCE") or "linkedin-ai-agent-client"

        return cls(
            app_env=app_env,
            log_level=log_level,
            ai_provider=optional_value("AI_PROVIDER"),
            ai_api_key=optional_value("AI_API_KEY"),
            linkedin_client_id=optional_value("LINKEDIN_CLIENT_ID"),
            linkedin_client_secret=optional_value("LINKEDIN_CLIENT_SECRET"),
            linkedin_redirect_uri=optional_value("LINKEDIN_REDIRECT_URI"),
            database_url=optional_value("DATABASE_URL"),
            jwt_secret_key=optional_value("JWT_SECRET_KEY"),
            jwt_issuer=jwt_issuer,
            jwt_audience=jwt_audience,
            access_token_ttl_minutes=positive_integer("ACCESS_TOKEN_TTL_MINUTES", 15),
            refresh_token_ttl_days=positive_integer("REFRESH_TOKEN_TTL_DAYS", 14),
            auth_cookie_secure=cookie_secure,
            auth_cookie_samesite=same_site,
        )

    def validate_authentication(self) -> None:
        """Confere segredos e cookies antes de atender requisições autenticadas."""
        self.validate_environment()
        if not self.jwt_secret_key or len(self.jwt_secret_key.encode("utf-8")) < 32:
            raise SettingsError("JWT_SECRET_KEY deve conter ao menos 32 bytes aleatórios.")
        if self.auth_cookie_samesite not in _SAME_SITE_VALUES:
            raise SettingsError("AUTH_COOKIE_SAMESITE deve ser 'lax', 'strict' ou 'none'.")
        if self.auth_cookie_samesite == "none" and not self.auth_cookie_secure:
            raise SettingsError("AUTH_COOKIE_SECURE deve estar habilitado com SameSite 'none'.")
        if self.access_token_ttl_minutes <= 0 or self.refresh_token_ttl_days <= 0:
            raise SettingsError("Os prazos dos tokens devem ser números positivos.")
        if not self.jwt_issuer.strip() or not self.jwt_audience.strip():
            raise SettingsError("JWT_ISSUER e JWT_AUDIENCE não podem ficar vazios.")
        if self.app_env.casefold() == "production" and not self.auth_cookie_secure:
            raise SettingsError("AUTH_COOKIE_SECURE deve estar habilitado em produção.")

    def validate_environment(self) -> None:
        """Rejeita ambientes desconhecidos, inclusive em objetos construídos diretamente."""
        if self.app_env.casefold() not in _APP_ENVIRONMENTS:
            allowed = ", ".join(sorted(_APP_ENVIRONMENTS))
            raise SettingsError(f"APP_ENV inválido. Escolha um destes valores: {allowed}.")
