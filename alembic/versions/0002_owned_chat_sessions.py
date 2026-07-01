"""Add authenticated Chat Session ownership.

Revision ID: 0002_owned_chat_sessions
Revises: 0001_current_schema
Create Date: 2026-07-01
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_owned_chat_sessions"
down_revision = "0001_current_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_uuid", sa.String(36), nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "ownership_state",
            sa.String(20),
            nullable=False,
            server_default="owned",
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
        sa.UniqueConstraint("client_uuid", name="uq_chat_sessions_client_uuid"),
    )
    op.create_index(
        "ix_chat_sessions_client_uuid",
        "chat_sessions",
        ["client_uuid"],
        unique=True,
    )
    op.create_index("ix_chat_sessions_user_id", "chat_sessions", ["user_id"])

    with op.batch_alter_table("chat_messages") as batch:
        batch.add_column(sa.Column("chat_session_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_chat_messages_chat_session_id",
            "chat_sessions",
            ["chat_session_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.create_index(
            "ix_chat_messages_chat_session_id",
            ["chat_session_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("chat_messages") as batch:
        batch.drop_index("ix_chat_messages_chat_session_id")
        batch.drop_constraint(
            "fk_chat_messages_chat_session_id",
            type_="foreignkey",
        )
        batch.drop_column("chat_session_id")
    op.drop_table("chat_sessions")

