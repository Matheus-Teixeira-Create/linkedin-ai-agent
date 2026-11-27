"""Configurações da aplicação lidas do ambiente do processo."""

from collections.abc import Mapping
from dataclasses import dataclass, field
import base64
import binascii
import os
import re

from sqlalchemy.exc import ArgumentError
from sqlalchemy.engine import make_url


_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
_APP_ENVIRONMENTS = frozenset({"development", "test", "staging", "production"})
_SAME_SITE_VALUES = frozenset({"lax", "strict", "none"})
_JWT_SECRET_FORMAT = re.compile(r"[A-Za-z0-9_-]+\Z")
_KNOWN_PREDICTABLE_FRAGMENTS = (
    b"password",
    b"passw0rd",
    b"qwerty",
    b"asdfgh",
    b"zxcvbn",
    b"letmein",
    b"changeme",
    b"default",
    b"secret",
)


def _contains_obvious_sequence(value: bytes) -> bool:
    known_sequences = (
        b"abcdefghijklmnopqrstuvwxyz",
        b"zyxwvutsrqponmlkjihgfedcba",
        b"0123456789",
        b"9876543210",
    )
    if any(
        sequence[index : index + 8] in value
        for sequence in known_sequences
        for index in range(len(sequence) - 7)
    ):
        return True
    increasing = decreasing = 1
    for previous, current in zip(value, value[1:]):
        increasing = increasing + 1 if current == previous + 1 else 1
        decreasing = decreasing + 1 if current == previous - 1 else 1
        if increasing >= 8 or decreasing >= 8:
            return True
    return False


def _is_repetitive(value: bytes) -> bool:
    # Procura qualquer bloco que se repita exatamente, sem limitar o período
    # a um tamanho fixo (por exemplo, 17 bytes).
    for period in range(1, len(value) // 2 + 1):
        if len(value) % period == 0 and value == value[:period] * (len(value) // period):
            return True
    return False


def _validate_jwt_secret(value: str | None) -> None:
    """Exige ao menos 256 bits codificados em Base64 URL-safe canônico.

    Formato e filtros de padrões óbvios não comprovam entropia. A geração deve
    usar CSPRNG e o armazenamento deve ser feito em variável de ambiente ou
    gerenciador de segredos.
    """
    if not value or not _JWT_SECRET_FORMAT.fullmatch(value):
        raise SettingsError(
            "JWT_SECRET_KEY deve ser Base64 URL-safe canônico de ao menos 32 bytes aleatórios."
        )
    padding = "=" * (-len(value) % 4)
    try:
        material = base64.b64decode(value + padding, altchars=b"-_", validate=True)
    except (binascii.Error, ValueError):
        raise SettingsError(
            "JWT_SECRET_KEY deve ser Base64 URL-safe canônico de ao menos 32 bytes aleatórios."
        ) from None
    canonical = base64.urlsafe_b64encode(material).decode("ascii").rstrip("=")
    if canonical != value:
        raise SettingsError("JWT_SECRET_KEY deve usar codificação Base64 URL-safe canônica.")
    normalized_material = material.lower()
    if (
        len(material) < 32
        or _is_repetitive(value.encode("ascii"))
        or _is_repetitive(material)
        or _contains_obvious_sequence(value.encode("ascii"))
        or _contains_obvious_sequence(material)
        or any(fragment in normalized_material for fragment in _KNOWN_PREDICTABLE_FRAGMENTS)
    ):
        raise SettingsError(
            "JWT_SECRET_KEY deve representar ao menos 256 bits e não pode corresponder a padrões previsíveis conhecidos."
        )


class SettingsError(ValueError):
    """Indica que uma configuração do ambiente tem um valor inválido."""


@dataclass(frozen=True, slots=True)
class Settings:
    """Objeto de configurações da aplicação, sem dependências externas."""

    app_env: str = ""
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

    def __post_init__(self) -> None:
        """Exige ambiente explícito também em Settings construído diretamente."""
        self.validate_environment()

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

        raw_app_env = optional_value("APP_ENV")
        if raw_app_env is None:
            raise SettingsError("APP_ENV deve ser definido explicitamente.")
        app_env = raw_app_env.casefold()
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
        if app_env == "production" and raw_cookie_secure.casefold() != "true":
            raise SettingsError("AUTH_COOKIE_SECURE deve ser definido exatamente como true em produção.")

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
        _validate_jwt_secret(self.jwt_secret_key)
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

    def validate_database(self, *, production: bool = False) -> None:
        """Valida a URL do banco sem incluí-la em mensagens de erro."""
        if not self.database_url:
            if production:
                raise SettingsError("DATABASE_URL deve ser configurada em produção.")
            return
        try:
            parsed = make_url(self.database_url)
        except (ArgumentError, TypeError, ValueError):
            raise SettingsError("DATABASE_URL não contém uma URL de banco válida.") from None
        if parsed.drivername not in {"postgresql+psycopg", "sqlite", "sqlite+pysqlite"}:
            raise SettingsError("DATABASE_URL deve usar PostgreSQL ou SQLite.")
        if production and parsed.drivername != "postgresql+psycopg":
            raise SettingsError("DATABASE_URL deve usar PostgreSQL em produção.")

    def validate_environment(self) -> None:
        """Rejeita ambientes desconhecidos, inclusive em objetos construídos diretamente."""
        if not isinstance(self.app_env, str) or not self.app_env.strip():
            raise SettingsError("APP_ENV deve ser definido explicitamente.")
        normalized = self.app_env.strip().casefold()
        object.__setattr__(self, "app_env", normalized)
        if normalized not in _APP_ENVIRONMENTS:
            allowed = ", ".join(sorted(_APP_ENVIRONMENTS))
            raise SettingsError(f"APP_ENV inválido. Escolha um destes valores: {allowed}.")
