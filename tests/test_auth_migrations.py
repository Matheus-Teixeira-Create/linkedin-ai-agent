"""Migração de autenticação preserva usuários e dados anteriores."""

from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.pool import StaticPool

from app.db.session import create_database_engine


def test_auth_migration_preserves_legacy_user_uuid_and_personal_data() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    config = Config(str(repo_root / "alembic.ini"))
    engine = create_database_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    user_id, criteria_id = uuid4(), uuid4()

    try:
        with engine.connect() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "657fb3215f03")
            connection.execute(
                text("INSERT INTO users (id, created_at) VALUES (:id, :created_at)"),
                {"id": user_id.hex, "created_at": "2026-01-01 00:00:00.000000"},
            )
            connection.execute(
                text("INSERT INTO search_criteria (id, user_id, desired_title) "
                     "VALUES (:id, :user_id, :title)"),
                {"id": criteria_id.hex, "user_id": user_id.hex, "title": "Analista"},
            )
            connection.commit()

            command.upgrade(config, "head")
            legacy_user = connection.execute(
                text("SELECT id, email, email_normalized, password_hash, is_active "
                     "FROM users WHERE id = :id"),
                {"id": user_id.hex},
            ).one()
            legacy_criteria = connection.execute(
                text("SELECT id, user_id, desired_title FROM search_criteria WHERE id = :id"),
                {"id": criteria_id.hex},
            ).one()
            assert legacy_user.id == user_id.hex
            assert legacy_user.email is None
            assert legacy_user.email_normalized is None
            assert legacy_user.password_hash is None
            assert bool(legacy_user.is_active)
            assert legacy_criteria.id == criteria_id.hex
            assert legacy_criteria.user_id == user_id.hex
            assert legacy_criteria.desired_title == "Analista"

            command.downgrade(config, "657fb3215f03")
            preserved_id = connection.execute(
                text("SELECT id FROM users WHERE id = :id"), {"id": user_id.hex}
            ).scalar_one()
            assert preserved_id == user_id.hex
    finally:
        engine.dispose()
