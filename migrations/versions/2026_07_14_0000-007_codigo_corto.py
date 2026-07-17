"""add codigo_corto to proyectos

Revision ID: 007
Revises: 006
Create Date: 2026-07-14
"""
from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("proyectos", sa.Column("codigo_corto", sa.String(8), nullable=True))
    op.create_index("ix_proyectos_codigo_corto", "proyectos", ["codigo_corto"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_proyectos_codigo_corto", table_name="proyectos")
    op.drop_column("proyectos", "codigo_corto")
