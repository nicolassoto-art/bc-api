"""descuento_pct/bono_pie_pct en unidades: sin DEFAULT 0 (null = "sin dato")

Revision ID: 011
Revises: 010
Create Date: 2026-09-30 00:00:00

La migración inicial les puso server_default "0". Como la ORM omite los None en el
INSERT, la base rellenaba con 0 cada alta que no traía el dato: un scraper sin fuente
de bono (Euro/Mobysuite) creaba unidades con bono 0%, y el editor toma ese 0 como dato
real de la unidad, tapando el bono de la ficha del proyecto (239 unidades de Euro al
2026-09-30). Regla del negocio: None = sin dato, hereda la ficha; 0 = cero real.
Solo cambia el DEFAULT de la columna: no toca filas existentes y ya eran nullable.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for col in ("descuento_pct", "bono_pie_pct"):
        op.alter_column("unidades", col, server_default=None,
                        existing_type=sa.Float(), existing_nullable=True)


def downgrade() -> None:
    for col in ("descuento_pct", "bono_pie_pct"):
        op.alter_column("unidades", col, server_default="0",
                        existing_type=sa.Float(), existing_nullable=True)
