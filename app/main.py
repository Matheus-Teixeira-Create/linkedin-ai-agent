"""Aplicação FastAPI e gerenciamento do ciclo de vida do banco."""

from contextlib import asynccontextmanager
import hashlib
import hmac
import logging
import secrets
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.types import Message, Receive, Scope, Send

from app.api.routes.auth import router as auth_router
from app.api.routes.personal_data import router as personal_data_router
from app.db.session import create_database_engine, create_session_factory
from app.security.rate_limiting import (
    AuthRateLimitPolicy,
    AuthenticationRateLimiter,
    InMemoryRateLimitStore,
    RateLimitStore,
)
from config.settings import Settings, SettingsError


_logger = logging.getLogger(__name__)


class SafeFastAPI(FastAPI):
    """Impede que exceções já convertidas em HTTP 500 cheguem ao servidor ASGI."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await super().__call__(scope, receive, send)
            return

        response_started = False
        send_failed = False

        async def tracked_send(message: Message) -> None:
            nonlocal response_started, send_failed
            if message["type"] == "http.response.start":
                response_started = True
            try:
                await send(message)
            except Exception:
                send_failed = True
                raise

        try:
            await super().__call__(scope, receive, tracked_send)
        except Exception as error:
            if send_failed:
                error_id = secrets.token_hex(8)
                _logger.error(
                    "Falha de transporte ASGI (id=%s, tipo=%s).",
                    error_id,
                    type(error).__name__,
                )
                return
            if response_started:
                # O handler interno já registrou um identificador sem a exceção.
                return

            error_id = secrets.token_hex(8)
            _logger.error(
                "Falha ASGI antes da resposta (id=%s, tipo=%s).",
                error_id,
                type(error).__name__,
            )
            response = JSONResponse(
                status_code=500,
                content={
                    "detail": "Não foi possível processar a requisição.",
                    "request_id": error_id,
                },
            )
            await response(scope, receive, send)


def create_app(
    settings: Settings | None = None,
    *,
    rate_limit_store: RateLimitStore | None = None,
    rate_limit_policy: AuthRateLimitPolicy | None = None,
) -> FastAPI:
    """Cria a aplicação; banco e segredos são configurados pelo ambiente."""
    app_settings = settings or Settings.from_env()
    app_settings.validate_environment()
    if app_settings.app_env.casefold() == "production":
        app_settings.validate_authentication()
    app_settings.validate_database(production=app_settings.app_env.casefold() == "production")
    if app_settings.app_env.casefold() == "production":
        if (
            rate_limit_store is None
            or isinstance(rate_limit_store, InMemoryRateLimitStore)
            or getattr(rate_limit_store, "is_shared", False) is not True
            or not callable(getattr(rate_limit_store, "check_and_record", None))
        ):
            raise SettingsError(
                "Produção exige uma implementação compartilhada de RateLimitStore."
            )

    fingerprint_source = (
        app_settings.jwt_secret_key.encode("utf-8")
        if app_settings.jwt_secret_key
        else secrets.token_bytes(32)
    )
    fingerprint_key = hmac.new(
        fingerprint_source, b"linkedin-ai-agent:auth-rate-limit:v1", hashlib.sha256
    ).digest()
    auth_rate_limiter = AuthenticationRateLimiter(
        rate_limit_store if rate_limit_store is not None else InMemoryRateLimitStore(),
        policy=rate_limit_policy,
        fingerprint_key=fingerprint_key,
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        engine = None
        application.state.session_factory = None
        if app_settings.database_url:
            engine = create_database_engine(app_settings.database_url, pool_pre_ping=True)
            application.state.session_factory = create_session_factory(engine)
        try:
            yield
        finally:
            if engine is not None:
                engine.dispose()

    application = SafeFastAPI(
        title="LinkedIn AI Agent",
        description="API de autenticação e gerenciamento de usuários.",
        lifespan=lifespan,
    )
    application.state.settings = app_settings
    application.state.auth_rate_limiter = auth_rate_limiter
    application.state.rate_limit_store = auth_rate_limiter.store
    application.include_router(auth_router)
    application.include_router(personal_data_router)

    @application.exception_handler(RequestValidationError)
    async def sanitized_validation_error(
        _request: Request, _error: RequestValidationError
    ) -> JSONResponse:
        # Erros padrão do Pydantic podem ecoar o conteúdo enviado no corpo.
        return JSONResponse(
            status_code=422,
            content={"detail": "Os dados da requisição são inválidos."},
        )

    @application.exception_handler(Exception)
    async def sanitized_internal_error(_request: Request, error: Exception) -> JSONResponse:
        # A exceção pode carregar SQL, parâmetros ou dados enviados pelo usuário.
        # O identificador correlaciona o log e a resposta sem expor a exceção.
        error_id = secrets.token_hex(8)
        _logger.error("Falha interna da API (id=%s, tipo=%s).", error_id, type(error).__name__)
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Não foi possível processar a requisição.",
                "request_id": error_id,
            },
        )

    return application


def _create_asgi_entrypoint() -> FastAPI:
    """Mantém importável o módulo, mas falha no startup sem configuração explícita."""
    try:
        return create_app()
    except SettingsError as configuration_error:
        startup_error = configuration_error

        @asynccontextmanager
        async def reject_startup(_application: FastAPI) -> AsyncIterator[None]:
            raise RuntimeError("Configuração obrigatória ausente ou insegura.") from startup_error
            yield

        return SafeFastAPI(lifespan=reject_startup)


app = _create_asgi_entrypoint()
