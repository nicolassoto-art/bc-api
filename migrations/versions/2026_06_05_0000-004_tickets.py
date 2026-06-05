"""tickets: reporte de fallas (Fase 5)

Revision ID: 004
Revises: 003
Create Date: 2026-06-05 00:00:00

Tabla nueva (additive, segura). Cualquier usuario autenticado crea un ticket;
super-admin lista y cierra. La captura (imagen) se sirve desde /uploads/tickets/.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tickets",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("autor", sa.String(length=255), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=True),
        sa.Column("descripcion", sa.Text(), nullable=False),
        sa.Column("captura_url", sa.String(length=1000), nullable=True),
        sa.Column("estado", sa.String(length=20), nullable=False, server_default="abierto"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tickets_autor", "tickets", ["autor"])
    op.create_index("ix_tickets_estado", "tickets", ["estado"])


def downgrade() -> None:
    op.drop_index("ix_tickets_estado", table_name="tickets")
    op.drop_index("ix_tickets_autor", table_name="tickets")
    op.drop_table("tickets")
