"""proyectos.deleted_at: soft-delete (papelera de 30 días)

Revision ID: 005
Revises: 004
Create Date: 2026-06-05 01:00:00

Columna nullable additive. NULL = proyecto activo; con timestamp = en la papelera
(oculto de listados/catálogo, recuperable 30 días). Las filas existentes quedan
NULL (activas). Segura.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("proyectos", sa.Column("deleted_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("proyectos", "deleted_at")
