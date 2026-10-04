"""stock_ok_at en proyectos: última revisión de stock que salió bien

Revision ID: 012
Revises: 011
Create Date: 2026-10-05 00:00:00

Base del correo "Stock interno · proyectos sin revisar" (pedido de Nicolás, 30/09/2026):
cuenta como revisado que un robot corrió sin cambios o que una persona revisó y no
encontró nada nuevo. Ni `stock_updated_at` ni `ultima_revision_at` sirven tal cual:
- `stock_updated_at` lo mueve también la marca de reserva de la intranet (una reserva
  no revisa el resto del stock) y no lo debe mover el botón "Revisé el stock: sin
  cambios" (es la fecha que ve el corredor en el catálogo).
- `ultima_revision_at` lo mueve también una alerta de robot bloqueado, justo el caso
  que el correo tiene que mostrar.
La columna es solo aditiva: nada existente la lee. Se rellena con `stock_updated_at`,
que es la mejor aproximación previa. NUNCA revertir el commit de este archivo: si se
borra, el deploy siguiente falla en `alembic upgrade head` (la base quedaría en 012).
"""
from typing import Union
from alembic import op
import sqlalchemy as sa


revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("proyectos", sa.Column("stock_ok_at", sa.DateTime(), nullable=True))
    op.execute("UPDATE proyectos SET stock_ok_at = stock_updated_at WHERE stock_ok_at IS NULL")


def downgrade() -> None:
    op.drop_column("proyectos", "stock_ok_at")
