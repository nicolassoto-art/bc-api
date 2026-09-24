"""reserva_bc/reserva_bc_at en unidades: marca "reservada por BigCapital"

Revision ID: 010
Revises: 009
Create Date: 2026-09-24 00:00:00

Nuestro stock y el de la inmobiliaria son dos. Al reservar en la intranet la unidad
sale del nuestro, pero sigue libre en PlanOk hasta que la inmobiliaria la registra;
mientras tanto la lectura horaria ("aparece en el Excel = disponible") la volvía a
abrir. La marca guarda el correlativo de la reserva (RES-…) y, mientras exista, la
unidad no puede quedar disponible. Nullable: las unidades existentes quedan sin marca
y se comportan igual que antes.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("unidades", sa.Column("reserva_bc", sa.String(length=40), nullable=True))
    op.add_column("unidades", sa.Column("reserva_bc_at", sa.DateTime(), nullable=True))
    op.create_index("ix_unidades_reserva_bc", "unidades", ["reserva_bc"])


def downgrade() -> None:
    op.drop_index("ix_unidades_reserva_bc", table_name="unidades")
    op.drop_column("unidades", "reserva_bc_at")
    op.drop_column("unidades", "reserva_bc")
