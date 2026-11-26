"""Base declarativa compartilhada pelos mapeamentos ORM."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Metadata central usada pelo ORM e pelo Alembic."""
