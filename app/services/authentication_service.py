"""Cadastro, login e gerenciamento de sessões autenticadas."""

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import secrets
from typing import Iterator
from uuid import UUID

from email_validator import EmailNotValidError, validate_email
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import AuthSessionORM, UserORM
from app.repositories.auth_session_repository import AuthSessionRepository
from app.repositories.user_repository import UserRepository
from app.security.passwords import PasswordManager, get_password_manager
from app.security.tokens import AccessTokenManager, InvalidAccessToken, IssuedAccessToken
from config.settings import Settings


class AuthenticationInputError(ValueError):
    """Indica dados inválidos para uma operação de autenticação."""


class InvalidCredentialsError(ValueError):
    """Mensagem deliberadamente genérica para falhas de login."""


class InvalidRefreshTokenError(ValueError):
    """Indica refresh token inválido, expirado, revogado ou reutilizado."""


class CsrfValidationError(ValueError):
    """Indica falha na validação CSRF de uma operação com cookies."""


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    user: UserORM
    session_id: UUID


@dataclass(frozen=True, slots=True)
class SessionCredentials:
    user: UserORM
    session_id: UUID
    access_token: IssuedAccessToken = field(repr=False)
    refresh_token: str = field(repr=False)
    csrf_token: str = field(repr=False)
    refresh_expires_at: datetime


def _utc(value: datetime) -> datetime:
    """Normaliza timestamps do SQLite, que pode remover a informação de fuso."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@contextmanager
def _write_transaction(session: Session) -> Iterator[None]:
    """Usa savepoint se a requisição já abriu uma transação de leitura."""
    transaction = session.begin_nested() if session.in_transaction() else session.begin()
    with transaction:
        yield


class AuthenticationService:
    """Coordena regras de autenticação sem expor credenciais nas respostas."""

    def __init__(
        self,
        session: Session,
        settings: Settings,
        users: UserRepository | None = None,
        sessions: AuthSessionRepository | None = None,
        passwords: PasswordManager | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.users = users or UserRepository()
        self.sessions = sessions or AuthSessionRepository()
        self.passwords = passwords or get_password_manager()

    @staticmethod
    def normalize_email(email: str) -> str:
        if not isinstance(email, str):
            raise AuthenticationInputError("Informe um endereço de e-mail válido.")
        try:
            normalized = validate_email(email.strip(), check_deliverability=False).normalized
        except EmailNotValidError:
            raise AuthenticationInputError("Informe um endereço de e-mail válido.") from None
        return normalized.casefold()

    def register(self, email: str, password: str) -> bool:
        normalized_email = self.normalize_email(email)
        self._validate_new_password(password)
        password_hash = self.passwords.hash(password)
        try:
            with _write_transaction(self.session):
                if self.users.get_by_normalized_email(self.session, normalized_email):
                    return False
                self.users.create(self.session, normalized_email, normalized_email, password_hash)
        except IntegrityError:
            # A constraint única também resolve a corrida entre cadastros simultâneos.
            return False
        return True

    def login(self, email: str, password: str) -> SessionCredentials:
        normalized_email = self.normalize_email(email)
        now = datetime.now(UTC)
        result: SessionCredentials | None = None
        with _write_transaction(self.session):
            user = self.users.get_by_normalized_email(self.session, normalized_email)
            encoded_hash = user.password_hash if user is not None else None
            password_valid = self.passwords.verify(password, encoded_hash)
            if user is None or not user.is_active or not password_valid:
                raise InvalidCredentialsError("E-mail ou senha inválidos.")

            if user.password_hash and self.passwords.needs_rehash(user.password_hash):
                self.users.update_password_hash(user, self.passwords.hash(password))

            refresh_ttl = timedelta(days=self.settings.refresh_token_ttl_days)
            session_expires_at = now + refresh_ttl
            refresh_token = secrets.token_urlsafe(48)
            csrf_token = secrets.token_urlsafe(32)
            auth_session, _ = self.sessions.create(
                self.session,
                user.id,
                session_expires_at,
                _token_hash(csrf_token),
                _token_hash(refresh_token),
                session_expires_at,
            )
            access_token = self._token_manager().issue(user.id, auth_session.id, now)
            result = SessionCredentials(
                user=user,
                session_id=auth_session.id,
                access_token=access_token,
                refresh_token=refresh_token,
                csrf_token=csrf_token,
                refresh_expires_at=session_expires_at,
            )
        assert result is not None
        return result

    def authenticate_access_token(self, token: str) -> AuthenticatedPrincipal:
        claims = self._token_manager().decode(token)
        now = datetime.now(UTC)
        auth_session = self.sessions.get_active_session(
            self.session, claims.session_id, claims.user_id, now
        )
        user = self.users.get_by_id(self.session, claims.user_id)
        if auth_session is None or user is None or not user.is_active:
            raise InvalidAccessToken("Token de acesso inválido.")
        return AuthenticatedPrincipal(user=user, session_id=auth_session.id)

    def refresh(
        self,
        refresh_token: str | None,
        csrf_cookie: str | None,
        csrf_header: str | None,
    ) -> SessionCredentials:
        if not refresh_token:
            raise InvalidRefreshTokenError("Sessão inválida.")
        if not self._csrf_values_match(csrf_cookie, csrf_header):
            raise CsrfValidationError("Validação CSRF inválida.")

        now = datetime.now(UTC)
        new_refresh_token = secrets.token_urlsafe(48)
        new_csrf_token = secrets.token_urlsafe(32)
        result: SessionCredentials | None = None
        failure: InvalidRefreshTokenError | CsrfValidationError | None = None

        # Se o token já foi usado, a revogação é confirmada antes do erro ser
        # convertido em HTTP 401 pelo endpoint. Assim, o rollback da resposta
        # não restaura uma sessão cujo refresh token foi reutilizado.
        with _write_transaction(self.session):
            current = self.sessions.get_by_refresh_hash(
                self.session, _token_hash(refresh_token), lock=True
            )
            if current is None:
                failure = InvalidRefreshTokenError("Sessão inválida.")
            else:
                auth_session = current.auth_session
                session_expiration = _utc(auth_session.expires_at)
                token_expiration = _utc(current.expires_at)
                if current.revoked_at is not None:
                    self.sessions.revoke_session(self.session, auth_session, now)
                    failure = InvalidRefreshTokenError("Sessão inválida.")
                elif auth_session.revoked_at is not None or session_expiration <= now or token_expiration <= now:
                    failure = InvalidRefreshTokenError("Sessão inválida.")
                elif not hmac.compare_digest(auth_session.csrf_token_hash, _token_hash(csrf_header or "")):
                    failure = CsrfValidationError("Validação CSRF inválida.")
                else:
                    refresh_expires_at = min(
                        now + timedelta(days=self.settings.refresh_token_ttl_days),
                        session_expiration,
                    )
                    self.sessions.rotate(
                        self.session,
                        current,
                        now,
                        _token_hash(new_refresh_token),
                        refresh_expires_at,
                        _token_hash(new_csrf_token),
                    )
                    access_token = self._token_manager().issue(auth_session.user_id, auth_session.id, now)
                    user = self.users.get_by_id(self.session, auth_session.user_id)
                    if user is None or not user.is_active:
                        self.sessions.revoke_session(self.session, auth_session, now)
                        failure = InvalidRefreshTokenError("Sessão inválida.")
                    else:
                        result = SessionCredentials(
                            user=user,
                            session_id=auth_session.id,
                            access_token=access_token,
                            refresh_token=new_refresh_token,
                            csrf_token=new_csrf_token,
                            refresh_expires_at=refresh_expires_at,
                        )

        if failure is not None:
            raise failure
        assert result is not None
        return result

    def verify_csrf_for_principal(
        self,
        principal: AuthenticatedPrincipal,
        csrf_cookie: str | None,
        csrf_header: str | None,
    ) -> None:
        if not self._csrf_values_match(csrf_cookie, csrf_header):
            raise CsrfValidationError("Validação CSRF inválida.")
        auth_session = self.sessions.get_active_session(
            self.session, principal.session_id, principal.user.id, datetime.now(UTC)
        )
        if auth_session is None or not hmac.compare_digest(
            auth_session.csrf_token_hash, _token_hash(csrf_header or "")
        ):
            raise CsrfValidationError("Validação CSRF inválida.")

    def logout(self, principal: AuthenticatedPrincipal) -> None:
        with _write_transaction(self.session):
            self.sessions.revoke_session_by_id(
                self.session,
                principal.session_id,
                principal.user.id,
                datetime.now(UTC),
            )

    def logout_with_refresh(
        self,
        refresh_token: str | None,
        csrf_cookie: str | None,
        csrf_header: str | None,
    ) -> None:
        """Revoga a sessão usando o refresh cookie, mesmo após expirar o access JWT."""
        if not refresh_token:
            raise InvalidRefreshTokenError("Sessão inválida.")
        if not self._csrf_values_match(csrf_cookie, csrf_header):
            raise CsrfValidationError("Validação CSRF inválida.")
        with _write_transaction(self.session):
            current = self.sessions.get_by_refresh_hash(
                self.session, _token_hash(refresh_token), lock=True
            )
            if current is None:
                raise InvalidRefreshTokenError("Sessão inválida.")
            auth_session = current.auth_session
            if not hmac.compare_digest(
                auth_session.csrf_token_hash, _token_hash(csrf_header or "")
            ):
                raise CsrfValidationError("Validação CSRF inválida.")
            self.sessions.revoke_session(self.session, auth_session, datetime.now(UTC))

    @staticmethod
    def _validate_new_password(password: str) -> None:
        if not isinstance(password, str) or not 12 <= len(password) <= 1024:
            raise AuthenticationInputError("A senha deve ter entre 12 e 1024 caracteres.")

    @staticmethod
    def _csrf_values_match(cookie: str | None, header: str | None) -> bool:
        return bool(cookie and header and hmac.compare_digest(cookie, header))

    def _token_manager(self) -> AccessTokenManager:
        return AccessTokenManager(self.settings)
