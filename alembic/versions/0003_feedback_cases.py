"""Create durable Feedback Cases.

Revision ID: 0003_feedback_cases
Revises: 0002_owned_chat_sessions
Create Date: 2026-07-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_feedback_cases"
down_revision = "0002_owned_chat_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "feedback_cases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("public_id", sa.String(36), nullable=False),
        sa.Column(
            "feedback_id",
            sa.Integer(),
            sa.ForeignKey("user_feedback.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "chat_session_id",
            sa.Integer(),
            sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "rated_message_id",
            sa.Integer(),
            sa.ForeignKey("chat_messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(24),
            nullable=False,
            server_default="awaiting_admin",
        ),
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
        sa.UniqueConstraint("public_id", name="uq_feedback_cases_public_id"),
    )
    op.create_index(
        "ix_feedback_cases_public_id",
        "feedback_cases",
        ["public_id"],
        unique=True,
    )
    op.create_index("ix_feedback_cases_user_id", "feedback_cases", ["user_id"])
    op.create_index(
        "ix_feedback_cases_chat_session_id",
        "feedback_cases",
        ["chat_session_id"],
    )
    op.create_index(
        "ix_feedback_cases_rated_message_id",
        "feedback_cases",
        ["rated_message_id"],
    )


def downgrade() -> None:
    op.drop_table("feedback_cases")

