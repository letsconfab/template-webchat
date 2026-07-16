"""Add bulk invite batches and recipients.

Revision ID: 0010_invite_batches
Revises: 0009_email_canonical
Create Date: 2026-07-16
"""

from alembic import op
import sqlalchemy as sa


revision = "0010_invite_batches"
down_revision = "0009_email_canonical"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "invite_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column(
            "created_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "state", sa.String(32), nullable=False, server_default="queued"
        ),
        sa.Column(
            "total_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "pending_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "sent_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "failed_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "skipped_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "cancelled_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "unknown_delivery_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "retry_wait_count", sa.Integer(), nullable=False, server_default="0"
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
    )
    op.create_index("ix_invite_batches_state", "invite_batches", ["state"])
    op.create_index(
        "ix_invite_batches_created_by_id", "invite_batches", ["created_by_id"]
    )

    op.create_table(
        "bulk_invite_recipients",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "batch_id",
            sa.Integer(),
            sa.ForeignKey("invite_batches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("email_canonical", sa.String(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column(
            "invite_id",
            sa.Integer(),
            sa.ForeignKey("invites.id"),
            nullable=True,
        ),
        sa.Column(
            "state", sa.String(32), nullable=False, server_default="pending"
        ),
        sa.Column(
            "attempt_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("lease_owner", sa.String(128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("safe_error_category", sa.String(64), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
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
    op.create_index(
        "ix_bulk_invite_recipients_batch_id",
        "bulk_invite_recipients",
        ["batch_id"],
    )
    op.create_index(
        "ix_bulk_invite_recipients_state",
        "bulk_invite_recipients",
        ["state"],
    )
    op.create_index(
        "ix_bulk_invite_recipients_email_canonical",
        "bulk_invite_recipients",
        ["email_canonical"],
    )
    op.create_index(
        "ix_bulk_invite_recipients_invite_id",
        "bulk_invite_recipients",
        ["invite_id"],
    )


def downgrade() -> None:
    op.drop_table("bulk_invite_recipients")
    op.drop_table("invite_batches")
