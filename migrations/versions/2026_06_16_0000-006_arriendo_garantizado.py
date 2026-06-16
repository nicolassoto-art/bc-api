"""add arriendo_garantizado and arriendo_moneda to unidades

Revision ID: 006
Revises: 005
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("unidades", sa.Column("arriendo_garantizado", sa.Float(), nullable=True))
    op.add_column("unidades", sa.Column("arriendo_moneda", sa.String(4), nullable=True))


def downgrade() -> None:
    op.drop_column("unidades", "arriendo_moneda")
    op.drop_column("unidades", "arriendo_garantizado")
