"""Persistência de sessões e do histórico de refresh tokens."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import AuthSessionORM, RefreshTokenORM


class AuthSessionRepository:
    """Opera somente com sessões delimitadas por usuário ou hash de token."""

    def create(
        self,
        session: Session,
        user_id: UUID,
        session_expires_at: datetime,
        csrf_token_hash: str,
        refresh_token_hash: str,
        refresh_expires_at: datetime,
    ) -> tuple[AuthSessionORM, RefreshTokenORM]:
        auth_session = AuthSessionORM(
            user_id=user_id,
            expires_at=session_expires_at,
            csrf_token_hash=csrf_token_hash,
        )
        session.add(auth_session)
        session.flush()
        refresh_token = RefreshTokenORM(
            session_id=auth_session.id,
            token_hash=refresh_token_hash,
            expires_at=refresh_expires_at,
        )
        session.add(refresh_token)
        session.flush()
        return auth_session, refresh_token

    def get_active_session(
        self, session: Session, session_id: UUID, user_id: UUID, now: datetime
    ) -> AuthSessionORM | None:
        return session.scalar(
            select(AuthSessionORM).where(
                AuthSessionORM.id == session_id,
                AuthSessionORM.user_id == user_id,
                AuthSessionORM.revoked_at.is_(None),
                AuthSessionORM.expires_at > now,
            )
        )

    def get_by_refresh_hash(
        self, session: Session, token_hash: str, *, lock: bool = False
    ) -> RefreshTokenORM | None:
        statement = select(RefreshTokenORM).where(RefreshTokenORM.token_hash == token_hash)
        if lock:
            statement = statement.with_for_update()
        return session.scalar(statement)

    def rotate(
        self,
        session: Session,
        current: RefreshTokenORM,
        now: datetime,
        new_hash: str,
        new_expires_at: datetime,
        csrf_token_hash: str,
    ) -> RefreshTokenORM:
        replacement_id = uuid4()
        replacement = RefreshTokenORM(
            id=replacement_id,
            session_id=current.session_id,
            token_hash=new_hash,
            expires_at=new_expires_at,
        )
        session.add(replacement)
        # O alvo do vínculo precisa existir antes de atualizar o token antigo,
        # para satisfazer a chave estrangeira em PostgreSQL e SQLite.
        session.flush()
        current.revoked_at = now
        current.replaced_by_id = replacement_id
        current.auth_session.csrf_token_hash = csrf_token_hash
        return replacement

    def revoke_session(self, session: Session, auth_session: AuthSessionORM, now: datetime) -> None:
        if auth_session.revoked_at is None:
            auth_session.revoked_at = now
        session.execute(
            update(RefreshTokenORM)
            .where(
                RefreshTokenORM.session_id == auth_session.id,
                RefreshTokenORM.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )

    def revoke_session_by_id(
        self, session: Session, session_id: UUID, user_id: UUID, now: datetime
    ) -> bool:
        auth_session = session.scalar(
            select(AuthSessionORM).where(
                AuthSessionORM.id == session_id,
                AuthSessionORM.user_id == user_id,
            )
        )
        if auth_session is None:
            return False
        self.revoke_session(session, auth_session, now)
        session.flush()
        return True
