"""Emissão e validação estrita de access tokens JWT."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
from jwt.exceptions import InvalidTokenError

from config.settings import Settings


class InvalidAccessToken(ValueError):
    """Indica token ausente, inválido, expirado ou com claims incorretos."""


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    user_id: UUID
    session_id: UUID


@dataclass(frozen=True, slots=True)
class IssuedAccessToken:
    value: str = field(repr=False)
    expires_at: datetime


class AccessTokenManager:
    """Usa HS256 fixo e valida emissor, audiência e todos os tempos do JWT."""

    _ALGORITHM = "HS256"

    def __init__(self, settings: Settings) -> None:
        settings.validate_authentication()
        self._key = settings.jwt_secret_key
        self._issuer = settings.jwt_issuer
        self._audience = settings.jwt_audience
        self._ttl = timedelta(minutes=settings.access_token_ttl_minutes)

    def issue(self, user_id: UUID, session_id: UUID, now: datetime | None = None) -> IssuedAccessToken:
        issued_at = now or datetime.now(UTC)
        expires_at = issued_at + self._ttl
        token = jwt.encode(
            {
                "sub": str(user_id),
                "sid": str(session_id),
                "iss": self._issuer,
                "aud": self._audience,
                "iat": issued_at,
                "nbf": issued_at,
                "exp": expires_at,
                "jti": str(uuid4()),
            },
            self._key,
            algorithm=self._ALGORITHM,
        )
        return IssuedAccessToken(value=token, expires_at=expires_at)

    def decode(self, token: str) -> AccessTokenClaims:
        try:
            claims = jwt.decode(
                token,
                self._key,
                algorithms=[self._ALGORITHM],
                issuer=self._issuer,
                audience=self._audience,
                options={"require": ["sub", "sid", "iss", "aud", "iat", "nbf", "exp", "jti"]},
            )
            user_id = UUID(claims["sub"])
            session_id = UUID(claims["sid"])
            UUID(claims["jti"])
        except (InvalidTokenError, KeyError, TypeError, ValueError):
            raise InvalidAccessToken("Token de acesso inválido.") from None
        return AccessTokenClaims(user_id=user_id, session_id=session_id)
