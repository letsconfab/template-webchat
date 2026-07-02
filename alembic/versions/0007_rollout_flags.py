"""Add explicit Feedback Case rollout flags.

Revision ID: 0007_rollout_flags
Revises: 0006_case_notifications
Create Date: 2026-07-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_rollout_flags"
down_revision = "0006_case_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("system_settings") as batch:
        batch.add_column(
            sa.Column(
                "admin_replay_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch.add_column(
            sa.Column(
                "tester_correspondence_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch.add_column(
            sa.Column(
                "tester_email_notifications_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("system_settings") as batch:
        batch.drop_column("tester_email_notifications_enabled")
        batch.drop_column("tester_correspondence_enabled")
        batch.drop_column("admin_replay_enabled")

