"""Add durable tester email notifications.

Revision ID: 0006_case_notifications
Revises: 0005_case_correspondence
Create Date: 2026-07-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_case_notifications"
down_revision = "0005_case_correspondence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "case_notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "case_reply_id",
            sa.Integer(),
            sa.ForeignKey("case_replies.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "recipient_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "state", sa.String(16), nullable=False, server_default="pending"
        ),
        sa.Column(
            "attempt_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("safe_error_category", sa.String(40)),
        sa.Column("last_attempt_at", sa.DateTime()),
        sa.Column("sent_at", sa.DateTime()),
        sa.Column(
            "created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_case_notifications_case_reply_id",
        "case_notifications",
        ["case_reply_id"],
        unique=True,
    )
    op.create_index(
        "ix_case_notifications_recipient_user_id",
        "case_notifications",
        ["recipient_user_id"],
    )


def downgrade() -> None:
    op.drop_table("case_notifications")

