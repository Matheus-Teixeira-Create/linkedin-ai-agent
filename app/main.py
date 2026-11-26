"""Aplicação FastAPI e gerenciamento do ciclo de vida do banco."""

from contextlib import asynccontextmanager
import hashlib
import hmac
import secrets
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

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
        if not app_settings.database_url:
            raise SettingsError("DATABASE_URL deve ser configurada em produção.")

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

    application = FastAPI(
        title="LinkedIn AI Agent",
        description="API de autenticação e gerenciamento de usuários.",
        lifespan=lifespan,
    )
    application.state.settings = app_settings
    application.state.auth_rate_limiter = auth_rate_limiter
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

    return application


app = create_app()
