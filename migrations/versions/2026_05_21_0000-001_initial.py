"""initial schema: usuarios, proyectos, unidades, imagenes, documentos

Revision ID: 001
Revises:
Create Date: 2026-05-21 00:00:00
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "usuarios",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("nombre", sa.String(255)),
        sa.Column("password_hash", sa.String(255)),
        sa.Column("is_admin", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("activo", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("last_login_at", sa.DateTime),
    )

    op.create_table(
        "proyectos",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("nombre", sa.String(255), nullable=False, index=True),
        sa.Column("inmobiliaria", sa.String(255)),
        sa.Column("comuna", sa.String(120), index=True),
        sa.Column("region", sa.String(120)),
        sa.Column("direccion", sa.String(255)),
        sa.Column("gps_lat", sa.Float),
        sa.Column("gps_lon", sa.Float),
        sa.Column("fase", sa.String(80), index=True),
        sa.Column("modalidad", sa.String(80)),
        sa.Column("activo", sa.Boolean, nullable=False, server_default=sa.text("true"), index=True),
        sa.Column("disponible", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("fecha_entrega", sa.String(80)),
        sa.Column("ano_entrega", sa.Integer),
        sa.Column("foto_principal_url", sa.Text),
        sa.Column("external_url", sa.Text),
        sa.Column("extra", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("stock_last_upload", JSONB),
        sa.Column("notas", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "unidades",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("proyecto_id", sa.String(64), sa.ForeignKey("proyectos.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("numero", sa.String(40), nullable=False),
        sa.Column("modelo", sa.String(80)),
        sa.Column("tipologia", sa.String(80)),
        sa.Column("tipo", sa.String(40), server_default="Depto"),
        sa.Column("orientacion", sa.String(20)),
        sa.Column("sup_total", sa.Float),
        sa.Column("sup_interior", sa.Float),
        sa.Column("sup_terraza", sa.Float),
        sa.Column("sup_logia", sa.Float),
        sa.Column("sup_jardin", sa.Float),
        sa.Column("precio_lista_uf", sa.Float),
        sa.Column("descuento_pct", sa.Float, server_default="0"),
        sa.Column("bono_pie_pct", sa.Float, server_default="0"),
        sa.Column("precio_final_uf", sa.Float),
        sa.Column("estac_flag", sa.String(20), server_default="optional"),
        sa.Column("bodega_flag", sa.String(20), server_default="optional"),
        sa.Column("pack_flag", sa.String(20), server_default="optional"),
        sa.Column("disponible", sa.Boolean, nullable=False, server_default=sa.text("true"), index=True),
        sa.UniqueConstraint("proyecto_id", "numero", name="uq_unidad_por_proyecto"),
    )

    op.create_table(
        "imagenes",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("proyecto_id", sa.String(64), sa.ForeignKey("proyectos.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("categoria", sa.String(40), nullable=False, server_default="Otro"),
        sa.Column("es_principal", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("orden", sa.Integer, nullable=False, server_default="0"),
        sa.Column("bytes", sa.Integer),
        sa.Column("mime", sa.String(60)),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "documentos",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("proyecto_id", sa.String(64), sa.ForeignKey("proyectos.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("nombre", sa.String(255), nullable=False),
        sa.Column("tipo", sa.String(60)),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("bytes", sa.Integer),
        sa.Column("mime", sa.String(60)),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )


def downgrade() -> None:
    op.drop_table("documentos")
    op.drop_table("imagenes")
    op.drop_table("unidades")
    op.drop_table("proyectos")
    op.drop_table("usuarios")
