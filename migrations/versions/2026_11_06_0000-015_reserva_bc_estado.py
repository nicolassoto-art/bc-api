"""reserva_bc_estado y reserva_bc_vista_disponible_at en unidades: marca provisoria

Revision ID: 015
Revises: 014
Create Date: 2026-11-06 00:00:00

«PlanOk manda» (decisión de Nicolás, 6-nov-2026). La marca de reserva de la intranet
(reserva_bc) deja de ocultar la unidad para siempre: es una marca PROVISORIA que dura
hasta que PlanOk la muestre tomada o 24 h como máximo.

- reserva_bc_estado: provisoria | confirmada | no_tomada | caida (null = marca puesta
  antes de este cambio; se interpreta por la edad de reserva_bc_at).
- reserva_bc_vista_disponible_at: primera subida en que una reserva confirmada volvió a
  aparecer disponible en PlanOk. Se exige una 2ª subida seguida para declararla caída.

Nullable y sin default: solo aditiva. NUNCA revertir el commit de este archivo (el
deploy siguiente fallaría en `alembic upgrade head`). Para volver atrás se revierte el
código; las columnas quedan.
"""
from typing import Union
from alembic import op
import sqlalchemy as sa


revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("unidades", sa.Column("reserva_bc_estado", sa.String(length=20), nullable=True))
    op.add_column("unidades", sa.Column("reserva_bc_vista_disponible_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("unidades", "reserva_bc_vista_disponible_at")
    op.drop_column("unidades", "reserva_bc_estado")
