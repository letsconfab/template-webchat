"""Add immutable Feedback Case correspondence.

Revision ID: 0005_case_correspondence
Revises: 0004_admin_replay_diagnostics
Create Date: 2026-07-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_case_correspondence"
down_revision = "0004_admin_replay_diagnostics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "case_replies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "case_id",
            sa.Integer(),
            sa.ForeignKey("feedback_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "author_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("author_role", sa.String(16), nullable=False),
        sa.Column("raw_text", sa.String(4000), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_case_replies_case_id", "case_replies", ["case_id"])
    op.create_index("ix_case_replies_author_id", "case_replies", ["author_id"])


def downgrade() -> None:
    op.drop_table("case_replies")

