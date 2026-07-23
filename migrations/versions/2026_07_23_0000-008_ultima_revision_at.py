"""ultima_revision_at en proyectos: marca cuándo un scraper REVISÓ el proyecto

Revision ID: 008
Revises: 007
Create Date: 2026-07-23 00:00:00

Distinto de stock_updated_at (que solo cambia si el STOCK realmente cambió).
Un scraper puede revisar cada hora y no tocar stock_updated_at ni una vez si su
sanity-check bloquea la subida (fuente muestra una baja sospechosa) — sin este
campo, el listado mostraba "9 días desactualizado" para un proyecto revisado
hace 40 minutos y deliberadamente congelado por seguridad. Nullable: filas
existentes quedan NULL hasta la próxima revisión real.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("proyectos", sa.Column("ultima_revision_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("proyectos", "ultima_revision_at")
