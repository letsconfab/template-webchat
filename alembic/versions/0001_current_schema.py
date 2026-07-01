"""Baseline the schema that predates managed migrations.

Revision ID: 0001_current_schema
Revises:
Create Date: 2026-07-01
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_current_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_users_id", "users", ["id"])
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "system_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("is_configured", sa.Boolean(), nullable=False),
        sa.Column("configured_at", sa.DateTime()),
        sa.Column("configured_by", sa.String()),
        sa.Column("app_name", sa.String(255)),
        sa.Column("app_description", sa.Text()),
        sa.Column("company_name", sa.String(255)),
        sa.Column("smtp_server", sa.String(255)),
        sa.Column("smtp_port", sa.Integer()),
        sa.Column("smtp_username", sa.String(255)),
        sa.Column("smtp_password", sa.String(255)),
        sa.Column("from_email", sa.String(255)),
        sa.Column("use_tls", sa.Boolean(), nullable=False),
        sa.Column("frontend_url", sa.String(500)),
        sa.Column("session_timeout_minutes", sa.Integer(), nullable=False),
        sa.Column("max_login_attempts", sa.Integer(), nullable=False),
        sa.Column("email_notifications_enabled", sa.Boolean(), nullable=False),
        sa.Column("user_registration_enabled", sa.Boolean(), nullable=False),
        sa.Column("llm_provider", sa.String(50), nullable=False),
        sa.Column("llm_model", sa.String(100), nullable=False),
        sa.Column("llm_api_key", sa.String(500)),
        sa.Column("rag_provider", sa.String(50), nullable=False),
        sa.Column("rag_model", sa.String(100), nullable=False),
        sa.Column("rag_api_key", sa.String(500)),
        sa.Column("rag_base_url", sa.String(500)),
        sa.Column("google_drive_enabled", sa.Boolean(), nullable=False),
        sa.Column("google_drive_refresh_token", sa.Text()),
        sa.Column("google_drive_root_folder_id", sa.String(500)),
        sa.Column("google_drive_last_synced", sa.DateTime()),
        sa.Column("neo4j_url", sa.String(500), nullable=False),
        sa.Column("neo4j_user", sa.String(100), nullable=False),
        sa.Column("neo4j_password", sa.String(500)),
        sa.Column("neo4j_database", sa.String(100), nullable=False),
        sa.Column("cocoindex_embedding_model", sa.String(200), nullable=False),
        sa.Column("graphrag_enabled", sa.Boolean(), nullable=False),
        sa.Column("foundry_url", sa.String(500)),
        sa.Column("foundry_confab_id", sa.Integer()),
        sa.Column("langfuse_secret_key", sa.String(500)),
        sa.Column("langfuse_public_key", sa.String(500)),
        sa.Column("langfuse_base_url", sa.String(500)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_system_settings_id", "system_settings", ["id"])

    op.create_table(
        "invites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("token", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("expiry_date", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column(
            "created_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
    )
    op.create_index("ix_invites_id", "invites", ["id"])
    op.create_index("ix_invites_email", "invites", ["email"])
    op.create_index("ix_invites_token", "invites", ["token"], unique=True)

    op.create_table(
        "wiki_pages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", sa.Text()),
        sa.Column("category", sa.String(100)),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("wiki_pages.id")),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("source_id", sa.Integer()),
        sa.Column("is_draft", sa.Boolean()),
        sa.Column("is_processed", sa.Boolean()),
        sa.Column("is_folder", sa.Boolean()),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
    )
    op.create_index("ix_wiki_pages_id", "wiki_pages", ["id"])

    op.create_table(
        "wiki_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "page_id",
            sa.Integer(),
            sa.ForeignKey("wiki_pages.id"),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("diff_from_previous", sa.Text()),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("ix_wiki_versions_id", "wiki_versions", ["id"])

    op.create_table(
        "knowledge_insights",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(255)),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("source_user_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("source_message_id", sa.Integer()),
        sa.Column("chat_session_id", sa.String(100)),
        sa.Column("status", sa.String(20)),
        sa.Column("tags", sa.JSON()),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("reviewed_at", sa.DateTime()),
        sa.Column("reviewed_by_id", sa.Integer(), sa.ForeignKey("users.id")),
    )
    op.create_index("ix_knowledge_insights_id", "knowledge_insights", ["id"])

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.String(100), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("msg_metadata", sa.JSON()),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("ix_chat_messages_id", "chat_messages", ["id"])
    op.create_index("ix_chat_messages_session_id", "chat_messages", ["session_id"])

    op.create_table(
        "user_feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("rating", sa.Integer()),
        sa.Column("feedback_type", sa.String(20), nullable=False),
        sa.Column("message", sa.Text()),
        sa.Column("categories", sa.JSON()),
        sa.Column(
            "chat_message_id",
            sa.Integer(),
            sa.ForeignKey("chat_messages.id"),
        ),
        sa.Column("created_at", sa.DateTime()),
    )
    op.create_index("ix_user_feedback_id", "user_feedback", ["id"])


def downgrade() -> None:
    op.drop_table("user_feedback")
    op.drop_table("chat_messages")
    op.drop_table("knowledge_insights")
    op.drop_table("wiki_versions")
    op.drop_table("wiki_pages")
    op.drop_table("invites")
    op.drop_table("system_settings")
    op.drop_table("users")

