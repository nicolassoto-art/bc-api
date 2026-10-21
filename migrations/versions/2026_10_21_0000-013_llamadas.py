"""llamadas y zadarma_eventos: telefonía de las setters

Revision ID: 013
Revises: 012
Create Date: 2026-10-21 00:00:00

Base del módulo de llamadas (Zadarma): una fila por llamada con su transcripción y,
más adelante, su evaluación contra el script; y un registro crudo de los eventos
recibidos para depurar. Solo aditiva: nada existente la lee. NUNCA revertir el commit
de este archivo: si se borra, el deploy siguiente falla en `alembic upgrade head`
(la base quedaría en 013).
"""
from typing import Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "zadarma_eventos",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("evento", sa.String(40), nullable=False),
        sa.Column("pbx_call_id", sa.String(80), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("recibido_en", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_zadarma_eventos_evento", "zadarma_eventos", ["evento"])
    op.create_index("ix_zadarma_eventos_pbx_call_id", "zadarma_eventos", ["pbx_call_id"])
    op.create_index("ix_zadarma_eventos_recibido_en", "zadarma_eventos", ["recibido_en"])

    op.create_table(
        "llamadas",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("pbx_call_id", sa.String(80), nullable=False),
        sa.Column("call_id_con_grabacion", sa.String(80), nullable=True),
        sa.Column("anexo", sa.String(10), nullable=True),
        sa.Column("setter", sa.String(120), nullable=True),
        sa.Column("sentido", sa.String(10), nullable=True),
        sa.Column("numero_cliente", sa.String(40), nullable=True),
        sa.Column("numero_linea", sa.String(40), nullable=True),
        sa.Column("inicio", sa.DateTime(), nullable=True),
        sa.Column("duracion_s", sa.Integer(), nullable=True),
        sa.Column("resultado", sa.String(40), nullable=True),
        sa.Column("transcripcion_frases", postgresql.JSONB(), nullable=True),
        sa.Column("transcripcion_texto", sa.Text(), nullable=True),
        sa.Column("transcripcion_idioma", sa.String(20), nullable=True),
        sa.Column("estado", sa.String(20), nullable=False, server_default="nuevo"),
        sa.Column("intentos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evaluacion", postgresql.JSONB(), nullable=True),
        sa.Column("puntaje", sa.Float(), nullable=True),
        sa.Column("version_pauta", sa.String(20), nullable=True),
        sa.Column("evaluada_en", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_llamadas_pbx_call_id", "llamadas", ["pbx_call_id"], unique=True)
    op.create_index("ix_llamadas_call_id_con_grabacion", "llamadas", ["call_id_con_grabacion"])
    op.create_index("ix_llamadas_anexo", "llamadas", ["anexo"])
    op.create_index("ix_llamadas_setter", "llamadas", ["setter"])
    op.create_index("ix_llamadas_inicio", "llamadas", ["inicio"])
    op.create_index("ix_llamadas_estado", "llamadas", ["estado"])
    op.create_index("ix_llamadas_setter_inicio", "llamadas", ["setter", "inicio"])


def downgrade() -> None:
    op.drop_table("llamadas")
    op.drop_table("zadarma_eventos")
