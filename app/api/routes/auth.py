"""Cadastro, login, renovação e encerramento de sessões."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from app.api.dependencies import (
    get_authentication_service,
    get_current_principal,
    get_settings,
)
from app.schemas.auth import GenericMessageResponse, LoginRequest, RegisterRequest, UserResponse
from app.services.authentication_service import (
    AuthenticatedPrincipal,
    AuthenticationInputError,
    AuthenticationService,
    CsrfValidationError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
)
from config.settings import Settings, SettingsError


router = APIRouter(prefix="/auth", tags=["autenticação"])


def _set_auth_cookies(response: Response, credentials, settings: Settings) -> None:
    common = {
        "secure": settings.auth_cookie_secure,
        "samesite": settings.auth_cookie_samesite,
        "path": "/",
    }
    response.set_cookie(
        "access_token",
        credentials.access_token.value,
        max_age=settings.access_token_ttl_minutes * 60,
        httponly=True,
        **common,
    )
    refresh_seconds = max(
        0, int((credentials.refresh_expires_at - datetime.now(UTC)).total_seconds())
    )
    response.set_cookie(
        "refresh_token",
        credentials.refresh_token,
        max_age=refresh_seconds,
        httponly=True,
        **common,
    )
    response.set_cookie(
        "csrf_token",
        credentials.csrf_token,
        max_age=refresh_seconds,
        httponly=False,
        **common,
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


def _clear_auth_cookies(response: Response, settings: Settings) -> None:
    common = {
        "secure": settings.auth_cookie_secure,
        "samesite": settings.auth_cookie_samesite,
        "path": "/",
    }
    for name in ("access_token", "refresh_token", "csrf_token"):
        response.delete_cookie(name, **common)


def _enforce_rate_limit(request: Request, action: str, email: str) -> None:
    """Usa o peer da conexão; não interpreta X-Forwarded-For enviado pelo cliente."""
    client_ip = request.client.host if request.client is not None else "unknown-client"
    retry_after = request.app.state.auth_rate_limiter.check(action, client_ip, email)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Muitas tentativas. Tente novamente mais tarde.",
            headers={"Retry-After": str(retry_after)},
        )


@router.post(
    "/register",
    response_model=GenericMessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def register(
    request: Request,
    payload: RegisterRequest,
    service: AuthenticationService = Depends(get_authentication_service),
) -> GenericMessageResponse:
    _enforce_rate_limit(request, "register", str(payload.email))
    try:
        # A resposta é igual para e-mail novo e já cadastrado, reduzindo enumeração.
        service.register(payload.email, payload.password.get_secret_value())
    except AuthenticationInputError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    return GenericMessageResponse(message="Solicitação de cadastro processada.")


@router.post("/login", response_model=UserResponse)
def login(
    request: Request,
    payload: LoginRequest,
    response: Response,
    service: AuthenticationService = Depends(get_authentication_service),
    settings: Settings = Depends(get_settings),
) -> UserResponse:
    _enforce_rate_limit(request, "login", str(payload.email))
    try:
        credentials = service.login(payload.email, payload.password.get_secret_value())
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha inválidos.",
        ) from None
    except SettingsError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Autenticação não configurada.",
        ) from None

    _set_auth_cookies(response, credentials, settings)
    return UserResponse(
        id=credentials.user.id,
        email=credentials.user.email or "",
        created_at=credentials.user.created_at,
    )


@router.post("/refresh", response_model=GenericMessageResponse)
def refresh(
    request: Request,
    response: Response,
    service: AuthenticationService = Depends(get_authentication_service),
    settings: Settings = Depends(get_settings),
) -> GenericMessageResponse | JSONResponse:
    try:
        credentials = service.refresh(
            request.cookies.get("refresh_token"),
            request.cookies.get("csrf_token"),
            request.headers.get("X-CSRF-Token"),
        )
    except CsrfValidationError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Validação CSRF inválida.",
        ) from None
    except InvalidRefreshTokenError:
        unauthorized = JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Sessão inválida."},
            headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
        )
        _clear_auth_cookies(unauthorized, settings)
        return unauthorized
    except SettingsError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Autenticação não configurada.",
        ) from None

    _set_auth_cookies(response, credentials, settings)
    return GenericMessageResponse(message="Sessão renovada.")


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def logout(
    request: Request,
    response: Response,
    service: AuthenticationService = Depends(get_authentication_service),
    settings: Settings = Depends(get_settings),
) -> Response | JSONResponse:
    try:
        service.logout_with_refresh(
            request.cookies.get("refresh_token"),
            request.cookies.get("csrf_token"),
            request.headers.get("X-CSRF-Token"),
        )
    except CsrfValidationError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Validação CSRF inválida.",
        ) from None
    except InvalidRefreshTokenError:
        unauthorized = JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Sessão inválida."},
            headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
        )
        _clear_auth_cookies(unauthorized, settings)
        return unauthorized
    _clear_auth_cookies(response, settings)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserResponse)
def get_authenticated_user(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> UserResponse:
    user = principal.user
    return UserResponse(id=user.id, email=user.email or "", created_at=user.created_at)
