"""Dependências FastAPI para sessões, autenticação e proteção CSRF."""

from collections.abc import Iterator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.services.authentication_service import (
    AuthenticatedPrincipal,
    AuthenticationService,
    CsrfValidationError,
)
from app.security.tokens import InvalidAccessToken
from config.settings import Settings


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db_session(request: Request) -> Iterator[Session]:
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Banco de dados não configurado.",
        )
    with factory() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def get_authentication_service(
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> AuthenticationService:
    return AuthenticationService(session, settings)


def get_current_principal(
    request: Request,
    service: AuthenticationService = Depends(get_authentication_service),
) -> AuthenticatedPrincipal:
    access_token = request.cookies.get("access_token")
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticação necessária.",
        )
    try:
        return service.authenticate_access_token(access_token)
    except InvalidAccessToken:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticação necessária.",
        ) from None


def require_csrf(
    request: Request,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    service: AuthenticationService = Depends(get_authentication_service),
) -> AuthenticatedPrincipal:
    try:
        service.verify_csrf_for_principal(
            principal,
            request.cookies.get("csrf_token"),
            request.headers.get("X-CSRF-Token"),
        )
    except CsrfValidationError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Validação CSRF inválida.",
        ) from None
    return principal
