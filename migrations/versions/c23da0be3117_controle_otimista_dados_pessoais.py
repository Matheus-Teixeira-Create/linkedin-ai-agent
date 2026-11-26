"""Adiciona controle otimista de concorrência aos dados pessoais."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c23da0be3117"
down_revision: Union[str, None] = "a8e95f48d2c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # O valor inicial preserva todos os registros existentes.
    op.add_column(
        "search_criteria",
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )
    op.add_column(
        "professional_profiles",
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )


def downgrade() -> None:
    # A remoção do número de versão não remove os dados profissionais.
    op.drop_column("professional_profiles", "version")
    op.drop_column("search_criteria", "version")
