"""Add email_canonical to users and invites; pending uniqueness.

Revision ID: 0009_email_canonical
Revises: 0008_last_login_at
Create Date: 2026-07-16

Preceded by scripts/audit_email_canonical.py. This migration also refuses to
proceed if collisions remain after backfill, rather than silently picking a
winner.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0009_email_canonical"
down_revision = "0008_last_login_at"
branch_labels = None
depends_on = None


def _raise_if_collisions(bind, table: str, *, pending_only: bool = False) -> None:
    where = "WHERE status = 'pending'" if pending_only else ""
    rows = bind.execute(
        sa.text(
            f"""
            SELECT email_canonical, COUNT(*) AS n
            FROM {table}
            {where}
            GROUP BY email_canonical
            HAVING COUNT(*) > 1
            """
        )
    ).fetchall()
    if rows:
        detail = ", ".join(f"{r[0]} ({r[1]})" for r in rows)
        label = "pending invite" if pending_only else table.rstrip("s")
        raise RuntimeError(
            f"email_canonical collisions on {label}s; resolve by hand before "
            f"migrating: {detail}"
        )


def upgrade() -> None:
    bind = op.get_bind()

    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("email_canonical", sa.String(), nullable=True))

    with op.batch_alter_table("invites") as batch:
        batch.add_column(sa.Column("email_canonical", sa.String(), nullable=True))

    bind.execute(
        sa.text(
            "UPDATE users SET email_canonical = lower(trim(email)) "
            "WHERE email_canonical IS NULL"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE invites SET email_canonical = lower(trim(email)) "
            "WHERE email_canonical IS NULL"
        )
    )

    # Reap expired pending before uniqueness decisions / collision checks.
    bind.execute(
        sa.text(
            """
            UPDATE invites
            SET status = 'expired', updated_at = CURRENT_TIMESTAMP
            WHERE status = 'pending'
              AND expiry_date <= CURRENT_TIMESTAMP
            """
        )
    )

    _raise_if_collisions(bind, "users")
    _raise_if_collisions(bind, "invites", pending_only=True)

    with op.batch_alter_table("users") as batch:
        batch.alter_column(
            "email_canonical",
            existing_type=sa.String(),
            nullable=False,
        )
        batch.create_index(
            "ix_users_email_canonical",
            ["email_canonical"],
            unique=True,
        )

    with op.batch_alter_table("invites") as batch:
        batch.alter_column(
            "email_canonical",
            existing_type=sa.String(),
            nullable=False,
        )
        batch.create_index("ix_invites_email_canonical", ["email_canonical"])

    # Partial unique index: one live pending invite per canonical address.
    # Supported on both Postgres and SQLite.
    op.create_index(
        "uq_invites_email_canonical_pending",
        "invites",
        ["email_canonical"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
        sqlite_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_invites_email_canonical_pending",
        table_name="invites",
    )
    with op.batch_alter_table("invites") as batch:
        batch.drop_index("ix_invites_email_canonical")
        batch.drop_column("email_canonical")

    with op.batch_alter_table("users") as batch:
        batch.drop_index("ix_users_email_canonical")
        batch.drop_column("email_canonical")
