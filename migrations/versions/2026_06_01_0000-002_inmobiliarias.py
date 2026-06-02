"""inmobiliarias: catálogo maestro persistente

Revision ID: 002
Revises: 001
Create Date: 2026-06-01 22:00:00

Antes esta tabla vivía en localStorage del browser de cada super-admin
(bomba de tiempo: se perdía al cambiar de equipo o limpiar caché).
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inmobiliarias",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("nombre", sa.String(255), nullable=False, unique=True, index=True),
        sa.Column("rut", sa.String(40)),
        sa.Column("web", sa.String(500)),
        sa.Column("direccion", sa.String(500)),
        sa.Column("logo_url", sa.String(500)),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )


def downgrade() -> None:
    op.drop_table("inmobiliarias")
