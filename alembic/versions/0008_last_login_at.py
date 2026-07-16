"""Add last_login_at and inferred_last_activity_at on users.

Revision ID: 0008_last_login_at
Revises: 0007_rollout_flags
Create Date: 2026-07-16

Columns only — no backfill. Activity population is a separate resumable CLI
(see scripts/backfill_user_activity.py) so ExecStartPre migrations stay fast.
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_last_login_at"
down_revision = "0007_rollout_flags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("last_login_at", sa.DateTime(), nullable=True))
        batch.add_column(
            sa.Column("inferred_last_activity_at", sa.DateTime(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("inferred_last_activity_at")
        batch.drop_column("last_login_at")
