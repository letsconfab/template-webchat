"""Add fail-closed projections and bounded execution traces.

Revision ID: 0004_admin_replay_diagnostics
Revises: 0003_feedback_cases
Create Date: 2026-07-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_admin_replay_diagnostics"
down_revision = "0003_feedback_cases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_projections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("content_type", sa.String(40), nullable=False),
        sa.Column("content_id", sa.Integer(), nullable=False),
        sa.Column("source_field", sa.String(40), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("redacted_text", sa.Text()),
        sa.Column("safe_error_category", sa.String(40)),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "content_type",
            "content_id",
            "source_field",
            "version",
            name="uq_admin_projection_source_version",
        ),
    )
    op.create_index(
        "ix_admin_projections_content_type",
        "admin_projections",
        ["content_type"],
    )
    op.create_index(
        "ix_admin_projections_content_id",
        "admin_projections",
        ["content_id"],
    )
    op.create_table(
        "execution_traces",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "chat_message_id",
            sa.Integer(),
            sa.ForeignKey("chat_messages.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("events", sa.JSON(), nullable=False),
        sa.Column("event_count", sa.Integer(), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("truncated", sa.Boolean(), nullable=False),
        sa.Column("safe_error_category", sa.String(40)),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_execution_traces_chat_message_id",
        "execution_traces",
        ["chat_message_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("execution_traces")
    op.drop_table("admin_projections")

