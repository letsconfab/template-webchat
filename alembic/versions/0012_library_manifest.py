"""Add the Library Manifest setting.

Revision ID: 0012_library_manifest
Revises: 0011_sessions_journeys
Create Date: 2026-10-19
"""

from alembic import op
import sqlalchemy as sa


revision = "0012_library_manifest"
down_revision = "0011_sessions_journeys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("system_settings") as batch:
        batch.add_column(
            sa.Column("library_manifest_file_id", sa.String(length=500), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("system_settings") as batch:
        batch.drop_column("library_manifest_file_id")
