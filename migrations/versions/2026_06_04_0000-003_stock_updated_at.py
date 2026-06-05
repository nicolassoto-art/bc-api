"""stock_updated_at en proyectos: marca solo cambios de stock

Revision ID: 003
Revises: 002
Create Date: 2026-06-04 20:30:00

La columna "último stock actualizado" del listado debe reflejar SOLO cambios de
unidades (no cualquier edición del proyecto). Nullable: las filas existentes
quedan NULL y el frontend cae a updated_at hasta el próximo cambio de stock real
(stock_updated_at lo setean las mutaciones de unidades en app/routes/unidades.py).
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("proyectos", sa.Column("stock_updated_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("proyectos", "stock_updated_at")
