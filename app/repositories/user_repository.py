"""Consultas e gravações de contas de usuário."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import UserORM


class UserRepository:
    """Mantém a persistência de usuários fora do serviço de autenticação."""

    def get_by_normalized_email(self, session: Session, email: str) -> UserORM | None:
        return session.scalar(select(UserORM).where(UserORM.email_normalized == email))

    def get_by_id(self, session: Session, user_id: UUID) -> UserORM | None:
        return session.get(UserORM, user_id)

    def create(self, session: Session, email: str, email_normalized: str, password_hash: str) -> UserORM:
        user = UserORM(
            email=email,
            email_normalized=email_normalized,
            password_hash=password_hash,
            is_active=True,
        )
        session.add(user)
        session.flush()
        return user

    def update_password_hash(self, user: UserORM, password_hash: str) -> None:
        user.password_hash = password_hash
