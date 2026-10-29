"""precio_con_iva_uf y precio_en_revision en unidades: precio normal y sin IVA (MNK)

Revision ID: 014
Revises: 013
Create Date: 2026-10-29 00:00:00

En MNK el precio del negocio es el SIN IVA (casilla «Descontar IVA» de PlanOk): en un
proyecto activado, `precio_lista_uf` pasa a ser el sin IVA y el precio normal (con IVA)
queda en `precio_con_iva_uf`, solo para mostrarlo. `precio_en_revision` marca una unidad
cuyo sin IVA todavía no se leyó (visible, sin cotizar ni cobrar).

Ambas nullable y sin default: las unidades existentes quedan en null y todo se comporta
igual que antes. Solo aditiva. NUNCA revertir el commit de este archivo: si se borra, el
deploy siguiente falla en `alembic upgrade head` (la base quedaría en 014). Para volver
atrás se revierte el código; las columnas quedan.
"""
from typing import Union
from alembic import op
import sqlalchemy as sa


revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("unidades", sa.Column("precio_con_iva_uf", sa.Float(), nullable=True))
    op.add_column("unidades", sa.Column("precio_en_revision", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("unidades", "precio_en_revision")
    op.drop_column("unidades", "precio_con_iva_uf")
