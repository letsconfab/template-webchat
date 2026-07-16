"""Invite claim service — canonical email, expiry reaper, and DB-enforced uniqueness."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.invite import Invite, InviteStatus
from backend.models.user import User
from backend.services.auth import generate_secure_token


class InviteClaimError(Exception):
    """Domain error from claim_invite; routers map ``detail`` to HTTP 400."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


def canonicalize_email(email: str) -> str:
    """Trim and lowercase for case-insensitive identity."""
    return email.strip().lower()


async def reap_expired_invites(db: AsyncSession) -> int:
    """Flip expired pending invites to EXPIRED. Returns rows affected."""
    now = datetime.utcnow()
    result = await db.execute(
        update(Invite)
        .where(
            Invite.status == InviteStatus.PENDING,
            Invite.expiry_date <= now,
        )
        .values(status=InviteStatus.EXPIRED, updated_at=now)
    )
    return result.rowcount or 0


async def claim_invite(
    db: AsyncSession,
    *,
    email: str,
    role: str,
    created_by_id: int,
    expiry_days: int = 7,
) -> Invite:
    """Canonicalize, reap expired, check for an account, then insert.

    The partial unique index on ``email_canonical WHERE status = 'pending'``
    is the correctness mechanism. A uniqueness violation becomes
    ``InviteClaimError("already invited")``.
    """
    display_email = email.strip()
    canonical = canonicalize_email(email)

    await reap_expired_invites(db)

    existing_user = (
        await db.execute(select(User).where(User.email_canonical == canonical))
    ).scalar_one_or_none()
    if existing_user:
        raise InviteClaimError("User with this email already exists")

    invite = Invite(
        email=display_email,
        email_canonical=canonical,
        token=generate_secure_token(),
        role=role,
        status=InviteStatus.PENDING,
        expiry_date=datetime.utcnow() + timedelta(days=expiry_days),
        created_by_id=created_by_id,
    )
    db.add(invite)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise InviteClaimError(
            "Pending invitation already exists for this email"
        ) from exc

    return invite
