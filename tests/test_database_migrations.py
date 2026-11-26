from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.pool import StaticPool

from app.db.session import create_database_engine


def test_initial_migration_upgrades_and_downgrades_sqlite_memory() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    config = Config(str(repo_root / "alembic.ini"))
    engine = create_database_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    try:
        with engine.connect() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            tables = set(inspect(connection).get_table_names())
            assert {
                "users",
                "search_criteria",
                "search_criteria_skills",
                "professional_profiles",
                "professional_skills",
                "educations",
                "experiences",
                "profile_languages",
                "profile_projects",
                "course_certifications",
                "professional_links",
                "job_vacancies",
                "job_requirements",
            }.issubset(tables)

            command.downgrade(config, "base")
            remaining = set(inspect(connection).get_table_names())
            assert remaining == {"alembic_version"}
    finally:
        engine.dispose()
