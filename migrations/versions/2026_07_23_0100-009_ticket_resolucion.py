"""resolucion_texto/resolucion_captura_url en tickets

Revision ID: 009
Revises: 008
Create Date: 2026-07-23 01:00:00

Al marcar un ticket resuelto, se guarda qué se hizo (texto) y una captura de
prueba, para que queden visibles en el ticket cerrado (no solo el estado).
Nullable: tickets ya cerrados antes de esto quedan sin resolución hasta que
alguien la agregue a mano.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tickets", sa.Column("resolucion_texto", sa.Text(), nullable=True))
    op.add_column("tickets", sa.Column("resolucion_captura_url", sa.String(length=1000), nullable=True))


def downgrade() -> None:
    op.drop_column("tickets", "resolucion_captura_url")
    op.drop_column("tickets", "resolucion_texto")
