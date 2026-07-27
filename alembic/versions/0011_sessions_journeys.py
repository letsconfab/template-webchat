"""Add Chat Session titles and administrator-curated journeys.

Revision ID: 0011_sessions_journeys
Revises: 0010_invite_batches
Create Date: 2026-07-27
"""

from alembic import op
import sqlalchemy as sa


revision = "0011_sessions_journeys"
down_revision = "0010_invite_batches"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("chat_sessions") as batch:
        batch.add_column(
            sa.Column(
                "title",
                sa.String(length=200),
                nullable=False,
                server_default="New chat",
            )
        )

    op.create_table(
        "journeys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("purpose", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("starter_prompt", sa.Text(), nullable=False),
        sa.Column("icon", sa.String(length=64), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("knowledge_source_labels", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("journeys")
    with op.batch_alter_table("chat_sessions") as batch:
        batch.drop_column("title")
